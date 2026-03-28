# jobpilot — Project Context for Claude

## What This Project Is
An autonomous job search agent that automates two workflows:
1. **Startup Hunter** — finds recently funded Indian startups, checks if they're hiring for junior DS/ML roles, finds the hiring contact, drafts and sends cold emails
2. **Job Board Hunter** — searches LinkedIn, Naukri, Instahyre, Wellfound, Indeed for junior DS/ML roles in Bangalore/Gurgaon/Noida, scores them against the candidate's CV, applies, then finds and messages hiring managers on LinkedIn

## Candidate Profile
- Targeting: Junior Data Scientist / ML Engineer / AI Engineer roles
- Cities: Bangalore, Gurgaon, Noida
- Experience: fresher/junior level
- Stack: Python, ML, Deep Learning, NLP, PyTorch, TensorFlow, scikit-learn, SQL, pandas

## Architecture
```
main.py                  → entry point, runs the full agent loop
config.py                → all settings, preferences, API keys (from .env)
memory/db.py             → SQLite — tracks jobs, statuses, agent memory
modules/searcher.py      → Module 1: search job boards via Tavily
modules/scorer.py        → Module 2: score jobs against CV using Gemini API
modules/notifier.py      → Module 3: Telegram HITL (not built yet)
modules/applier.py       → Module 4: Playwright form filler (not built yet)
modules/outreach.py      → Module 5: LinkedIn message drafter (not built yet)
modules/tracker.py       → Module 6: Google Sheets logger (not built yet)
```

## Current Build Status
- [x] Project scaffold created
- [x] config.py — candidate profile + job board query templates
- [x] memory/db.py — SQLite with jobs + agent_memory tables
- [x] modules/searcher.py — Tavily-based multi-board job search
- [x] modules/scorer.py — Gemini-powered CV vs job scoring (returns score/10 + metadata)
- [x] main.py — wires search → score → save to DB
- [ ] Module 3: Telegram notifier + HITL approval loop
- [ ] Module 4: Playwright job applier
- [ ] Module 5: LinkedIn outreach drafter
- [ ] Module 6: Google Sheets tracker
- [ ] Startup Hunter workflow (separate from job board hunter)

## Key Design Decisions
- **SerpAPI** (misc_key) for web search via Google Search organic results
- **Gemini 2.0 Flash** (google_api_key) for all LLM calls (scoring, drafting, reasoning)
- **SQLite** for local memory/state — job lifecycle: seen → approved → rejected → applied → messaged
- **Telegram bot** for human-in-the-loop (HITL) — agent pauses and notifies, waits for approval
- **Playwright** for browser automation (form filling, LinkedIn)
- **Google Sheets** for tracking dashboard
- LinkedIn automation is kept human-in-the-loop to avoid account bans — agent drafts, user sends
- `.env` holds all secrets — never committed to git
- `cv/` folder holds resume.pdf — never committed to git

## Tech Stack
- Python 3.11+
- google-generativeai (Gemini 2.0 Flash)
- google-search-results (SerpAPI)
- langgraph (for agent graph, being introduced gradually)
- playwright
- gspread + google-auth
- python-telegram-bot
- PyPDF2
- sqlite3 (built-in)
- python-dotenv

## Key Files NOT in Repo (local only)
- `.env` — all API keys
- `cv/resume.pdf` — candidate's CV

## Conventions
- Each module is independently runnable for testing
- All LLM calls use structured JSON output — strip markdown fences before parsing
- DB is the source of truth for job status
- When in doubt, write to DB and notify via Telegram rather than auto-acting
- `agent_memory` table is a free-form key-value store for persistent agent state

## Next Immediate Step
Build `modules/notifier.py` — Telegram bot that:
1. Reads all `status = 'seen'` jobs from DB
2. Sends each to the user as a Telegram message with score + reason + URL
3. User replies approve/reject
4. Agent updates DB status and continues