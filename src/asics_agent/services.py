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


def make_chat_model(settings: Settings, model: str | None = None) -> ChatAnthropic:
    extra = {}
    if settings.enable_fallbacks:
        # Server-side fallback: if a safety classifier declines, the API retries on a
        # suitable model instead of returning a refusal.
        extra = {
            "betas": ["server-side-fallback-2026-07-01"],
            "model_kwargs": {"fallbacks": "default"},
        }
    return ChatAnthropic(
        model=model or settings.model,
        max_tokens=32000,
        effort=settings.effort,
        streaming=True,
        max_retries=4,
        **extra,
    )


def default_services() -> Services:
    settings = get_settings()
    return Services(
        llm=make_chat_model(settings),
        http=make_http_client(settings.user_agent, settings.http_timeout),
        settings=settings,
    )
