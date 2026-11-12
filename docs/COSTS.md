# EstateFlow running costs

What it costs per month to run the platform at three levels of use. All prices are
list prices checked on **12 November 2026**; conversions use **₹94 = $1**. Figures are
estimates for budgeting. Recheck the sources at the end before quoting a client.

## Summary

| | Least (pilot) | Generic (growing) | High (marketplace) |
|---|---|---|---|
| Who | 1–2 sellers | ~10 sellers | ~100 sellers |
| Buyer WhatsApp messages / month | 1,500 (≈50 a day) | 15,000 | 150,000 |
| Listings | 50 | 500 | 5,000 |
| Site visits booked / month | 50 | 500 | 5,000 |
| **Hosting and database** | ₹3,800 | ₹12,500 | ₹66,700 |
| **AI (Google Gemini)** | ₹900 | ₹9,200 | ₹91,700 |
| **WhatsApp (Meta), incl. 18% GST** | ₹20 | ₹900 | ₹8,800 |
| **Total / month (until 31 Dec 2026)** | **≈ ₹4,700** ($50) | **≈ ₹22,600** ($240) | **≈ ₹1,67,300** ($1,780) |
| **Total / month (from 1 Jan 2027)** | **≈ ₹5,600** | **≈ ₹31,700** | **≈ ₹2,58,500** |
| Cost per buyer message | ₹3.10 | ₹1.50 | ₹1.10 |

> **1 January 2027:** Google doubles the price of `gemini-3.6-flash`, the model that writes
> WhatsApp replies. That's why the totals jump. See [Ways to cut the bill](#ways-to-cut-the-bill).

The AI bill grows with **buyer messages**. Listings, photos, brochures and smart paste
barely register. Hosting grows in steps as the database and servers move up a size.

## What each action costs

AI prices are Gemini's paid tier.

| Action | Model | Until 31 Dec 2026 | From 1 Jan 2027 |
|---|---|---|---|
| Assistant answers one buyer message (≈6,000 input + 500 output tokens) | `gemini-3.6-flash` | ₹0.60 | ₹1.20 |
| Transcribe a 30-second voice note | `gemini-3.6-flash` | ₹0.13 | ₹0.26 |
| Describe a photo a buyer sends | `gemini-3.6-flash` | ₹0.13 | ₹0.26 |
| Smart paste (fill a form from pasted text) | `gemini-3.5-flash-lite` | ₹0.11 | ₹0.11 |
| Index a listing for search | `gemini-embedding-2` | ₹0.006 | ₹0.006 |
| Index a 20-page brochure | `gemini-embedding-2` | ₹0.23 | ₹0.23 |
| **Voice fill in forms** (English and Hindi) | the browser's own speech recognition | **free** | **free** |
| Send a visit confirmation or reminder on WhatsApp | Meta, utility message | ₹0.136 incl. GST | same |
| WhatsApp reply (assistant or staff), first 1,000 a month per number | Meta, service message | free | free |
| WhatsApp reply after the first 1,000 that month | Meta, service message | ₹0.136 incl. GST | same |

Token figures come from live runs of the assistant. A plain answer used about 3,500 input
tokens; one that searched listings or checked visit slots used about 7,500. The budget
assumes 6,000 input and 500 output tokens per message. Long chats cost more, because the
last 20 messages are re-sent each time (`AGENT_HISTORY_TURNS`).

## Assumptions per tier

| | Least | Generic | High |
|---|---|---|---|
| Buyer messages answered by the assistant | 1,500 | 15,000 | 150,000 |
| Voice notes from buyers | 50 | 500 | 5,000 |
| Photos from buyers | 50 | 500 | 5,000 |
| Smart pastes | 30 | 300 | 3,000 |
| Listings indexed (re-indexed when edited) | 50 | 500 | 5,000 |
| Brochures uploaded | 5 | 50 | 500 |
| Visits booked (each → confirmation + 24 h + 2 h reminder = 3 messages) | 50 | 500 | 5,000 |

## Hosting and database

| | Least | Generic | High |
|---|---|---|---|
| MongoDB Atlas | Flex, $8–30 (≈$15) | M10, $57 + backups ≈$8 | M30, $394 + backups ≈$40 |
| App servers (API, worker, website) | One 4 GB server running everything with Docker Compose, ≈$24 | One 8 GB server, $48 | Three 8 GB servers + load balancer, ≈$156 |
| Redis (queue, rate limits) | On the same server | Managed, ≈$15 | Managed, ≈$45 |
| Photo and file storage | Server disk | Object storage, ≈$5 | Object storage + CDN, ≈$35 |
| Monitoring, error tracking | Free tiers | Free tiers | ≈$40 |
| Domain | ≈$1 (≈₹1,000 a year) | included | included |
| **Total** | **≈$40 / ₹3,800** | **≈$133 / ₹12,500** | **≈$710 / ₹66,700** |

- **Atlas:** prices are for AWS us-east-1. A cluster in Mumbai (`ap-south-1`) costs somewhat
  more, so price it in the [Atlas calculator](https://www.mongodb.com/pricing/calculator).
- **Free Atlas tier:** M0 costs nothing and runs the app, including vector search, for a
  demo. But it caps at 512 MB and 3 search indexes and has no backups, so don't put a
  paying client on it.
- **Moving up a database size:** M10/M20 have burstable CPUs. Move to M30 when the
  dashboard feels slow at busy hours; M20 ($146) is the step between.
- **Server prices** are DigitalOcean-style list prices. AWS Lightsail, Hetzner and similar
  providers are in the same range.

## WhatsApp: who pays

Each seller connects **their own** WhatsApp Business number, so **Meta bills each seller's
own Meta account**, not the platform. The WhatsApp row above is the combined total across
all sellers, for when you resell the platform with messaging included.

- **Free:** messages from buyers are always free.
- **Service messages** are free-form replies inside the 24-hour window after a buyer writes:
  - The first **1,000 per number per month** are free.
  - From **1 October 2026**, Meta charges after those (≈₹0.115 + GST).
- **Utility messages:** visit confirmations and reminders sent as templates (≈₹0.115 + GST).
  From 1 October 2026 these are charged even inside the 24-hour window.
- **Marketing messages** (≈₹0.86 + GST) are never sent by the platform. A seller sending
  broadcasts would pay those separately.
- **Billing changes:** Indian businesses must move their Meta billing to INR by
  31 December 2026, or messages stop on 1 January 2027.
- **Provider fees:** if a seller goes through a WhatsApp provider (a BSP) instead of
  connecting directly, add that provider's fee.

## Free tiers and why production must be paid

The Gemini free tier is enough for development and demos, but not for clients:

- **Too small:** about 5 requests a minute and 20 a day for `gemini-3.6-flash`. Each buyer
  message needs 1–3 requests, so that's under 10 buyer messages a day.
- **Not private:** on the free tier, Google uses submitted content to improve its products.
  Buyer chats contain names, phone numbers and budgets, so turn on billing for any real
  client data.

## Ways to cut the bill

1. **Try the "lite" model for WhatsApp replies:** `GEMINI_LLM_MODEL=gemini-3.5-flash-lite`.
   - About **₹0.29 per reply** instead of ₹1.20 from 2027, cutting the high-tier AI bill
     from ≈₹1.8 lakh to ≈₹43,000 a month.
   - It isn't tested yet for tool use or Hindi on this platform. Run `make evals` with it
     first and switch only if the scores hold.
2. **Send less history:** lower `AGENT_HISTORY_TURNS` from 20 to 10. That's roughly 30–40%
   fewer input tokens on long chats, but the assistant remembers less of the conversation.
3. **Pause idle databases:** pause the Atlas cluster for staging or demo projects when not
   in use.
4. **Voice fill is already free**: it uses the browser's own speech recognition, not
   Gemini.
5. **Avoid needless reindexing:** run `make reindex` only after changing the embedding
   model. Each run re-embeds every listing and document (cheap, but not free at 5,000+
   listings).

## Recalculating for a client

Monthly AI cost ≈ **buyer messages × ₹0.60** (₹1.20 from 2027), plus ~5% for voice notes,
photos and smart paste.

Monthly WhatsApp cost per seller ≈ **(replies above 1,000 + 3 × visits booked) × ₹0.136**.

Add the hosting tier that matches the number of sellers and listings.

## Sources (checked 12 Nov 2026)

- Gemini API prices and free tier: https://aistudio.google.com/docs/pricing
- WhatsApp Business Platform pricing rules: https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing
- India WhatsApp rates: Meta's India rate card wasn't published openly. The rates above
  (marketing ₹0.8631, utility/authentication/service ₹0.115) match several Indian provider
  guides, e.g. https://chatmaxima.com/whatsapp-api-pricing/india/ and
  https://mindlytics.in/blog/whatsapp-business-api-pricing-india-2026. Confirm in your
  Meta Business Manager before quoting.
- MongoDB Atlas (updated 29 Sep 2026): https://www.mongodb.com/pricing
- Server prices: DigitalOcean list prices as reported in 2026 reviews, e.g.
  https://www.activepieces.com/blog/digitalocean-pricing-plans-and-real-costs-in-2026.md.
  Confirm on the provider's site.
- Exchange rate: ≈₹94/$ (early November 2026), e.g. https://currencybeacon.com/rates/USD/INR
