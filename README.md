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
| AI | Google Gemini for everything: chat with tool calling (`gemini-3.6-flash`), embeddings (`gemini-embedding-2`, 768 dims), voice notes and buyer photos (`gemini-3.6-flash`). Claude optional for chat. LangChain text splitters. |
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

You also need a **MongoDB Atlas** cluster (the free tier works) and a **Gemini API key**
with billing or credits (see [AI providers](#ai-providers)).

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
| `GEMINI_API_KEY` | Google AI Studio → **Get API key** (https://aistudio.google.com/apikey) |
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
startup. `make seed-no-embed` loads the demo data without calling Gemini.

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
| Assistant replies "passing this to our team" for everything | Gemini returned an error. `402 … prepayment credits are depleted` means the AI Studio project needs credits or billing (https://ai.studio/projects). Check the worker logs. |
| Gemini errors although your key in `.env` works | A `GEMINI_API_KEY` exported in your shell (e.g. in `~/.zshrc`) overrides `.env` for local runs. Remove it, or run `unset GEMINI_API_KEY` before `make dev`. Docker reads only `.env`. |
| Documents stuck as **Failed**, or the assistant can't find listings | Embeddings failed (same cause as above), or the embedding model/size changed. Fix the cause, then `make reindex`. |
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

Everything runs on Google Gemini with `GEMINI_API_KEY`. Usage is billed to the key's AI
Studio project; when its prepaid credits run out, calls fail with `402 RESOURCE_EXHAUSTED`
and the assistant hands every chat to your team until you top up.

| Job | Setting | Default |
|---|---|---|
| Chat + tool calling | `GEMINI_LLM_MODEL`, `GEMINI_THINKING_LEVEL` | `gemini-3.6-flash`, `low` |
| Embeddings | `GEMINI_EMBEDDING_MODEL`, `EMBEDDING_DIM` | `gemini-embedding-2`, 768 |
| Voice notes and buyer photos | `GEMINI_MEDIA_MODEL` | `gemini-3.6-flash` |

Changing the embedding model or dimension needs `make reindex`: it updates the Atlas
vector index to the new size and re-embeds every listing and document.

`LLM_PROVIDER=anthropic` switches only the chat model to Claude (`claude-opus-5-5`).

## Voice fill and smart paste

Every dashboard form, plus sign-up and the public booking page, has **Fill by voice**.
It starts at the field the cursor is in (or the first empty one), types what you say, and
moves to the next field. Prices, areas and counts understand "95 lakh", "1.2 crore" and
"twelve hundred". Dropdowns match the option you name, and checkboxes take yes or no.
Description boxes keep listening until you say "next". Spoken commands: *next*, *back*,
*clear*, *submit form*, *stop* (or Esc). One-line forms such as notes, follow-ups and
WhatsApp replies get a mic button instead.

Voice works in **English and Hindi**: switch with the EN / हिंदी toggle, which each device
remembers. Hindi understands "डेढ़ करोड़", "साढ़े तीन", हाँ/नहीं, Hindi option names
(किराया → Rent, फ्लैट → Apartment) and the commands अगला, पीछे, साफ़ करो, जमा करो, रुको. City
names said in Hindi are typed in English so search keeps working. Dictate emails in English.
Voice runs on the browser's own speech recognition (Chrome, Edge, Safari). It's free and
doesn't use your Gemini quota. In Firefox the mic button is hidden.

**Smart paste:** paste a block of text (a WhatsApp forward, a portal listing, an email)
anywhere in **Add property** or **Add lead**, and the fields it mentions are filled and
highlighted, with Undo. The text can be English, Hindi or Hinglish. Short pastes behave normally, and a paste into a text box still
lands there. It uses one `GEMINI_EXTRACT_MODEL` call per paste (default
`gemini-3.5-flash-lite`, about 2 s). Emails and phone numbers are always taken verbatim
from the text, never retyped by the model.

## Running costs

Monthly cost estimates for a pilot, a growing agency and a marketplace (hosting, Gemini,
WhatsApp), what each action costs, and ways to cut the bill: [docs/COSTS.md](docs/COSTS.md).

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
embedder. They never touch the database or Gemini key in your `.env`.

## Layout

```
backend/
  app/api/routes/        REST endpoints (auth, properties, CRM, scheduling, dashboard, public, webhooks)
  app/models.py          MongoDB document models; every tenant-owned document has tenant_id
  app/services/agent/    WhatsApp assistant: prompts + tenant-scoped tools
  app/services/llm/      Provider interface: Gemini (default) and Claude
  app/services/rag/      Ingestion (PDF/DOCX/TXT → chunks → Atlas Vector Search) and retrieval
  app/services/gemini.py Gemini client, speech-to-text and image description
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
