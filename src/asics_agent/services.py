"""External dependencies (LLM, HTTP) bundled so tests can swap in fakes."""

import dataclasses
from dataclasses import dataclass, field
from typing import Any

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from asics_agent.config import Settings, get_settings
from asics_agent.links.accessibility import make_http_client


@dataclass
class Services:
    llm: BaseChatModel
    http: httpx.Client
    settings: Settings
    _models: dict = field(default_factory=dict, repr=False)
    batcher: Any = None  # set for Step 2: model calls go out as Message Batches (batch.py)

    def batched(self, batcher) -> "Services":
        """These services with every Claude call sent through `batcher` (practice and test
        models are left as they are)."""
        llm = self.llm
        if isinstance(llm, AsicsChatAnthropic):
            llm = llm.model_copy(update={"batcher": batcher})
        return dataclasses.replace(self, llm=llm, batcher=batcher, _models={})

    def llm_for(self, model: str | None) -> BaseChatModel:
        """The chat model for an agent: its own `model:` if set, else the default one."""
        if not model or not isinstance(self.llm, ChatAnthropic) or model == self.llm.model:
            return self.llm  # practice/test models stand in for every model
        check_model(model)
        if model not in self._models:
            self._models[model] = make_chat_model(self.settings, model, batcher=self.batcher)
        return self._models[model]


class AsicsChatAnthropic(ChatAnthropic):
    """ChatAnthropic that keeps each content block's `caller` when replaying a conversation.

    With the current web_search / web_fetch tools, Claude often runs searches from inside
    code execution; those blocks carry a `caller`. langchain-anthropic drops `caller` from
    server tool blocks when it sends earlier turns back, and the API then rejects the request
    ("code_execution tool use ... without a corresponding code_execution_tool_result")
    whenever a turn continues after our own tool (e.g. check_link). Put it back.
    """

    batcher: Any = Field(default=None, exclude=True)  # see batch.py

    def _should_stream(self, *, async_api: bool, **kwargs) -> bool:
        return self.batcher is None and super()._should_stream(async_api=async_api, **kwargs)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        """With a batcher, the request goes out in the next Message Batch; anything the batch
        couldn't complete is sent as an ordinary call."""
        if self.batcher is None:
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        from asics_agent.batch import BatchItemFailed

        try:
            reply = self.batcher.submit(self._get_request_payload(messages, stop=stop, **kwargs))
        except BatchItemFailed:  # sent live (streamed, with the refusal fallback) instead
            live = self.model_copy(update={"batcher": None})
            reply = live.invoke(messages, stop=stop, **kwargs)
            return ChatResult(generations=[ChatGeneration(message=reply)])
        result = self._format_output(reply, **kwargs)
        message = result.generations[0].message
        # What a direct call would show, plus "batch" so the cost meter charges half.
        message.response_metadata.update(
            {
                k: v
                for k, v in (result.llm_output or {}).items()
                if k in ("model", "model_name", "stop_reason", "stop_sequence", "id")
            }
            | {"batch": True}
        )
        return result

    def _get_request_payload(self, input_, *, stop=None, **kwargs) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        callers = {}
        for message in self._convert_input(input_).to_messages():
            for block in message.content if isinstance(message.content, list) else []:
                if isinstance(block, dict) and block.get("caller"):
                    callers[(block.get("type"), _block_id(block))] = block["caller"]
        if callers:
            for message in payload.get("messages", []):
                content = message.get("content")
                for block in content if isinstance(content, list) else []:
                    key = (block.get("type"), _block_id(block)) if isinstance(block, dict) else None
                    if key in callers and "caller" not in block:
                        block["caller"] = callers[key]
        return payload


def _block_id(block: dict) -> str | None:
    return block.get("id") or block.get("tool_use_id")


# The only models the app may use: Sonnet 5.5 is the ceiling (nothing above Sonnet).
ALLOWED_MODELS = ("claude-sonnet-5-5", "claude-sonnet-5", "claude-haiku-5-5")
NO_FALLBACK = ("claude-haiku-5-5",)  # no server-side refusal fallback on Haiku 5.5


class ModelNotAllowed(ValueError):
    """A model above the allowed ceiling was asked for."""


def check_model(model: str) -> str:
    if model not in ALLOWED_MODELS:
        raise ModelNotAllowed(
            f"The model '{model}' isn't allowed: this app is limited to "
            f"{', '.join(ALLOWED_MODELS)} (Claude Sonnet 5.5 at most). Change it in .env "
            "(ASICS_MODEL), the agent's file in agent_setup/agents/, or the run's options."
        )
    return model


def make_chat_model(
    settings: Settings, model: str | None = None, batcher: Any = None
) -> ChatAnthropic:
    model = check_model(model or settings.model)
    extra = {}
    if settings.enable_fallbacks and model not in NO_FALLBACK:
        # Server-side fallback: if a safety classifier declines, the API retries on a
        # suitable model instead of returning a refusal. For Sonnet 5.5 that is Sonnet 5,
        # so the ceiling holds.
        extra = {
            "betas": ["server-side-fallback-2026-07-01"],
            "model_kwargs": {"fallbacks": "default"},
        }
    return AsicsChatAnthropic(
        model=model,
        max_tokens=32000,
        effort=settings.effort,
        streaming=True,
        # Longest wait for the next piece of a reply. Claude sends keep-alive pings while it
        # works, so only a dropped connection (sleep, Wi-Fi change) waits this long. The SDK
        # retries only the request that opens the stream; a timeout mid-reply is retried
        # (then reported as a failed call) by `llm._invoke`.
        default_request_timeout=settings.api_read_timeout,
        max_retries=4,
        batcher=batcher,
        **extra,
    )


def default_services(settings: Settings | None = None) -> Services:
    """Real Claude and HTTP, for the given category's settings (default: ASICS_CATEGORY)."""
    settings = settings or get_settings()
    return Services(
        llm=make_chat_model(settings),
        http=make_http_client(settings.user_agent, settings.http_timeout),
        settings=settings,
    )
