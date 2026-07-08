"""
LLM provider interface. Any generation backend (Groq today, Anthropic's
Claude API or others later) implements this single method, so swapping
providers means adding one new module and flipping the LLM_PROVIDER
config value — no changes anywhere else in the app.
"""
from abc import ABC, abstractmethod


class LLMProviderError(Exception):
    """Base class for LLM provider failures that routers should present
    to the user as a clear, friendly message rather than a raw exception
    string. Provider modules (groq_provider.py etc.) are responsible for
    catching their SDK's own exception types and re-raising one of these
    instead, so routers never need to know which provider is active."""


class LLMTemporarilyUnavailableError(LLMProviderError):
    """The provider can't serve the request right now but it's expected
    to work again shortly on its own -- rate limiting (e.g. Groq's free
    tier) or a transient connection/timeout blip. Routers should show a
    "try again shortly" message rather than a raw error for these."""


class LLMProvider(ABC):
    @abstractmethod
    def generate_answer(self, question: str, context_blocks: list[str], max_tokens: int = 1024) -> str:
        """
        context_blocks: list of retrieved chunk texts (already formatted
        with source labels by the caller). Returns the generated answer
        as plain text.

        max_tokens defaults to the chat answer length; callers that need a
        longer generation (e.g. a multi-document notebook report) can raise
        it without affecting normal chat behavior.
        """
        raise NotImplementedError
