"""Step 2: Ticket classifier (prompt engineering + structured output).

A customer writes a ticket (complaint or question). The AI returns a FIXED format:
    {"category": "...", "priority": "...", "sentiment": "...", "summary": "...", "needs_human": true/false}

Three layers of safety, so we always get clean data:
1. Prompt   - clear rules + examples tell the AI what we want   (prompts/classify_ticket.md)
2. Schema   - the AI API is told the exact JSON shape            (ticket_schema)
3. Pydantic - our code checks the answer; if bad, ask once more  (classify_ticket)
"""

import json
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from app.config import BASE_DIR
from app.industries import Industry
from app.llm import ChatModel

PROMPT_FILE: Path = BASE_DIR / "prompts" / "classify_ticket.md"

Priority = Literal["low", "medium", "high", "urgent"]
Sentiment = Literal["positive", "neutral", "negative"]
PRIORITIES = ["low", "medium", "high", "urgent"]
SENTIMENTS = ["positive", "neutral", "negative"]


class TicketResult(BaseModel):
    category: str
    priority: Priority
    sentiment: Sentiment
    summary: str = Field(min_length=1, max_length=300)
    needs_human: bool


class ClassifyResponse(BaseModel):
    """What the API sends back: the result + some facts about how it was made."""

    result: TicketResult
    provider: str
    attempts: int
    latency_ms: int


class ClassificationError(Exception):
    """The AI did not give a valid answer, even after a retry."""


def categories_for(industry: Industry) -> list[str]:
    return [*industry.ticket_categories.keys(), "other"]


def ticket_schema(industry: Industry) -> dict:
    """The exact JSON shape we want. `enum` = only these values are allowed."""
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": categories_for(industry)},
            "priority": {"type": "string", "enum": PRIORITIES},
            "sentiment": {"type": "string", "enum": SENTIMENTS},
            "summary": {"type": "string"},
            "needs_human": {"type": "boolean"},
        },
        "required": ["category", "priority", "sentiment", "summary", "needs_human"],
        "additionalProperties": False,
    }


def build_system_prompt(industry: Industry) -> str:
    """Fill the prompt template with this industry's categories and examples (few-shot)."""
    categories = "\n".join(f"- {name}: {desc}" for name, desc in industry.ticket_categories.items())
    examples = "\n\n".join(
        f"<ticket>{ex['text']}</ticket>\n{json.dumps(ex['result'])}" for ex in industry.ticket_examples
    )
    template = PROMPT_FILE.read_text(encoding="utf-8")
    return (
        template.replace("{{industry_name}}", industry.name)
        .replace("{{categories}}", categories)
        .replace("{{examples}}", examples or "(none)")
    )


def parse_result(raw: str, industry: Industry) -> TicketResult:
    """Check the AI's answer. Raises ValueError if anything is wrong."""
    data = json.loads(raw)  # bad JSON -> json.JSONDecodeError (a ValueError)
    result = TicketResult(**data)  # wrong fields/values -> ValidationError (a ValueError)
    if result.category not in categories_for(industry):
        raise ValueError(f"category '{result.category}' is not one of {categories_for(industry)}")
    return result


async def classify_ticket(
    model: ChatModel, industry: Industry, text: str, provider: str = "unknown", max_attempts: int = 2
) -> ClassifyResponse:
    system = build_system_prompt(industry)
    schema = ticket_schema(industry)
    user = f"<ticket>\n{text}\n</ticket>"

    start = time.perf_counter()
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        prompt = user
        if last_error:
            # Retry with feedback: tell the AI what was wrong last time.
            prompt += f"\n\nYour previous answer was invalid: {last_error}\nReply again with JSON that matches the schema exactly."
        raw = await model.generate_json(system, prompt, schema)
        try:
            result = parse_result(raw, industry)
        except (ValueError, ValidationError) as e:
            last_error = str(e)[:300]
            continue
        latency = int((time.perf_counter() - start) * 1000)
        return ClassifyResponse(result=result, provider=provider, attempts=attempt, latency_ms=latency)

    raise ClassificationError(f"The AI did not return a valid result after {max_attempts} tries: {last_error}")
