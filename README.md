# 🧠 OpsMind - Multi-Industry Multimodal Agentic AI Platform

One AI platform for many industries. A company adds its files, and people ask
questions by typing, talking, or sending a photo. The AI answers from the files
(showing the source) and can do work like creating a ticket.

**Industries now:** 🛡️ Insurance · 🛒 E-commerce · 👔 HR
**Add a new industry:** add one YAML file in `industries/`. No code change.

---

## ▶️ How to run (Windows)

```powershell
cd d:\Source\opsmind
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

copy .env.example .env      # then open .env and add your ANTHROPIC_API_KEY
uvicorn app.main:app --reload
```

Open **http://localhost:8000**, choose an industry, and ask a question.

### 🆓 Use a free AI instead (Ollama)
1. Install Ollama from **https://ollama.com/download** and open it.
2. Download a small free model (about 2 GB, one time):
   ```powershell
   ollama pull llama3.2
   ```
3. In `.env`, set:
   ```
   LLM_PROVIDER=ollama
   ```
4. Restart the app. Now it uses the free model on your computer.

### ☁️ Use Gemini (free plan, in Google's cloud)
1. Get a free key at **https://aistudio.google.com/apikey** (sign in with Google).
2. In `.env`, set:
   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your-key
   ```
3. Restart the app. Now it uses Gemini.

The free plan has a limit (some questions per minute and per day). If you hit it, wait a minute.

Switch any time with `LLM_PROVIDER=claude`, `gemini`, or `ollama`.

API docs (auto-made by FastAPI): **http://localhost:8000/docs**

### Run tests
```powershell
pytest -v
```
Tests use a fake AI, so they need no API key and cost nothing.

### Run with Docker
```powershell
docker compose up --build
```

---

## 📁 Folder structure

```
opsmind/
├── app/
│   ├── main.py         # API routes (/api/chat, /api/industries)
│   ├── llm.py          # all AI calls go through here
│   ├── industries.py   # loads industry YAML files
│   └── config.py       # settings from .env
├── industries/         # one YAML file = one industry
├── data/               # sample company files per industry (used in Step 3)
├── static/index.html   # simple chat web page
├── tests/              # automatic tests
├── docs/decisions.md   # why you made each choice (interview gold!)
├── Dockerfile
└── docker-compose.yml
```

---

## 🗺️ Roadmap

- [x] **Step 1** - Chat app with streaming, 3 industries, tests, Docker
- [x] **Step 1.5** - Three AI providers: Claude (paid), Gemini (free plan, cloud), Ollama (free, local), switch in `.env`
- [x] **Step 2** - Good prompts + structured output (ticket classifier) - see below
- [ ] **Step 3** - RAG: AI reads company files (pgvector)
- [ ] **Step 4** - Better search: hybrid search, reranking, caching
- [ ] **Step 5** - Evals: test the AI and get a score ⭐
- [ ] **Step 6** - Agent: tools (create ticket, check status) + MCP
- [ ] **Step 7** - Multimodal: photos and voice
- [ ] **Step 8** - Fine-tune a small model
- [ ] **Step 9** - Model routing, safety, cost tracking, deploy online
- [ ] **Step 10** - Demo video, blog post

---

## 🏷️ Step 2 - Ticket classifier

Open **http://localhost:8000/classify**, paste a customer message, click **Classify**.
The AI returns a fixed format:
```json
{"category": "fraud", "priority": "urgent", "sentiment": "negative",
 "summary": "Customer reports an unknown Rs 15,000 debit.", "needs_human": true}
```

**Measure accuracy** on 24 labeled tickets:
```powershell
python -m scripts.eval_classifier                    # uses LLM_PROVIDER from .env
python -m scripts.eval_classifier --provider ollama  # compare another AI
```

| Prompt | AI | Category | Priority (exact) | Needs human | Valid JSON | Avg time |
|---|---|---|---|---|---|---|
| v1 | Gemini flash-lite | 83% | 62% | 79% | 83% | 1.5 s |
| **v2** | **Gemini flash-lite** | **92%** | **83%** | **96%** | **100%** | 3.0 s |
| v2 | Ollama llama3.2 (local) | 83% | 71% | 83% | 100% | 9.2 s |

What changed v1 → v2: auto-retry when Gemini is busy, and "decide priority by impact, not by how angry the customer sounds".
Details: [docs/decisions.md](docs/decisions.md) (006, 007).

| File | What it does |
|---|---|
| `prompts/classify_ticket.md` | The prompt (rules + examples) |
| `app/classifier.py` | Builds the prompt, JSON schema, checks the answer, retries |
| `app/llm.py` → `generate_json()` | Structured output for Claude, Gemini, Ollama |
| `industries/*.yaml` → `ticket_categories`, `ticket_examples` | Categories and few-shot examples per industry |
| `data/eval/tickets.jsonl` | 24 tickets with correct answers |
| `scripts/eval_classifier.py` | Measures accuracy |

---

## 📚 What you learn in Step 1

| Concept | Where to look |
|---|---|
| REST API with FastAPI | `app/main.py` |
| Input checking (Pydantic) | `ChatRequest`, `Message` in `app/main.py` |
| Calling an LLM | `app/llm.py` |
| Streaming answers | `stream_answer()` in `app/llm.py` + `ask()` in `static/index.html` |
| System prompt per industry | `industries/*.yaml` |
| Settings and secrets (.env) | `app/config.py`, `.env.example` |
| Error handling | `generate()` in `app/main.py` |
| Dependency injection + fake AI for tests | `get_chat_model` + `tests/test_api.py` |
| Docker | `Dockerfile` |

### ✅ Step 1 homework (do it yourself!)
1. Add a 4th industry: `industries/banking.yaml`. Check it appears in the web page.
2. Write a test that checks the banking industry is listed.
3. Change `LLM_EFFORT` in `.env` to `low` and `high`. Note the speed difference in `docs/decisions.md`.
4. Explain in your own words: what is a system prompt? what is streaming? why do tests use a fake AI?
