# Decision Log

Write down every important choice: what you chose, why, and what else you tried.
In interviews, this is your "experience".

---

## 001 - One platform, industry settings in YAML files
- **Date:** 2026-11-20
- **Choice:** Each industry is one YAML file in `industries/`. The main code is the same for all.
- **Why:** Adding a new industry needs no code change. Easy to test, easy to grow.
- **Other option:** Separate app per industry. Rejected: too much repeated code.

## 002 - Stream the answer
- **Choice:** The API sends the answer piece by piece (streaming).
- **Why:** The user sees text start in about 1 second instead of waiting for the full answer.

## 003 - Fake AI model in tests
- **Choice:** Tests replace the real AI with a fake one.
- **Why:** Tests run fast, free, and without an API key. Real AI quality is tested separately in Step 5 (evals).

## 004 - Support two AI providers: Claude and Ollama
- **Date:** 2026-11-21
- **Choice:** `LLM_PROVIDER` in `.env` picks Claude (paid) or Ollama (free, local).
  Both follow the same `ChatModel` shape, so the rest of the app does not care which one runs.
- **Why:** Practise for free with Ollama; use Claude for the best quality and the final demo.
  Also no lock-in to one company.
- **Other option:** LangChain to wrap both. Rejected for now: I want to understand the raw APIs first.

---

## Template
## 00X - Title
- **Date:**
- **Choice:**
- **Why:**
- **Other option tried:**
- **Result / numbers:**
