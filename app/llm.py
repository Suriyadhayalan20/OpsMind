"""Talking to the LLM.

All LLM calls go through this one file. Two providers are supported:
- "claude": Claude API by Anthropic (paid, strongest answers)
- "ollama": free open-source models running on your own computer

Switch with one line in .env:  LLM_PROVIDER=claude  or  LLM_PROVIDER=ollama

Later steps add more here:
- Step 3: send retrieved document chunks with the question (RAG)
- Step 6: tools (agent)
- Step 7: images and voice
- Step 9: use a cheap model for easy questions, a strong model for hard ones
"""

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
    """Anything that can stream an answer. Claude, Ollama, and the fake model in tests all follow this."""

    def stream_answer(self, system: str, messages: list[dict]) -> AsyncIterator[str]: ...


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


# ---------------------------------------------------------------- pick one

def create_chat_model(settings: Settings) -> ChatModel:
    """Return the model chosen by LLM_PROVIDER in .env."""
    if settings.llm_provider == "ollama":
        return OllamaChatModel(settings)
    return ClaudeChatModel(settings)
