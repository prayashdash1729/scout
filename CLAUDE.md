# jobpilot — Project Context for Claude

## What This Project Is
A multi-user, Telegram-driven job-hunting agent. A user onboards by chatting
with the bot (name, CV upload, target roles/cities, experience); the bot
extracts skills from the CV and suggests roles. On `/hunt`, the bot searches job
boards, renders each page, scores it against the user's CV with Gemini, dedups
against the DB, and pushes new matches as Telegram approval cards
(Persist / Discard). Profiles + jobs persist in Postgres across restarts.

> The pre-v1 one-shot pipeline (root `main.py`/`config.py`, `modules/`,
> `memory/db.py`, `test_modules.py`) has been **removed** — all logic now lives
> in the `app/` package.

## Architecture (`app/` package)
```
app/__main__.py          → `python -m app` → starts the bot (Docker CMD)
app/config.py            → Settings (Pydantic) loaded/validated from .env
app/enums.py             → JobStatus, JobSource, ConvState
app/schemas.py           → Pydantic: CVInsights, JobEvaluation (Gemini I/O), JobCandidate
app/logging_conf.py      → logging setup

app/db/base.py           → async engine + session (SQLAlchemy 2.0 + asyncpg), init_models()
app/db/models.py         → ORM: User (PK = telegram id), Job (unique per user_id+job_key)
app/db/repo.py           → all async DB access (upsert, dedup, rate-limit, status)

app/services/gemini.py   → google.genai structured-output helper (Pydantic response_schema; 429 backoff)
app/services/cv.py       → PDF text extract (PyPDF2) + CV→skills/roles via Gemini
app/services/fetch.py    → shared HTTP getter: direct → ScraperAPI fallback (cloud egress)
app/services/linkedin.py → LinkedIn guest jobs API: search (filters+pagination) + JD fetch
app/services/naukri.py   → Naukri source (DISABLED — anti-bot blocks all no-login paths)
app/services/jina.py     → Google/Jina search (s.jina.ai) + read (r.jina.ai)
app/services/sources.py  → SourceAdapter registry (linkedin/naukri/jina); resolve(user) selection
app/services/scorer.py   → score a page vs CV → JobEvaluation
app/services/hunt.py     → multi-source orchestration: gather→dedup→fetch JD→score→persist

app/bot/app.py           → builds Application, registers handlers, run_polling
app/bot/access.py        → allowlist gate (ALLOWED_TELEGRAM_IDS)
app/bot/onboarding.py    → /start ConversationHandler (name→CV→roles→cities→exp)
app/bot/profile.py       → /me, /setroles, /setcities, /setexp, /setname, /editcv, /help
app/bot/hunt_cmd.py      → /hunt (rate-limited; optional one-off source override `/hunt linkedin`)
app/bot/sources_cmd.py   → /sources (per-user source selection via toggle buttons)
app/bot/approval.py      → Persist/Discard inline-button callbacks
app/bot/keyboards.py     → inline keyboards + callback_data tokens
app/bot/texts.py         → user-facing message templates

Dockerfile, docker-compose.yml → bot + Postgres (named volume `pgdata`), local run
```

## Candidate Profile (default test user)
- Targeting: Junior Data Scientist / ML / AI Engineer roles
- Cities: Bangalore, Gurgaon, Noida, Pune
- Experience: fresher/junior; Stack: Python, ML/DL, NLP, PyTorch, TF, SQL, pandas, LangGraph

## Current Build Status
- [x] Telegram onboarding (CV upload + Gemini skill/role extraction)
- [x] Multi-user profiles in Postgres; `/start` returns existing profile
- [x] Profile-edit commands (`/setroles`, `/setcities`, `/setexp`, `/setname`, `/editcv`)
- [x] `/hunt`: Jina search → Jina reader → Gemini scoring → dedup → approval cards
- [x] Persist/Discard approval loop updates job status (so jobs aren't re-shown)
- [x] Access allowlist + per-user hunt cooldown/daily-cap + per-hunt link ceiling
- [x] Pluggable source registry (`services/sources.py`); per-user selection via
      `/sources` (User.enabled_sources) + one-off `/hunt <names>` override
- [x] Docker Compose (bot + Postgres with persistent volume)
- [ ] Auto-apply (Playwright) — future
- [ ] LinkedIn outreach drafting — future
- [ ] Startup Hunter workflow — future

## Key Design Decisions
- **google.genai + GEMINI_API_KEY** for all LLM calls. Structured output via
  Pydantic `response_schema` — no markdown-fence stripping. Model: gemini-2.0-flash.
- **Job sources** (pluggable): **LinkedIn guest API** is primary — the
  `seeMoreJobPostings/search` endpoint (no login) returns fresh, filtered cards
  (f_TPR/f_E/f_JT) with a stable job id → `job_key='linkedin|<id>'`, so board jobs
  dedup before any LLM spend. **Jina/Google** (`s.jina.ai` + `r.jina.ai`) is a
  supplementary keyword source. **Naukri** is coded but DISABLED (406 recaptcha
  direct; ScraperAPI refuses it as a protected domain).
- **ScraperAPI** (`app/services/fetch.py`) is the egress fallback: direct fetch
  first, then proxy on block/failure — essential once deployed (cloud IPs get
  blocked by LinkedIn). Configured via `SCRAPER_API_KEY`.
- **Vertex quota**: `gemini-2.5-flash` 429s easily; the scorer retries with
  exponential backoff and `HUNT_CONCURRENCY` defaults to 3.
- **Postgres** (async SQLAlchemy + asyncpg) is the source of truth. Named Docker
  volume `pgdata` => data survives restarts/rebuilds.
- **Job lifecycle**: pending → persisted | discarded. Dedup key = `companyslug|jobid`
  (`job_key`), unique per user.
- **HITL**: the bot surfaces jobs as inline Persist/Discard cards; nothing is
  auto-applied. Long-polling => no public URL/ports needed (runs locally in Docker).
- **Abuse control**: optional `ALLOWED_TELEGRAM_IDS` allowlist (empty = open),
  per-user cooldown + daily cap, and `MAX_LINKS_PER_HUNT` ceiling.
- `.env` holds all secrets; `cv/` resumes — never committed.

## Tech Stack
- Python 3.12
- python-telegram-bot 22.x (async)
- google-genai (Gemini 2.0 Flash, structured output)
- Jina (search + reader) over httpx
- SQLAlchemy 2.0 (async) + asyncpg + Postgres 16
- Pydantic v2, PyPDF2, python-dotenv
- Docker + Docker Compose

## Key Files NOT in Repo (local only)
- `.env` — all API keys (see `.env.example` for the required new keys)
- `cv/*.pdf` — resumes

## Conventions
- All LLM calls use Gemini structured output (Pydantic `response_schema`).
- All DB access goes through `app/db/repo.py`; never open sessions elsewhere.
- Blocking work (genai SDK, PyPDF2) is wrapped in `asyncio.to_thread`; Jina/DB are async.
- Postgres is the source of truth for profiles and job status.

## Running
- Local Docker: fill the new keys in `.env` (see `.env.example`), then
  `docker compose up -d --build`. Stop the bot with `docker compose stop bot`.
- Requires a valid `GEMINI_API_KEY` (the previous key expired) and `JINA_API_KEY`.
