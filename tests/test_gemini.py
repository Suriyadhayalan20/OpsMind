"""Gemini tests. They use a fake Gemini server, so no API key or internet is needed."""

import asyncio
import json

import httpx

from app.config import Settings
from app.llm import GeminiChatModel, LLMError, create_chat_model


def collect(model: GeminiChatModel, system: str = "Be nice", messages: list | None = None) -> str:
    """Run the async stream and join all the pieces into one string."""
    messages = messages or [{"role": "user", "content": "Hi"}]

    async def run() -> str:
        return "".join([piece async for piece in model.stream_answer(system, messages)])

    return asyncio.run(run())


def fake_gemini(chunks: list[dict], status: int = 200, seen: dict | None = None) -> httpx.MockTransport:
    """A fake Gemini server that replies with the given chunks in SSE format ("data: {...}")."""

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["path"] = request.url.path
            seen["params"] = dict(request.url.params)
            seen["headers"] = request.headers
            seen["body"] = json.loads(request.content)
        if status != 200:
            return httpx.Response(status, json=chunks[0])
        body = "\n\n".join("data: " + json.dumps(c) for c in chunks)
        return httpx.Response(200, text=body)

    return httpx.MockTransport(handler)


def text_chunk(text: str, finish: str | None = None) -> dict:
    candidate = {"content": {"role": "model", "parts": [{"text": text}]}}
    if finish:
        candidate["finishReason"] = finish
    return {"candidates": [candidate]}


def gemini(transport: httpx.MockTransport, **kw) -> GeminiChatModel:
    return GeminiChatModel(Settings(gemini_api_key="test-key", gemini_model="gemini-test", **kw), transport=transport)


def test_streams_answer_and_sends_request_in_gemini_format():
    seen: dict = {}
    model = gemini(fake_gemini([text_chunk("Hello "), text_chunk("there", "STOP")], seen=seen))
    messages = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "How are you?"},
    ]

    assert collect(model, messages=messages) == "Hello there"
    assert seen["path"] == "/v1beta/models/gemini-test:streamGenerateContent"
    assert seen["params"] == {"alt": "sse"}
    # Key is sent in a header, not in the URL.
    assert seen["headers"]["x-goog-api-key"] == "test-key"
    assert seen["body"]["systemInstruction"] == {"parts": [{"text": "Be nice"}]}
    # "assistant" becomes "model" for Gemini.
    assert [c["role"] for c in seen["body"]["contents"]] == ["user", "model", "user"]
    assert seen["body"]["contents"][2]["parts"] == [{"text": "How are you?"}]


def test_no_api_key_gives_clear_message():
    model = GeminiChatModel(Settings(gemini_api_key=None), transport=fake_gemini([]))
    try:
        collect(model)
        raise AssertionError("expected LLMError")
    except LLMError as e:
        assert "GEMINI_API_KEY" in e.user_message


def test_wrong_key_gives_login_message():
    error = {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}
    model = gemini(fake_gemini([error], status=400))
    try:
        collect(model)
        raise AssertionError("expected LLMError")
    except LLMError as e:
        assert "login failed" in e.user_message


def test_free_limit_gives_wait_message():
    model = gemini(fake_gemini([{"error": {"code": 429, "message": "Quota exceeded"}}], status=429))
    try:
        collect(model)
        raise AssertionError("expected LLMError")
    except LLMError as e:
        assert "limit" in e.user_message


def test_cut_off_answer_adds_note():
    model = gemini(fake_gemini([text_chunk("Long", "MAX_TOKENS")]))
    assert "cut off" in collect(model)


def test_blocked_question_says_sorry():
    model = gemini(fake_gemini([{"promptFeedback": {"blockReason": "SAFETY"}}]))
    assert "can't help" in collect(model)


def test_provider_switch_to_gemini():
    assert isinstance(create_chat_model(Settings(llm_provider="gemini")), GeminiChatModel)
