"""External dependencies (LLM, HTTP) bundled so tests can swap in fakes."""

from dataclasses import dataclass, field

import httpx
from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from asics_agent.config import Settings, get_settings
from asics_agent.links.accessibility import make_http_client


@dataclass
class Services:
    llm: BaseChatModel
    http: httpx.Client
    settings: Settings
    _models: dict = field(default_factory=dict, repr=False)

    def llm_for(self, model: str | None) -> BaseChatModel:
        """The chat model for an agent: its own `model:` if set, else the default one."""
        if not model or not isinstance(self.llm, ChatAnthropic) or model == self.llm.model:
            return self.llm  # practice/test models stand in for every model
        if model not in self._models:
            self._models[model] = make_chat_model(self.settings, model)
        return self._models[model]


class AsicsChatAnthropic(ChatAnthropic):
    """ChatAnthropic that keeps each content block's `caller` when replaying a conversation.

    With the current web_search / web_fetch tools, Claude often runs searches from inside
    code execution; those blocks carry a `caller`. langchain-anthropic drops `caller` from
    server tool blocks when it sends earlier turns back, and the API then rejects the request
    ("code_execution tool use ... without a corresponding code_execution_tool_result")
    whenever a turn continues after our own tool (e.g. check_link). Put it back.
    """

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


def make_chat_model(settings: Settings, model: str | None = None) -> ChatAnthropic:
    extra = {}
    if settings.enable_fallbacks:
        # Server-side fallback: if a safety classifier declines, the API retries on a
        # suitable model instead of returning a refusal.
        extra = {
            "betas": ["server-side-fallback-2026-07-01"],
            "model_kwargs": {"fallbacks": "default"},
        }
    return AsicsChatAnthropic(
        model=model or settings.model,
        max_tokens=32000,
        effort=settings.effort,
        streaming=True,
        max_retries=4,
        **extra,
    )


def default_services(settings: Settings | None = None) -> Services:
    """Real Claude and HTTP, for the given vertical's settings (default: ASICS_VERTICAL)."""
    settings = settings or get_settings()
    return Services(
        llm=make_chat_model(settings),
        http=make_http_client(settings.user_agent, settings.http_timeout),
        settings=settings,
    )
