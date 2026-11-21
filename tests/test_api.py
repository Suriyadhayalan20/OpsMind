"""API tests. They use a fake AI model, so they run without an API key and cost nothing."""

from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from app.main import app, get_chat_model


class FakeChatModel:
    def __init__(self):
        self.last_system = None
        self.last_messages = None

    async def stream_answer(self, system: str, messages: list[dict]) -> AsyncIterator[str]:
        self.last_system = system
        self.last_messages = messages
        for piece in ["Hello ", "from ", "fake AI"]:
            yield piece


fake = FakeChatModel()
app.dependency_overrides[get_chat_model] = lambda: fake
client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_home_page_loads():
    res = client.get("/")
    assert res.status_code == 200
    assert "OpsMind" in res.text


def test_lists_all_industries():
    ids = {i["id"] for i in client.get("/api/industries").json()}
    assert {"insurance", "ecommerce", "hr", "banking"} <= ids


def test_chat_streams_answer_and_uses_industry_prompt():
    res = client.post(
        "/api/chat",
        json={"industry_id": "insurance", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert res.status_code == 200
    assert res.text == "Hello from fake AI"
    assert "insurance" in fake.last_system.lower()
    assert fake.last_messages == [{"role": "user", "content": "Hi"}]


def test_unknown_industry_returns_404():
    res = client.post(
        "/api/chat",
        json={"industry_id": "space", "messages": [{"role": "user", "content": "Hi"}]},
    )
    assert res.status_code == 404


def test_last_message_must_be_from_user():
    res = client.post(
        "/api/chat",
        json={"industry_id": "hr", "messages": [{"role": "assistant", "content": "Hi"}]},
    )
    assert res.status_code == 422


def test_too_long_message_is_rejected():
    res = client.post(
        "/api/chat",
        json={"industry_id": "hr", "messages": [{"role": "user", "content": "a" * 9000}]},
    )
    assert res.status_code == 422
