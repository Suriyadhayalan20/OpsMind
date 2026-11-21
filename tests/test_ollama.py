"""Ollama tests. They use a fake Ollama server, so Ollama does not need to be installed."""

import asyncio
import json

import httpx

from app.config import Settings
from app.llm import ClaudeChatModel, LLMError, OllamaChatModel, create_chat_model


def collect(model: OllamaChatModel, system: str = "Be nice", messages: list | None = None) -> str:
    """Run the async stream and join all the pieces into one string."""
    messages = messages or [{"role": "user", "content": "Hi"}]

    async def run() -> str:
        return "".join([piece async for piece in model.stream_answer(system, messages)])

    return asyncio.run(run())


def fake_ollama(lines: list[dict], status: int = 200, seen: dict | None = None) -> httpx.MockTransport:
    """A fake Ollama server that replies with the given JSON lines."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["path"] = request.url.path
            seen["body"] = json.loads(request.content)
        body = "\n".join(json.dumps(line) for line in lines)
        return httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


def test_streams_answer_and_sends_system_prompt_first():
    seen: dict = {}
    transport = fake_ollama(
        [
            {"message": {"role": "assistant", "content": "Hello "}, "done": False},
            {"message": {"role": "assistant", "content": "there"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
        ],
        seen=seen,
    )
    model = OllamaChatModel(Settings(ollama_model="llama3.2"), transport=transport)

    assert collect(model) == "Hello there"
    assert seen["path"] == "/api/chat"
    assert seen["body"]["model"] == "llama3.2"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "Be nice"}
    assert seen["body"]["messages"][1] == {"role": "user", "content": "Hi"}


def test_model_not_downloaded_gives_pull_hint():
    transport = fake_ollama([{"error": "model not found"}], status=404)
    model = OllamaChatModel(Settings(ollama_model="llama3.2"), transport=transport)
    try:
        collect(model)
        raise AssertionError("expected LLMError")
    except LLMError as e:
        assert "ollama pull llama3.2" in e.user_message


def test_ollama_not_running_gives_clear_message():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    model = OllamaChatModel(Settings(), transport=httpx.MockTransport(handler))
    try:
        collect(model)
        raise AssertionError("expected LLMError")
    except LLMError as e:
        assert "not running" in e.user_message


def test_cut_off_answer_adds_note():
    transport = fake_ollama([{"message": {"content": "Long"}, "done": True, "done_reason": "length"}])
    model = OllamaChatModel(Settings(), transport=transport)
    assert "cut off" in collect(model)


def test_provider_switch():
    assert isinstance(create_chat_model(Settings(llm_provider="ollama")), OllamaChatModel)
    assert isinstance(create_chat_model(Settings(llm_provider="claude")), ClaudeChatModel)
