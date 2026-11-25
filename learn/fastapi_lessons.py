"""
🎓 FastAPI Lessons for Freshers
================================

A tiny "Leave Request" API, built in 8 small lessons.
This is a PRACTICE file. It does not touch the main OpsMind app.

HOW TO RUN (in the VS Code terminal):
    cd d:\\Source\\opsmind
    .venv\\Scripts\\activate
    uvicorn learn.fastapi_lessons:app --reload --port 8001

Then open:  http://localhost:8001/docs
(Port 8001, so it can run at the same time as OpsMind on 8000.)

Read each lesson from top to bottom. After each lesson, test it in /docs.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# =============================================================================
# LESSON 1 - Create the app and your first route
# =============================================================================
# `app` is your backend. Uvicorn looks for this variable.
app = FastAPI(title="Leave API - FastAPI Lessons")


# A ROUTE = an address + a function.
# @app.get("/hello")  means: "when someone does GET /hello, run this function".
# Whatever the function RETURNS is sent back as JSON.
@app.get("/hello")
def hello():
    return {"message": "Hello, FastAPI!"}

# ✅ TRY: open http://localhost:8001/hello
# ✏️ EXERCISE: add a route GET /about that returns {"app": "Leave API", "version": 1}


# =============================================================================
# LESSON 2 - Path parameter (a value INSIDE the address)
# =============================================================================
# {name} in the path is a placeholder. FastAPI gives its value to the function.
# The ": str" is a TYPE HINT. FastAPI uses it to check the input.
@app.get("/hello/{name}")
def hello_name(name: str):
    return {"message": f"Hello, {name}!"}

# ✅ TRY: http://localhost:8001/hello/Suriya   →  {"message": "Hello, Suriya!"}


# =============================================================================
# LESSON 3 - Fake database + query parameters (a value AFTER the "?")
# =============================================================================
# For practice we keep data in a Python list. (Real apps use a database.)
LEAVES: list[dict] = [
    {"id": 1, "employee": "Suriya", "type": "casual", "days": 2, "status": "approved"},
    {"id": 2, "employee": "Priya", "type": "sick", "days": 1, "status": "pending"},
    {"id": 3, "employee": "Arun", "type": "earned", "days": 5, "status": "pending"},
]


# A function argument that is NOT in the path becomes a QUERY parameter.
# "status: str | None = None" means: optional. If not given, it is None.
@app.get("/leaves")
def list_leaves(status: str | None = None):
    if status is None:
        return LEAVES
    return [leave for leave in LEAVES if leave["status"] == status]

# ✅ TRY: /leaves                    → all 3
# ✅ TRY: /leaves?status=pending     → only pending ones


# =============================================================================
# LESSON 4 - Get ONE item + errors with HTTPException
# =============================================================================
# "leave_id: int" → FastAPI converts "2" from the URL into the number 2.
# If someone sends /leaves/abc, FastAPI itself replies 422 (bad input).
@app.get("/leaves/{leave_id}")
def get_leave(leave_id: int):
    for leave in LEAVES:
        if leave["id"] == leave_id:
            return leave
    # Not found → stop and send an error with a status code.
    raise HTTPException(status_code=404, detail=f"Leave {leave_id} not found")

# ✅ TRY: /leaves/2    → 200, Priya's leave
# ✅ TRY: /leaves/99   → 404 "Leave 99 not found"
# ✅ TRY: /leaves/abc  → 422 (not a number)


# =============================================================================
# LESSON 5 - POST with a body + Pydantic validation
# =============================================================================
# A Pydantic MODEL describes the SHAPE of the data we accept.
# FastAPI checks every request against it. Bad data → 422 automatically.
class LeaveCreate(BaseModel):
    employee: str = Field(min_length=2, max_length=50)
    type: Literal["casual", "sick", "earned"]  # only these 3 words allowed
    days: int = Field(gt=0, le=30)             # gt = greater than, le = less or equal


# Because the argument type is a Pydantic model, FastAPI reads it from the JSON BODY.
# status_code=201 means "Created" (the normal code for "I made something new").
@app.post("/leaves", status_code=201)
def create_leave(new_leave: LeaveCreate):
    leave = {
        "id": max(l["id"] for l in LEAVES) + 1,
        **new_leave.model_dump(),  # turns the model into a dict
        "status": "pending",
    }
    LEAVES.append(leave)
    return leave

# ✅ TRY in /docs → POST /leaves → Try it out → body:
#     {"employee": "Kavin", "type": "casual", "days": 3}          → 201 ✅
#     {"employee": "Kavin", "type": "holiday", "days": 3}         → 422 (bad type)
#     {"employee": "Kavin", "type": "casual", "days": 0}          → 422 (days must be > 0)
# Then GET /leaves again - your new leave is there!


# =============================================================================
# LESSON 6 - Response model (control what goes OUT)
# =============================================================================
# Just like we check data coming IN, we can define the data going OUT.
# FastAPI removes extra fields and shows the shape in /docs.
class LeaveSummary(BaseModel):
    employee: str
    days: int


@app.get("/leaves-summary", response_model=list[LeaveSummary])
def leaves_summary():
    return LEAVES  # has id, type, status too... but only employee + days go out

# ✅ TRY: /leaves-summary → only "employee" and "days"


# =============================================================================
# LESSON 7 - Dependency injection with Depends
# =============================================================================
# A DEPENDENCY is a function that GIVES something to your route.
# FastAPI runs it first and passes the result in.
# Why? Share code (no copy-paste) and swap it in tests (e.g. a fake AI).
def get_leave_policy() -> dict:
    # In OpsMind, this is like get_industries() / get_chat_model().
    return {"casual": 12, "sick": 10, "earned": 15}


@app.get("/balance/{employee}")
def leave_balance(employee: str, policy: dict = Depends(get_leave_policy)):
    used: dict[str, int] = {"casual": 0, "sick": 0, "earned": 0}
    for leave in LEAVES:
        if leave["employee"].lower() == employee.lower() and leave["status"] == "approved":
            used[leave["type"]] += leave["days"]
    return {t: policy[t] - used[t] for t in policy}

# ✅ TRY: /balance/Suriya  → casual 10 left (12 - 2 approved)


# =============================================================================
# LESSON 8 - async + streaming (how OpsMind sends AI answers word by word)
# =============================================================================
# "async def" = this function can WAIT (for the AI, a database, the network)
# without blocking other users. While one request waits, others are served.
# "await" = "wait here, let others work meanwhile".
async def slow_words() -> AsyncIterator[str]:
    for word in ["Your ", "leave ", "request ", "is ", "being ", "processed..."]:
        await asyncio.sleep(0.5)  # pretend the AI is thinking
        yield word                # send this piece now


@app.get("/stream")
async def stream_demo():
    return StreamingResponse(slow_words(), media_type="text/plain")

# ✅ TRY: open http://localhost:8001/stream in the browser - words arrive one by one.
# This is EXACTLY how /api/chat in app/main.py streams the AI answer.


# =============================================================================
# 🏁 FINAL EXERCISES (do these yourself!)
# =============================================================================
# 1. Add GET /about (Lesson 1).
# 2. Add PUT /leaves/{leave_id}/approve → set status to "approved", 404 if not found.
# 3. Add DELETE /leaves/{leave_id} → remove it, 404 if not found.
# 4. In LeaveCreate, add an optional field: reason: str | None = None
# 5. Write a test in learn/test_fastapi_lessons.py for your /approve route.
