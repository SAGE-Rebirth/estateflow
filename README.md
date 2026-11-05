# EstateFlow

A multi-tenant CRM for brokers, resellers and real estate firms, with a WhatsApp assistant
that answers buyers from your own listings and brochures and books site visits straight onto
your calendar.

**How it flows**

1. The firm adds properties (photos, price, brochures) in the dashboard.
2. Buyers find them on the public marketplace (home page, search with filters, listing
   pages, like a property portal) and tap **Chat on WhatsApp**. The message carries the
   listing's ref code (e.g. `PR-1003`), so the right seller's assistant knows which home
   they mean.
3. The assistant (RAG over listings + uploaded PDFs/DOCX) answers questions, saves the
   buyer's budget and preferences, offers free slots and books the visit in-chat.
4. The booking lands on the **Today** day sheet and calendar, the agent gets a notification,
   the buyer gets WhatsApp confirmations and reminders.
5. When the buyer wants a human (negotiation, complaints, anything the data can't answer),
   the assistant hands over and the team replies from the inbox.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and decisions.

## Stack

| | |
|---|---|
| API | FastAPI (async PyMongo), Python 3.12 |
| Data | MongoDB Atlas (Vector Search for RAG, transactions for double-booking safety), Redis |
| Jobs | arq workers: document ingestion, WhatsApp replies, reminders, daily digest |
| AI | Hugging Face Inference Providers for everything: chat with tool calling (Qwen3 by default), embeddings (all-MiniLM-L6-v2), voice notes (Whisper), buyer photos (Qwen2.5-VL). Claude optional for chat. LangChain text splitters. |
| WhatsApp | Meta Cloud API, signed webhooks, media in and out, template fallback outside the 24h window |
| Web | Next.js 15, Tailwind 4, TanStack Query, FullCalendar; httpOnly-cookie sessions |

## Getting started

### 1. Prerequisites (once per machine)

| Tool | What it's for | Install (macOS) |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | Python package manager for `backend/`. Also installs Python 3.12 for you. | `brew install uv` |
| [Node.js](https://nodejs.org) (includes npm) | Package manager and runtime for `frontend/` | `brew install node` |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Runs Redis (and an optional local MongoDB) | download the app |
| make | Runs the shortcuts in the `Makefile` | preinstalled on macOS (`xcode-select --install` if missing) |

You also need a **MongoDB Atlas** cluster (the free tier works) and a **Hugging Face**
account with Inference Providers credits (see [AI providers](#ai-providers)).

### 2. Set up the project

```sh
git clone <your-repo-url> && cd langchain-rag-chat
make setup
```

`make setup` checks the tools above, creates `.env` from `.env.example` (and
`frontend/.env.local`), then installs packages: Python packages into `backend/.venv`
with `uv sync`, JavaScript packages into `frontend/node_modules` with `npm install`.

### 3. Configure `.env`

Everything is configured in **one file at the repo root**, `.env`; the API, worker and
docker-compose all read it. It is git-ignored, so secrets never get committed. Required:

| Variable | Where to get it |
|---|---|
| `MONGO_URL` | Atlas → your cluster → **Connect → Drivers** (the `mongodb+srv://…` string) |
| `DB_NAME` | Any name, e.g. `estateflow`. Collections and indexes are created automatically. |
| `COLLECTION_NAME` | Collection for document chunks and embeddings, e.g. `chunks` |
| `SECRET_KEY`, `REFRESH_SECRET_KEY` | Two different random strings: `openssl rand -hex 32` |
| `ENCRYPTION_KEY` | `cd backend && uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `HUGGINGFACEHUB_API_TOKEN` | huggingface.co → Settings → Access Tokens (needs **Make calls to Inference Providers**) |
| `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET` | See [Connect WhatsApp](#connect-whatsapp). Can wait until you connect a number. |

In Atlas, also allow your IP under **Network Access**.

### 4. Run it

```sh
make services     # start Redis in Docker
make seed         # optional: demo business with listings, leads and meetings
make dev          # API + worker + dashboard together; Ctrl+C stops all three
```

- Marketplace (what buyers see): http://localhost:3000
- Seller dashboard: http://localhost:3000/dashboard. The demo login is `demo@estateflow.dev` / `demo12345`.
- A seller's own listing page: http://localhost:3000/s/demo
- API docs: http://localhost:8000/docs

The API creates collections and indexes (including the Atlas Vector Search index) on
startup. `make seed-no-embed` loads the demo data without calling Hugging Face.

Prefer separate terminals? Run `make api`, `make worker` and `make web` instead of
`make dev`. To run everything in containers instead, use `make docker-up` / `make docker-down`.

### Everyday commands

Run `make` on its own to list every command.

| Command | What it does |
|---|---|
| `make dev` | Run API, worker and dashboard |
| `make test` | Backend tests, run against a local MongoDB and Redis in Docker; never your Atlas data |
| `make lint` | Check code style and common mistakes (Ruff for Python, ESLint for TypeScript) |
| `make format` | Auto-fix and reformat Python code |
| `make check` | Lint, type-check and tests: run before committing |
| `make evals` | Grade the WhatsApp assistant on buyer scenarios (spends HF credits) |
| `make install` | Re-install packages after pulling changes |
| `make clean` | Delete installed packages and build output |

### The tooling, briefly

- **uv** (backend): `pyproject.toml` lists the packages the backend needs, and `uv.lock`
  pins their exact versions. `uv sync` installs them into `backend/.venv`. `uv add <pkg>`
  adds a package, and `uv run <cmd>` runs a command inside the environment, so you never need
  to activate it. Python itself is downloaded into `~/.local/share/uv/python`, and your
  system Python is untouched.
- **npm** (frontend): `package.json` lists the packages and `package-lock.json` pins them.
  `npm install` installs them into `frontend/node_modules`.
- **Ruff**: Python linter and formatter (replaces flake8, black and isort). Its rules are in
  `backend/pyproject.toml` under `[tool.ruff]`. It's a development tool only and isn't
  installed in production images.
- **Docker Compose**: `docker-compose.yml` defines Redis (always), a local MongoDB under
  the `local` profile (`mongo`: the Atlas Local image with Vector Search, used by
  `make test` and for offline work), and containers for the API, worker and dashboard
  under the `app` profile. Your real data lives in MongoDB Atlas; there is no
  Postgres or other database.

### Troubleshooting

| Symptom | Fix |
|---|---|
| `The DNS query name does not exist: _mongodb._tcp…` | The Atlas cluster is paused or the URL is wrong. Resume it in Atlas. If it was just resumed, your computer may have cached the old answer for a few minutes: wait, or run `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`. |
| `ServerSelectionTimeoutError` | Your IP isn't allowed in Atlas → Network Access. |
| Assistant replies "passing this to our team" for everything | Hugging Face returned an error. `402 Payment Required` means the account needs Inference Providers credits. Check the worker logs. |
| `make test` can't connect | Docker Desktop isn't running; start it and retry. |
| Port 8000 or 3000 already in use | Another copy is running. Stop it, or `lsof -i :8000` to find it. |

Browser sessions use httpOnly cookies. API clients can send `X-Auth-Mode: token` on
login to get Bearer tokens instead.

## Connect WhatsApp

1. In Meta for Developers, create an app, add **WhatsApp**, register the business number.
2. Webhook URL: `{PUBLIC_BASE_URL}/api/v1/webhooks/whatsapp`, verify token = `WHATSAPP_VERIFY_TOKEN`,
   subscribe to `messages`. Set `WHATSAPP_APP_SECRET` to the app secret (signatures are verified).
3. In the dashboard: **Settings → WhatsApp number**, paste the phone number ID, display number
   and a permanent access token (stored encrypted).
4. For reminders outside the 24-hour window, create approved templates with three body
   variables (name, time, place) and enter their names under **Settings → WhatsApp assistant**.

Local testing needs a public URL for the webhook (e.g. `cloudflared tunnel --url http://localhost:8000`).

## AI providers

Everything runs on Hugging Face Inference Providers with `HUGGINGFACEHUB_API_TOKEN`.
Hosted inference is billed per use: add pre-paid credits (Billing → **Add Credits**) or
subscribe to PRO. Without credits, calls fail with `402 Payment Required`. The "Inference
Usage" figure on the billing page is a usage meter, not credit.

| Job | Setting | Default |
|---|---|---|
| Chat + tool calling | `HF_LLM_MODEL` | `Qwen/Qwen3-235B-A22B-Instruct-2507` (alternatives: `openai/gpt-oss-120b`, `meta-llama/Llama-3.3-70B-Instruct`) |
| Embeddings | `HF_EMBEDDING_MODEL`, `EMBEDDING_DIM` | `sentence-transformers/all-MiniLM-L6-v2`, 384 |
| Voice notes | `HF_ASR_MODEL` | `openai/whisper-large-v3` |
| Buyer photos | `HF_VISION_MODEL` | `Qwen/Qwen2.5-VL-72B-Instruct` |

Changing the embedding model or dimension needs a re-index: delete the vector index and
chunks, then re-save listings / retry documents.

`LLM_PROVIDER=anthropic` switches only the chat model to Claude (`claude-opus-5-5`).

## Evaluating the assistant

`backend/evals/` holds buyer scenarios (budget search, brochure questions, booking,
negotiation handover, Hindi, sold listing, prompt injection, photos, cancellation) graded
on tools called, reply content and CRM state:

```sh
make evals                                                    # all scenarios, 3 trials each
uv --directory backend run python -m evals.run -s book_site_visit -n 5   # one scenario
```

It spends inference credits and uses a separate database (`EVAL_DB_NAME`, default
`estateflow_eval`). Run it after changing the model, prompt or tools.

## Tests

```sh
make test      # starts local MongoDB + Redis in Docker, then runs pytest
```

Tests run against local Atlas (real transactions and `$vectorSearch`) and Redis, using the
`estateflow_test` database, a scripted LLM, a fake WhatsApp client and a deterministic
embedder. They never touch the database or Hugging Face account in your `.env`.

## Layout

```
backend/
  app/api/routes/        REST endpoints (auth, properties, CRM, scheduling, dashboard, public, webhooks)
  app/models.py          MongoDB document models; every tenant-owned document has tenant_id
  app/services/agent/    WhatsApp assistant: prompts + tenant-scoped tools
  app/services/llm/      Provider interface: Hugging Face (default) and Claude
  app/services/rag/      Ingestion (PDF/DOCX/TXT → chunks → Atlas Vector Search) and retrieval
  app/services/hf.py     Speech-to-text and image description
  app/services/          scheduling, inbound WhatsApp handling, notifications, client messages
  app/workers/           arq jobs and cron
  evals/                 Assistant evaluation scenarios and runner
  tests/                 pytest suite
frontend/
  src/app/(site)/        Buyer marketplace: home (/), search (/properties), listing (/properties/[seller]/[ref])
  src/app/dashboard/     Seller dashboard: Today, Calendar, Leads, WhatsApp inbox, Properties, Settings
  src/app/s/[slug]/      One seller's own listing page and site-visit booking page
  src/components/site/   Marketplace components (search, filters, listing cards, gallery)
legacy/                  The original Streamlit prototype
Makefile                 Shortcuts for setup, running, tests (`make` to list)
.env.example             Every setting, documented. Copy to .env
```
