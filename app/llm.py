"""Talking to the LLM.

All LLM calls go through this one file. Three providers are supported:
- "claude": Claude API by Anthropic (paid, strongest answers)
- "gemini": Gemini API by Google (free plan, cloud, can read photos and voice later)
- "ollama": free open-source models running on your own computer

Switch with one line in .env:  LLM_PROVIDER=claude  /  gemini  /  ollama

Later steps add more here:
- Step 3: send retrieved document chunks with the question (RAG)
- Step 6: tools (agent)
- Step 7: images and voice
- Step 9: use a cheap model for easy questions, a strong model for hard ones
"""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Protocol

import anthropic
import httpx

from app.config import Settings


class LLMError(Exception):
    """An LLM problem with a simple message we can show to the user."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class ChatModel(Protocol):
    """What every AI provider must be able to do. Claude, Gemini, Ollama, and the fake models in tests all follow this."""

    def stream_answer(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        """Chat: yield the answer piece by piece."""
        ...

    async def generate_json(self, system: str, user: str, schema: dict) -> str:
        """Step 2: return ONE answer as JSON text that follows `schema` (structured output)."""
        ...


# ---------------------------------------------------------------- Claude (paid)

class ClaudeChatModel:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        # Create the client only when first needed, so the app can start without a key.
        if self._client is None:
            key = self.settings.anthropic_api_key
            self._client = anthropic.AsyncAnthropic(api_key=key) if key else anthropic.AsyncAnthropic()
        return self._client

    async def stream_answer(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        """Send the conversation to Claude and yield the answer piece by piece (streaming)."""
        async with self.client.beta.messages.stream(
            model=self.settings.llm_model,
            max_tokens=self.settings.llm_max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": self.settings.llm_effort},
            # If the model declines a request, the API retries it on a suitable fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()

        if final.stop_reason == "refusal":
            yield "\n\nSorry, I can't help with that request."
        elif final.stop_reason == "max_tokens":
            yield "\n\n[Answer was cut off because it was too long.]"

    async def generate_json(self, system: str, user: str, schema: dict) -> str:
        """Structured output: Claude is forced to reply with JSON that matches `schema`."""
        response = await self.client.beta.messages.create(
            model=self.settings.llm_model,
            max_tokens=self.settings.llm_max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            output_config={
                "effort": self.settings.llm_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if response.stop_reason == "refusal":
            raise LLMError("The AI declined to classify this text.")
        return next((b.text for b in response.content if b.type == "text"), "")


# ---------------------------------------------------------------- Gemini (Google, free plan)

class GeminiChatModel:
    """Google's Gemini models in the cloud. Get a free key at https://aistudio.google.com/apikey

    We ask for the stream in "SSE" format: the answer comes as many lines like
      data: {"candidates": [{"content": {"parts": [{"text": "Hel"}]}}]}
      data: {"candidates": [{"content": {"parts": [{"text": "lo"}]}, "finishReason": "STOP"}]}

    Two differences from Claude/Ollama:
    - Gemini calls the AI's role "model" (not "assistant").
    - The system prompt goes in a separate "systemInstruction" field.
    """

    base_url = "https://generativelanguage.googleapis.com"
    retry_wait_scale = 1.0  # tests set this to 0 so they don't actually wait

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport  # tests pass a fake transport here

    async def stream_answer(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        key = self.settings.gemini_api_key
        if not key:
            raise LLMError("No Gemini API key found. Add GEMINI_API_KEY to .env")

        model = self.settings.gemini_model
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [
                {"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages
            ],
            "generationConfig": {"maxOutputTokens": self.settings.llm_max_tokens},
        }
        # The key goes in a header, never in the URL (URLs end up in logs).
        headers = {"x-goog-api-key": key}
        timeout = httpx.Timeout(120.0, connect=10.0)

        finish_reason = None
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST",
                    f"/v1beta/models/{model}:streamGenerateContent",
                    params={"alt": "sse"},
                    json=body,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        await response.aread()
                        raise LLMError(self._error_message(response, model))

                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = json.loads(line[len("data:"):])
                        candidates = chunk.get("candidates") or []
                        if not candidates:
                            # No answer at all: Gemini blocked the question itself.
                            if chunk.get("promptFeedback", {}).get("blockReason"):
                                finish_reason = "SAFETY"
                            continue
                        for part in candidates[0].get("content", {}).get("parts", []):
                            if part.get("text") and not part.get("thought"):
                                yield part["text"]
                        finish_reason = candidates[0].get("finishReason") or finish_reason

        except httpx.ConnectError:
            raise LLMError("Could not reach Gemini. Check your internet.") from None
        except httpx.TimeoutException:
            raise LLMError("Gemini took too long to answer. Please try again.") from None

        if finish_reason == "MAX_TOKENS":
            yield "\n\n[Answer was cut off because it was too long.]"
        elif finish_reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
            yield "\n\nSorry, I can't help with that request."

    async def generate_json(self, system: str, user: str, schema: dict) -> str:
        """Structured output: Gemini replies with JSON that matches `schema` (no streaming)."""
        key = self.settings.gemini_api_key
        if not key:
            raise LLMError("No Gemini API key found. Add GEMINI_API_KEY to .env")

        model = self.settings.gemini_model
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": schema,
                "temperature": 0,  # same input -> (almost) same output
            },
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=httpx.Timeout(120.0, connect=10.0), transport=self.transport
            ) as client:
                # "Busy" (503) and "too many requests" (429) are usually short problems.
                # Wait a bit and try again: 2s, then 5s. This is called "retry with backoff".
                for wait in [2, 5, None]:
                    response = await client.post(
                        f"/v1beta/models/{model}:generateContent",
                        json=body,
                        headers={"x-goog-api-key": key},
                    )
                    if response.status_code not in (429, 503) or wait is None:
                        break
                    await asyncio.sleep(wait * self.retry_wait_scale)
        except httpx.ConnectError:
            raise LLMError("Could not reach Gemini. Check your internet.") from None
        except httpx.TimeoutException:
            raise LLMError("Gemini took too long to answer. Please try again.") from None

        if response.status_code != 200:
            raise LLMError(self._error_message(response, model))
        candidates = response.json().get("candidates") or []
        if not candidates:
            raise LLMError("Gemini declined to classify this text.")
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if not p.get("thought"))

    @staticmethod
    def _error_message(response: httpx.Response, model: str) -> str:
        """Turn Gemini's error into a simple message for the user."""
        status = response.status_code
        try:
            detail = response.json().get("error", {}).get("message", "")
        except ValueError:
            detail = ""
        if status == 429:
            return "Gemini free limit reached. Wait a minute and try again."
        if status in (401, 403) or "API key" in detail:
            return "Gemini login failed. Check GEMINI_API_KEY in .env"
        if status == 404:
            return f"Gemini model '{model}' not found. Check GEMINI_MODEL in .env"
        if status == 503:
            return "Gemini is busy right now. Try again soon, or use GEMINI_MODEL=gemini-flash-lite-latest"
        return f"Gemini returned an error ({status})."


# ---------------------------------------------------------------- Ollama (free, local)

class OllamaChatModel:
    """Free models running on your computer through Ollama (https://ollama.com).

    Ollama's chat API streams one JSON object per line, like:
      {"message": {"role": "assistant", "content": "Hel"}, "done": false}
      {"message": {"role": "assistant", "content": "lo"}, "done": false}
      {"done": true, "done_reason": "stop", ...}
    """

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport  # tests pass a fake transport here

    async def stream_answer(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        model = self.settings.ollama_model
        body = {
            "model": model,
            # Ollama takes the system prompt as the first message.
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": True,
        }
        # Big read timeout: the first request loads the model into memory, which can be slow.
        timeout = httpx.Timeout(300.0, connect=5.0)

        try:
            async with httpx.AsyncClient(
                base_url=self.settings.ollama_url, timeout=timeout, transport=self.transport
            ) as client:
                async with client.stream("POST", "/api/chat", json=body) as response:
                    if response.status_code == 404:
                        raise LLMError(f"Model '{model}' is not downloaded. Run:  ollama pull {model}")
                    if response.status_code != 200:
                        raise LLMError(f"Ollama returned an error ({response.status_code}).")

                    done_reason = None
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        if "error" in chunk:
                            raise LLMError(f"Ollama error: {chunk['error']}")
                        text = chunk.get("message", {}).get("content", "")
                        if text:
                            yield text
                        if chunk.get("done"):
                            done_reason = chunk.get("done_reason")
                            break

        except httpx.ConnectError:
            raise LLMError("Ollama is not running. Open the Ollama app, or run:  ollama serve") from None
        except httpx.TimeoutException:
            raise LLMError("Ollama took too long to answer. Try a smaller model.") from None

        if done_reason == "length":
            yield "\n\n[Answer was cut off because it was too long.]"

    async def generate_json(self, system: str, user: str, schema: dict) -> str:
        """Structured output: Ollama's `format` field forces JSON that matches `schema`."""
        model = self.settings.ollama_model
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "format": schema,
            "stream": False,
            "options": {"temperature": 0},  # same input -> (almost) same output
        }
        try:
            async with httpx.AsyncClient(
                base_url=self.settings.ollama_url,
                timeout=httpx.Timeout(300.0, connect=5.0),
                transport=self.transport,
            ) as client:
                response = await client.post("/api/chat", json=body)
        except httpx.ConnectError:
            raise LLMError("Ollama is not running. Open the Ollama app, or run:  ollama serve") from None
        except httpx.TimeoutException:
            raise LLMError("Ollama took too long to answer. Try a smaller model.") from None

        if response.status_code == 404:
            raise LLMError(f"Model '{model}' is not downloaded. Run:  ollama pull {model}")
        if response.status_code != 200:
            raise LLMError(f"Ollama returned an error ({response.status_code}).")
        return response.json().get("message", {}).get("content", "")


# ---------------------------------------------------------------- pick one

def create_chat_model(settings: Settings) -> ChatModel:
    """Return the model chosen by LLM_PROVIDER in .env."""
    if settings.llm_provider == "ollama":
        return OllamaChatModel(settings)
    if settings.llm_provider == "gemini":
        return GeminiChatModel(settings)
    return ClaudeChatModel(settings)
