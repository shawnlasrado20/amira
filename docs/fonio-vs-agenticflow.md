# Fonio vs AgenticFlow — Platform Comparison

**Date:** July 2026
**Sources:** Fonio Public API spec (`app.fonio.ai/api/docs`), Fonio Help Center (`fonio.info`), AgenticFlow OpenAPI spec + 189 doc pages

---

## Headline finding

**Fonio has almost no public API.** Their entire "Fonio Public API v1.0" is **two endpoints**:

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/public/v1/outbound_call` | Trigger an outbound call |
| `POST` | `/api/public/v1/test-api-key` | Check whether your key is valid |

That's it. One real endpoint and a health check.

The outbound-call payload is minimal:

```json
{
  "apiKey":     "fonio_…",
  "fromNumber": "+49…",     // required
  "toNumber":   "+49…",     // required
  "context":    { }         // free-form object passed to the assistant
}
```

Auth is `Authorization: Bearer <key>` (or `apiKey` in the body).

**What you cannot do through Fonio's API:** create or edit assistants, manage knowledge bases, provision phone numbers, list or read calls, manage tools, or anything multi-tenant. All of that is dashboard-only, by hand.

---

## The strategic read

These are two fundamentally different kinds of product:

| | **Fonio** | **AgenticFlow** |
|---|---|---|
| **What it is** | A finished product with a polished UI | A platform / API with no product layer |
| **Public API** | 2 endpoints | 11 resource families, ~189 doc pages |
| **Who it's for** | End customers (SMBs) | Builders |
| **Can you build a SaaS on it?** | **No** — no programmatic provisioning | **Yes** — that's the point |
| **Phone numbers** | **Fonio provides them** (+ SIP, + forwarding) | **BYO only** — your Twilio or your SIP trunk |
| **Multi-tenant** | Not exposed | Possible via folders + metadata |

**Fonio doesn't need an API because their UI does everything.** They're selling the finished thing. We're not competing with their API — we're competing with their product, and building it on a platform that gives us programmatic control they don't offer their own customers.

---

## Feature comparison

From Fonio's Help Center article catalog, mapped against what AgenticFlow exposes:

| Capability | Fonio | AgenticFlow | Notes |
|---|---|---|---|
| Prompt / persona editor | Yes (guided) | Yes, via API | They ship a prompt-writing guide; we'd need equivalent onboarding |
| **Phone numbers** | **Provides own numbers**, individual numbers, SIP, forwarding | **BYO Twilio / BYO SIP only** | **Fonio's biggest advantage** — see below |
| Appointment booking | Built-in scheduler + Cal.com + Calendly | Via function tools → your own logic | We build it; they ship it |
| Call transfer | Yes | Yes — plus **dynamic destination resolver** via webhook | AgenticFlow is *more* capable here |
| Email after calls | Yes — **explicitly post-call** | Via end-of-call webhook | Parity |
| **Mid-call actions** | Only via Cal.com/Calendly's own notifications | **Function tools, sync + async, 20s budget** | **Our advantage** — see below |
| WhatsApp | Beta / Early Access | Full messaging API (channels, templates, conversations) | AgenticFlow is well ahead |
| Webhooks | Yes | tool-call, end-of-call, status-update, transcript, assistant-request | AgenticFlow richer |
| Knowledge base | Google Sheets recommended | Full KB API — files, URLs, re-sync | AgenticFlow richer |
| Automation | **"Make and n8n"** for anything not native | Same pattern, via tool webhooks | Both punt to n8n |

---

## Two findings that matter most

### 1. Fonio also sends email *after* the call

Their Help Center is explicit: *"Send Email **post-call** function: configure subject, recipient prompt, conditions, email content, and variables **after calls**."*

So the thing that bothered you about our build — confirmation arriving after the caller hangs up — **is also how Fonio works.** Building genuine mid-call notifications via function tools would put us *ahead* of them, not catching up.

**But note how they get away with it:** appointment booking runs through **Cal.com or Calendly**, and those platforms send their own confirmation email/SMS the instant a booking is created. So the caller *does* get a confirmation mid-call — it just comes from Cal.com, not from Fonio.

**That's a shortcut worth stealing.** We don't have to build an SMS/email system to get the mid-call moment. Integrate Cal.com properly and let it do the notifying. Far less to build, and it works immediately.

### 2. Fonio provides phone numbers. AgenticFlow does not.

This is the single biggest gap in our stack, and it's the one place Fonio is structurally ahead.

- **Fonio:** "use fonio numbers, individual phone numbers, SIP numbers, call forwarding." A customer signs up and gets a number.
- **AgenticFlow:** `POST /phone-number` requires `twilioAccountSid` + `twilioAuthToken`, or an existing SIP trunk. It will never sell you a number.

So our self-serve onboarding needs a **pre-bought number pool on our own Twilio**, with India/UAE KYC bundles cleared in advance. Fonio has no such constraint because they're the telco layer as well.

---

## Fonio's pricing (for reference)

| Tier | Price | Effective per-minute |
|---|---|---|
| Prepaid | €0.20/min (min €300 top-up) | €0.20 |
| Plans | €99 – €799/mo | — |
| Business | €799/mo | €0.08/min |

Our modelled cost on Sarvam is ~₹2/min (~€0.02) for Indian languages and ~0.30–0.40 AED (~€0.08) for Arabic via Munsit — so there is real margin room against Fonio's published rates, especially in the India/expat lane.

---

## Where we can genuinely beat them

1. **Mid-call actions.** Their email is post-call by design. Function tools with `asyncMode: false` let our assistant book, confirm, and notify *while the caller is still on the line* — and then say "I've just texted you." That's a demo moment they can't currently match.

2. **Indian languages at Indian prices.** Fonio is EU-first (their help centre is German-heavy). Sarvam gives us 11 native Indian languages at a fraction of their per-minute cost.

3. **Programmatic multi-tenancy.** We can provision, configure, and manage assistants entirely by API. A Fonio customer can't — and neither can Fonio offer it to a partner without building it.

4. **Deeper automation.** Both stacks punt to n8n, but our tool webhooks give n8n a *bidirectional* role — n8n can answer the assistant mid-call, not just receive events afterwards.

## Where they're ahead

1. **Phone numbers.** They own the telco layer. We need a number pool and KYC. This is real work.
2. **Product maturity.** Built-in scheduler, WhatsApp, guided prompt writing, a real help centre. Years of polish.
3. **Onboarding.** Their flow is proven; ours is half-built.

---

## Recommendations

**Do now**
- **Integrate Cal.com for booking** rather than building calendar logic ourselves. It solves booking *and* gives us instant mid-call confirmations for free — matching Fonio's real behaviour at a fraction of the effort.
- **Build the number pool.** It's the only structural gap where Fonio is genuinely ahead and it blocks self-serve onboarding entirely.

**Do next**
- **Ship mid-call function tools** (`check_availability`, `book_appointment`) — the one place we can visibly beat them.
- **Lean into Indian languages.** It's our cost advantage and their blind spot.

**Don't bother**
- Don't try to match WhatsApp beta or their built-in scheduler early. Cal.com covers scheduling; AgenticFlow's messaging API is already ahead on WhatsApp when we want it.

---

## Caveats

- Fonio may have a **private/partner API** beyond the two public endpoints. Nothing here rules that out — this reflects what they publish.
- Their Help Center is a client-rendered SPA; the feature list above comes from its article catalog, which may not be exhaustive.
- No authenticated calls were made against Fonio's API. This comparison is from public documentation only.
- **Rotate any API keys that have been shared in chat or docs** — both the Fonio and AgenticFlow ones.
