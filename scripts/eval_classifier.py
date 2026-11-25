"""Measure how good the ticket classifier is.

Runs every ticket in data/eval/tickets.jsonl through the real AI and compares
the answer with the correct label.

Run (from d:\\Source\\opsmind, with .venv active):
    python -m scripts.eval_classifier                     # uses LLM_PROVIDER from .env
    python -m scripts.eval_classifier --provider ollama   # try another AI
    python -m scripts.eval_classifier --limit 5           # quick test with 5 tickets

The free Gemini plan allows only a few requests per minute, so we wait
--delay seconds between tickets.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime

from app.classifier import ClassificationError, classify_ticket
from app.config import BASE_DIR, Settings
from app.industries import load_industries
from app.llm import LLMError, create_chat_model

EVAL_FILE = BASE_DIR / "data" / "eval" / "tickets.jsonl"
RESULTS_DIR = BASE_DIR / "eval_results"
PRIORITY_ORDER = ["low", "medium", "high", "urgent"]


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # so Windows can print ✅ ❌
    parser = argparse.ArgumentParser(description="Evaluate the ticket classifier")
    parser.add_argument("--provider", choices=["claude", "gemini", "ollama"], help="override LLM_PROVIDER")
    parser.add_argument("--limit", type=int, help="only run the first N tickets")
    parser.add_argument("--delay", type=float, default=4.0, help="seconds to wait between tickets")
    args = parser.parse_args()

    settings = Settings(llm_provider=args.provider) if args.provider else Settings()
    model = create_chat_model(settings)
    industries = load_industries(settings.industries_dir)
    tickets = [json.loads(line) for line in EVAL_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        tickets = tickets[: args.limit]

    model_name = {"claude": settings.llm_model, "gemini": settings.gemini_model, "ollama": settings.ollama_model}[
        settings.llm_provider
    ]
    print(f"\nEvaluating {len(tickets)} tickets with {settings.llm_provider} ({model_name})\n")

    rows = []
    for i, t in enumerate(tickets, 1):
        if i > 1:
            await asyncio.sleep(args.delay)
        start = time.perf_counter()
        try:
            res = await classify_ticket(model, industries[t["industry"]], t["text"], settings.llm_provider)
            got = res.result.model_dump()
            ok = True
            attempts = res.attempts
        except (LLMError, ClassificationError) as e:
            got = {"error": getattr(e, "user_message", str(e))}
            ok = False
            attempts = 0
        latency = int((time.perf_counter() - start) * 1000)

        row = {
            **t,
            "got": got,
            "valid": ok,
            "attempts": attempts,
            "latency_ms": latency,
            "category_ok": ok and got["category"] == t["category"],
            "priority_ok": ok and got["priority"] == t["priority"],
            "priority_close": ok
            and abs(PRIORITY_ORDER.index(got["priority"]) - PRIORITY_ORDER.index(t["priority"])) <= 1,
            "human_ok": ok and got["needs_human"] == t["needs_human"],
        }
        rows.append(row)
        mark = "✅" if row["category_ok"] and row["priority_ok"] else ("❌" if not ok else "⚠️")
        print(f"{mark} {i:>2}. [{t['industry']}] {t['text'][:60]}")
        if ok and not (row["category_ok"] and row["priority_ok"]):
            print(f"      expected {t['category']}/{t['priority']}, got {got['category']}/{got['priority']}")
        if not ok:
            print(f"      error: {got['error']}")

    n = len(rows)
    valid = [r for r in rows if r["valid"]]
    summary = {
        "provider": settings.llm_provider,
        "model": model_name,
        "tickets": n,
        "errors": n - len(valid),
        "valid_json": pct(len(valid), n),
        "category_accuracy": pct(sum(r["category_ok"] for r in rows), n),
        "priority_exact": pct(sum(r["priority_ok"] for r in rows), n),
        "priority_within_one": pct(sum(r["priority_close"] for r in rows), n),
        "needs_human_accuracy": pct(sum(r["human_ok"] for r in rows), n),
        "retries_needed": sum(1 for r in valid if r["attempts"] > 1),
        "avg_latency_ms": int(sum(r["latency_ms"] for r in valid) / len(valid)) if valid else 0,
    }

    print("\n=========== RESULT ===========")
    for key, value in summary.items():
        print(f"{key:<22} {value}")

    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"classifier_{settings.llm_provider}_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved details to {out.relative_to(BASE_DIR)}")


if __name__ == "__main__":
    asyncio.run(main())
