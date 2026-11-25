"""Tests for the FastAPI lessons. Run:  pytest learn -v

Read these too - each test shows how to CALL a route from code.
"""

from fastapi.testclient import TestClient

from learn.fastapi_lessons import app, get_leave_policy

client = TestClient(app)


def test_lesson1_hello():
    res = client.get("/hello")
    assert res.status_code == 200
    assert res.json() == {"message": "Hello, FastAPI!"}


def test_lesson2_path_parameter():
    assert client.get("/hello/Suriya").json() == {"message": "Hello, Suriya!"}


def test_lesson3_query_parameter_filters():
    pending = client.get("/leaves", params={"status": "pending"}).json()
    assert all(l["status"] == "pending" for l in pending)


def test_lesson4_not_found_and_bad_type():
    assert client.get("/leaves/99").status_code == 404
    assert client.get("/leaves/abc").status_code == 422


def test_lesson5_create_and_validation():
    ok = client.post("/leaves", json={"employee": "Kavin", "type": "casual", "days": 3})
    assert ok.status_code == 201
    assert ok.json()["status"] == "pending"

    bad = client.post("/leaves", json={"employee": "Kavin", "type": "holiday", "days": 3})
    assert bad.status_code == 422


def test_lesson6_response_model_hides_fields():
    first = client.get("/leaves-summary").json()[0]
    assert set(first) == {"employee", "days"}


def test_lesson7_dependency_can_be_swapped():
    # Swap the real policy with a fake one - same trick OpsMind uses for the fake AI.
    app.dependency_overrides[get_leave_policy] = lambda: {"casual": 1, "sick": 0, "earned": 0}
    try:
        assert client.get("/balance/Nobody").json() == {"casual": 1, "sick": 0, "earned": 0}
    finally:
        app.dependency_overrides.clear()


def test_lesson8_streaming():
    assert client.get("/stream").text == "Your leave request is being processed..."
