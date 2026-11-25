"""OpsMind API - the main entry point.

Run:  uvicorn app.main:app --reload
Open: http://localhost:8000
"""

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Literal

import anthropic
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from app.classifier import ClassificationError, ClassifyResponse, classify_ticket
from app.config import BASE_DIR, settings
from app.industries import Industry, load_industries
from app.llm import ChatModel, LLMError, create_chat_model

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("opsmind")

app = FastAPI(title="OpsMind", version="0.1.0", description="Multi-industry AI assistant")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


# ---------- Dependencies (easy to swap in tests) ----------

@lru_cache
def get_industries() -> dict[str, Industry]:
    return load_industries(settings.industries_dir)


@lru_cache
def get_chat_model() -> ChatModel:
    log.info("Using LLM provider: %s", settings.llm_provider)
    return create_chat_model(settings)


# ---------- Request models (input checking) ----------

class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def not_too_long(cls, v: str) -> str:
        if len(v) > settings.max_message_chars:
            raise ValueError(f"Message is longer than {settings.max_message_chars} characters")
        return v


class ChatRequest(BaseModel):
    industry_id: str
    messages: list[Message] = Field(min_length=1, max_length=50)

    @field_validator("messages")
    @classmethod
    def last_is_user(cls, v: list[Message]) -> list[Message]:
        if v[-1].role != "user":
            raise ValueError("The last message must be from the user")
        return v


# ---------- Routes ----------

@app.get("/")
def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/classify")
def classify_page() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "classify.html")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/industries")
def list_industries(industries: dict[str, Industry] = Depends(get_industries)) -> list[dict]:
    return [
        {
            "id": i.id,
            "name": i.name,
            "icon": i.icon,
            "description": i.description,
            "sample_questions": i.sample_questions,
        }
        for i in industries.values()
    ]


@app.post("/api/chat")
async def chat(
    req: ChatRequest,
    industries: dict[str, Industry] = Depends(get_industries),
    model: ChatModel = Depends(get_chat_model),
) -> StreamingResponse:
    industry = industries.get(req.industry_id)
    if industry is None:
        raise HTTPException(status_code=404, detail=f"Unknown industry '{req.industry_id}'")

    messages = [m.model_dump() for m in req.messages]
    log.info("chat industry=%s turns=%d", industry.id, len(messages))

    async def generate() -> AsyncIterator[str]:
        try:
            async for piece in model.stream_answer(industry.system_prompt, messages):
                yield piece
        # Most specific errors first, so each gets a clear message.
        except LLMError as e:
            log.error("LLM error: %s", e.user_message)
            yield f"\n[Error: {e.user_message}]"
        except anthropic.AuthenticationError:
            log.error("LLM auth failed - check ANTHROPIC_API_KEY")
            yield "\n[Error: AI service login failed. Check the API key in .env]"
        except anthropic.RateLimitError:
            log.warning("LLM rate limited")
            yield "\n[Error: Too many requests. Please wait a moment and try again.]"
        except anthropic.APIStatusError as e:
            log.error("LLM API error status=%s", e.status_code)
            yield f"\n[Error: AI service returned an error ({e.status_code}).]"
        except anthropic.APIConnectionError:
            log.error("LLM connection failed")
            yield "\n[Error: Could not reach the AI service. Check your internet.]"
        except TypeError as e:
            # The SDK raises this when no API key / login is found at all.
            log.error("LLM client setup failed: %s", e)
            yield "\n[Error: No API key found. Add ANTHROPIC_API_KEY to .env]"
        except Exception:
            # Last safety net: log the full error for us, show a simple message to the user.
            log.exception("Unexpected error while answering")
            yield "\n[Error: Something went wrong. Please try again.]"

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")


# ---------- Step 2: ticket classifier ----------

class ClassifyRequest(BaseModel):
    industry_id: str
    text: str = Field(min_length=3, max_length=5000)


@app.post("/api/classify", response_model=ClassifyResponse)
async def classify(
    req: ClassifyRequest,
    industries: dict[str, Industry] = Depends(get_industries),
    model: ChatModel = Depends(get_chat_model),
) -> ClassifyResponse:
    industry = industries.get(req.industry_id)
    if industry is None:
        raise HTTPException(status_code=404, detail=f"Unknown industry '{req.industry_id}'")
    if not industry.ticket_categories:
        raise HTTPException(status_code=400, detail=f"Industry '{industry.id}' has no ticket_categories")

    try:
        response = await classify_ticket(model, industry, req.text, provider=settings.llm_provider)
    # 502 = "the service behind me (the AI) failed", not our app.
    except LLMError as e:
        raise HTTPException(status_code=502, detail=e.user_message) from None
    except ClassificationError as e:
        log.warning("classify failed: %s", e)
        raise HTTPException(status_code=502, detail="The AI gave an invalid answer. Please try again.") from None
    except anthropic.AuthenticationError:
        raise HTTPException(status_code=502, detail="AI service login failed. Check the API key in .env") from None
    except anthropic.APIError:
        raise HTTPException(status_code=502, detail="AI service returned an error. Please try again.") from None
    except TypeError:
        raise HTTPException(status_code=502, detail="No API key found. Add it to .env") from None

    r = response.result
    log.info(
        "classify industry=%s category=%s priority=%s attempts=%d latency_ms=%d",
        industry.id, r.category, r.priority, response.attempts, response.latency_ms,
    )
    return response
