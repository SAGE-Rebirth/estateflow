# EstateFlow — Real Estate CRM with a WhatsApp RAG Agent

Multi-tenant SaaS for builders, resellers and real estate firms. Each firm (a
**tenant**) lists properties, which appear on a public marketplace that buyers can
search and filter, like a property portal, and on the firm's own listing page.
Interested buyers tap "Chat on WhatsApp", talk to an AI assistant that answers from that
firm's listings and brochures, and can book site visits directly in chat. Everything
lands in a CRM dashboard where the team sees today's meetings, follow-ups,
leads and conversations.

## 1. Stack and decisions

| Area | Choice | Why |
|---|---|---|
| Tenancy | One database, `tenant_id` on every tenant-owned document; every lookup goes through tenant-scoped helpers (`get_owned`, explicit `tenant_id` filters) | Simple to operate; one tenant can never read another's data through the API |
| Backend | FastAPI (async) + PyMongo's async driver, Python 3.12, managed with uv | Keeps the Python/LangChain ecosystem; async fits webhook + model I/O |
| Database | **MongoDB Atlas** (8.0): CRM data, document chunks with embeddings (**Atlas Vector Search**), multi-document **transactions** | One store for CRM records and vectors; transactions make double-booking impossible (§5) |
| Queue / cron / locks | **Redis** + **arq** | Webhook returns 200 immediately; replies, ingestion and reminders run in a worker. Redis also holds rate-limit counters and per-sender locks |
| WhatsApp | Meta **Cloud API** (Graph API), signed webhooks, one number per tenant | Cheapest route; supports templates, media and interactive replies |
| AI | **Hugging Face Inference Providers** via `huggingface_hub`: chat with tool calling (Qwen3-235B), embeddings (all-MiniLM-L6-v2, 384 dims), speech-to-text (Whisper large-v3), image description (Qwen2.5-VL). Claude optional for chat | One account and bill for all AI; each model swappable by env var |
| LangChain | Text splitters in the ingestion pipeline | Robust chunking with overlap |
| Scheduling | Built in-house: weekly hours + days off → free slots → appointments; the assistant books inside the chat | No third-party calendar; everything stays in the CRM |
| Frontend | Next.js 15 (App Router) + Tailwind 4 + TanStack Query + FullCalendar | One app: buyer marketplace (server-rendered, SEO-friendly) at `/`, seller dashboard at `/dashboard` |
| Auth | JWT access (30 min) + refresh (14 days) in httpOnly, SameSite=Lax cookies; Origin check on cookie-authenticated writes; `token_version` for revocation; bcrypt; roles owner/admin/agent | Tokens are never readable by page scripts; sessions can be revoked instantly |

## 2. System diagram

```
 Buyer ── marketplace: home → search → listing (Next.js) ──► "Chat on WhatsApp" (wa.me link carrying the ref code)
   │                                                     │
   └──────────────────── WhatsApp ◄──────────────────────┘
                            │  webhook (HMAC-signed)
                            ▼
                 FastAPI /webhooks/whatsapp ── verify signature, enqueue (job id = wamid) ─► Redis
                                                                                            │
                       arq worker ◄─────────────────────────────────────────────────────────┘
                         │ Redis lock per sender
                         │ tenant by phone_number_id → upsert contact → open conversation
                         │ insert message (unique wamid = idempotent)
                         │ photo → vision model description · voice note → Whisper transcript
                         │ ref codes in the text → property interest
                         │ conversation in human mode → notify team, stop
                         ▼
                   Assistant (HF chat model + tools)
                     search_properties · get_property_details · send_property_photos
                     search_knowledge (Atlas Vector Search) · get_available_slots
                     book_appointment · list_my_appointments · cancel_appointment
                     update_lead_profile · request_human
                         │
                         ▼
                 WhatsApp Cloud API ─► buyer
                         │
                         ▼
          MongoDB Atlas (CRM + vectors) ──► Dashboard (Next.js) ◄── notifications
                                           Today · Calendar · Leads · Inbox · Properties
```

## 3. Data model (MongoDB collections)

Documents use string ids (`_id`, 32-char hex). Every collection except `tenants` carries
`tenant_id`. Lists that belong to one parent are embedded instead of split into tables.

| Collection | Key fields | Embedded | Indexes |
|---|---|---|---|
| `tenants` | name, slug, timezone, currency, WhatsApp number id + display number, encrypted access token, `bot_settings` (persona, instructions, template names) | — | `slug` unique; `whatsapp_phone_number_id` unique (when set) |
| `users` | email, password_hash, full_name, role, is_active, `token_version`, `calendar_rev` | `availability[]` (weekday, "HH:MM" start/end, slot minutes), `days_off[]` | `email` unique |
| `properties` | ref_code (e.g. `PR-1042`), title, description, listing/property type, status, price, area, bedrooms, location, amenities, published, assigned_to | `media[]` (url, storage path, kind, order) | `(tenant_id, ref_code)` unique |
| `documents` | brochures, price sheets, FAQs; optional property_id; source (upload / generated listing text); status, error, chunk_count | — | `(tenant_id, property_id)` |
| chunks (`COLLECTION_NAME`) | document_id, property_id, ref_code, `active`, content, `embedding` (384 floats), source | — | Atlas Vector Search index `chunks_vector` (cosine) with filters on tenant_id, property_id, active |
| `contacts` (leads) | phone (E.164), wa_id, name, email, source, stage, budget, preferred locations/type/bedrooms, notes, assigned_to, last_inbound_at | `interests[]` (property, ref code, when) | `(tenant_id, phone)` unique |
| `conversations` | contact_id, mode (bot/human), status, focus_property_id, last_message_at, `last_direction`, last_message, unread_count | — | `(tenant_id, contact_id, status)` |
| `messages` | conversation_id, direction, sender_type, body, wa_message_id, delivery status, media_kind/path/mime, meta (transcript, description) | — | `wa_message_id` unique (when set) — webhook retries are no-ops |
| `appointments` | contact, property, user, kind, status, starts_at/ends_at, location, notes, outcome, created_by_bot, reminder flags | — | `(user_id, starts_at)`, `(status, starts_at)` |
| `tasks` | follow-ups: contact, assignee, title, due_at, done_at, reminder_sent | — | `(tenant_id, done_at, due_at)` |
| `activities` | per-contact timeline: note, call, message, stage change, appointment, interest, handover | — | `(contact_id, created_at)` |
| `notifications` | user, kind, title, body, link, read_at | — | `(user_id, read_at, created_at)` |

Indexes, including the vector index, are created idempotently when the API and the worker
start (`app.core.db.ensure_indexes`); there are no migrations to run.

### Web routes

| Route | Who | What |
|---|---|---|
| `/` | Buyers | Marketplace home: sentence search ("I want to buy a 3 BHK in Hebbal under ₹1 Cr"), newly listed homes, browse by city / type / budget |
| `/properties` | Buyers | Search results with filters (buy/rent, area, BHK, budget, type), sorting and pagination |
| `/properties/{seller}/{ref}` | Buyers | Listing: gallery, facts, price per sq ft, amenities, floor plan, map, seller card with WhatsApp and site-visit booking, similar homes |
| `/s/{seller}`, `/s/{seller}/book` | Buyers | One seller's own listing page and booking page |
| `/dashboard/…` | Sellers | Today, calendar, leads, WhatsApp inbox, properties, settings |

The marketplace API (`/api/v1/market/…`) returns published, available listings from every
active seller that hasn't switched off "Show my listings on the marketplace" (Settings →
Business).

## 4. Assistant design

- One assistant turn per inbound message; history is the last 20 text messages of the
  conversation, consecutive same-side messages merged.
- System prompt = stable persona and rules + tenant settings, then per-turn context: buyer
  profile, property in focus, current local time.
- Tools are bound to one tenant and one buyer; the model never sees or chooses `tenant_id`.
  Tool calls run one at a time because they update shared records.
- Structured questions (budget, bedrooms, area) go to MongoDB queries via
  `search_properties`; free-text questions ("payment plan?", "is there a gym?") go to vector
  search over listing text and uploaded documents (`search_knowledge`).
- Answers must come from tool results. Unknown facts, negotiation, complaints or a request
  for a person → `request_human`: the conversation switches to human mode and the team is
  notified. Model errors, refusals and runaway tool loops also hand over, with a safe reply.
- Photos are described by the vision model and voice notes transcribed before the chat model
  sees them, so the chat model only needs text and tool calling.
- Replies are WhatsApp-sized: short, no tables, in the buyer's language.
- `backend/evals/` grades the assistant on fixed buyer scenarios (tools called, reply
  content, resulting CRM state).

### Retrieval

1. Uploaded files (PDF, DOCX, TXT, MD) and each published listing's own text are split into
   ~900-character chunks (150 overlap) and embedded.
2. Chunks of sold, rented, draft or unpublished listings are marked `active: false`, so they
   stop appearing in answers without being deleted.
3. Queries use `$vectorSearch` filtered by tenant (and optionally one listing plus
   tenant-wide documents). Results below a cosine similarity of 0.4 are dropped.
4. `VECTOR_SEARCH_MODE=exact` scores in Python instead, for MongoDB deployments without Atlas
   Search.

## 5. Scheduling and notifications

- Free slots = each member's weekly hours − days off − active appointments, in the tenant's
  timezone, with a minimum lead time (2 h) and a 14-day horizon. Bookings without a named
  agent go to the least-loaded free member that day.
- **No double-booking**: every booking or reschedule runs in a MongoDB transaction that
  increments the agent's `users.calendar_rev`, checks for an overlapping active
  appointment, then writes. Two concurrent bookings for the same agent write-conflict; the
  driver retries the loser, which then sees the winner's appointment and is refused.
- Booking (assistant, staff or public page) → appointment + activity + notification to the
  agent + WhatsApp confirmation to the buyer.
- Worker cron:
  - every 5 min: buyer reminders 24 h and 2 h before (a template outside WhatsApp's 24-hour
    window; retried until sent), agent reminder 1 h before, follow-up tasks due within 30 min
  - hourly: 07:00 tenant-local daily digest ("Today: 3 meetings, 2 follow-ups")
- Dashboard `/today`: today's meetings, the next 3 days, past meetings without an outcome,
  overdue and due follow-ups, chats where the buyer is waiting for a person, new leads.

## 6. Security

- **WhatsApp webhook**: `X-Hub-Signature-256` HMAC with the app secret, verify-token
  handshake, unique message ids.
- **Secrets at rest**: each tenant's WhatsApp access token is Fernet-encrypted
  (`ENCRYPTION_KEY`).
- **Sessions**: httpOnly cookies (SameSite=Lax, Secure in production); writes authenticated
  by cookie must carry an allowed `Origin`. Bearer tokens remain available for API clients.
  Password change, "sign out everywhere" and deactivation bump `token_version`, revoking
  every existing token.
- **Rate limits** (Redis): login per IP and per account, signup, token refresh, password
  change, public pages per IP, public bookings per IP and per phone number. Limits fail open
  if Redis is down.
- **Tenant isolation**: ids from the URL are always looked up together with the caller's
  `tenant_id`; cross-tenant access returns 404.
- **Files**: size and type limits. Listing photos live in a public area (served at
  `/media`, also sent on WhatsApp); brochures and buyers' photos/voice notes live in a
  private area served only through authenticated, tenant-checked endpoints.
- **Production guard**: the API refuses to start in production with default or missing
  secrets.

## 7. Environments

| | Local development | Production |
|---|---|---|
| MongoDB | Your Atlas cluster, or the `mongo` container (Atlas Local: vector search + transactions) | MongoDB Atlas |
| Redis | `redis` container | Managed Redis or the container |
| API, worker, dashboard | `make dev` | Containers from `docker-compose.yml` (`app` profile) or any container host |
| AI | Hugging Face Inference Providers (needs credits) | Same |
| Tests | `make test`: Atlas Local + Redis in Docker, database `estateflow_test`, scripted model, fake WhatsApp, deterministic embedder | — |

## 8. Phases

1. **Backend core** ✅: config, document models, auth, tenants/users, properties + media,
   document ingestion + retrieval, model providers, assistant + tools, WhatsApp webhook and
   sending, scheduling, tasks, notifications, dashboard API, worker + cron, tests.
2. **Dashboard** ✅: sign-in, Today, calendar, leads pipeline + timeline, WhatsApp inbox
   with human takeover and buyer media, properties with photos and brochures, availability,
   WhatsApp and assistant settings, team, account.
3. **Public site** ✅: buyer marketplace (home with search, filtered results, listing pages
   with gallery, map and WhatsApp contact, similar homes), per-seller listing page,
   booking page.
4. **Hardening** ✅: cookie sessions, rate limiting, WhatsApp media in and out, eval
   harness, move to MongoDB Atlas + Hugging Face.
5. **Next**: S3-compatible file storage, real-time notifications (SSE), Google Calendar
   sync, audit log, error tracking/tracing (Sentry/OpenTelemetry), per-tenant usage
   metering and billing, per-tenant data export.
