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

Switch back to Claude any time with `LLM_PROVIDER=claude`.

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
- [x] **Step 1.5** - Two AI providers: Claude (paid) or Ollama (free), switch in `.env`
- [ ] **Step 2** - Good prompts + structured output (ticket classifier)
- [ ] **Step 3** - RAG: AI reads company files (pgvector)
- [ ] **Step 4** - Better search: hybrid search, reranking, caching
- [ ] **Step 5** - Evals: test the AI and get a score ⭐
- [ ] **Step 6** - Agent: tools (create ticket, check status) + MCP
- [ ] **Step 7** - Multimodal: photos and voice
- [ ] **Step 8** - Fine-tune a small model
- [ ] **Step 9** - Model routing, safety, cost tracking, deploy online
- [ ] **Step 10** - Demo video, blog post

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
