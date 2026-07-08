"""
Groq API implementation of LLMProvider (free tier, open model such as
Llama 3.3 70B). Kept isolated from the rest of the app so switching to
another provider (e.g. Anthropic's Claude API) only requires writing a
new class here and updating LLM_PROVIDER in config — no changes to
routers, retrieval, or chunking logic.
"""
import groq
from groq import Groq

from ..config import get_settings
from .base import LLMProvider, LLMTemporarilyUnavailableError

SYSTEM_PROMPT = (
    "You are a careful research assistant helping someone understand documents in their "
    "workspace. Answer the user's question using ONLY the provided source excerpts. Each "
    "excerpt is labeled with a source number like [S1], [S2] — cite sources inline using "
    "those labels wherever you use them.\n\n"
    "Write like a knowledgeable colleague, not a disclaimer generator. If the excerpts fully "
    "answer the question, just answer it, directly and confidently. If only part of a "
    "multi-part question is covered, answer the covered parts normally and mention what's "
    "missing once, briefly, in your own words at the end — never repeat a phrase like "
    "'this is not provided in the source' for every sub-point; that reads as robotic and "
    "makes the whole answer feel low-quality even when parts of it are solid. If the excerpts "
    "don't cover the question at all, say so in one plain sentence — do not pad the answer "
    "with speculation or filler to look more complete than it is.\n\n"
    "Use Markdown formatting to make the answer genuinely easier to read: **bold** for key "
    "terms, numbered or bulleted lists for multi-part or step-by-step answers, and proper "
    "GitHub-flavored Markdown tables (with a header row and `---` separator row) for any "
    "tabular data such as counts, scores, or comparisons — never describe a table in prose "
    "when a real table would be clearer. Keep the tone natural and varied rather than "
    "mechanically repeating the same sentence structure across an answer.\n\n"
    "Actively look for relationships between the excerpts instead of describing each one in "
    "isolation. If one excerpt is clearly the answer key, correction, or solution to a question "
    "posed in another excerpt, say so explicitly (e.g. 'S4 is the corrected version of the "
    "exercise in S2') rather than listing them as two unrelated topics. If the excerpts come "
    "from documents that are supposed to be comparable (different years of the same report, "
    "different versions of the same form) and one of them is missing something the others "
    "have, point that gap out by name instead of silently working around it or padding the "
    "answer to look complete. When asked to summarize, compile, or write something from "
    "multiple sources, treat all the excerpts as one set: cover the distinct topics they "
    "contain, note where sources overlap or duplicate each other, and flag anything "
    "inconsistent across them."
)


class GroqProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Get a free key at https://console.groq.com "
                "and add it to your .env file."
            )
        self._client = Groq(api_key=settings.GROQ_API_KEY)
        self._model = settings.GROQ_MODEL

    def generate_answer(self, question: str, context_blocks: list[str], max_tokens: int = 1024) -> str:
        context = "\n\n".join(context_blocks)
        user_prompt = f"Source excerpts:\n\n{context}\n\nQuestion: {question}"
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
        except groq.RateLimitError as exc:
            # Free-tier rate limits reset quickly (per-minute or per-day
            # depending on which limit was hit) -- this is expected and
            # transient, not a real failure, so it gets its own friendly
            # message instead of surfacing the raw 429 to the user.
            raise LLMTemporarilyUnavailableError(
                "The AI service hit its free-tier rate limit. This resets on its own "
                "-- please wait a minute and try again."
            ) from exc
        except (groq.APIConnectionError, groq.APITimeoutError) as exc:
            raise LLMTemporarilyUnavailableError(
                "Couldn't reach the AI service just now. Please wait a moment and "
                "try again."
            ) from exc
        return completion.choices[0].message.content or ""
