# Appointment Scheduler: Build vs. Buy

**Date:** July 2026
**Question:** Is there an existing project we can use instead of building a scheduler, and will it work with our stack?

---

## Short answer

**Yes — use Cal.com. Don't build a scheduler.**

Scheduling looks simple and isn't. Timezones, DST, buffers, double-booking races, recurring availability, calendar sync, cancellation/reschedule links, no-show handling. It's a year of edge cases that has already been solved.

Cal.com fits our stack almost exactly, and critically it solves the **per-customer Google Calendar credential problem** that would otherwise be the hardest part of the build.

⚠️ **One important gotcha:** the GitHub repo situation changed recently and it's easy to pick the wrong thing. Details below.

---

## The repo confusion — read this first

`github.com/calcom/cal.com` now **redirects to `github.com/calcom/cal.diy`**. They are not the same product.

| | **Cal.diy** (the MIT repo) | **Cal.com Platform** (commercial) |
|---|---|---|
| License | MIT, 100% open source, 46.9k ⭐ | Commercial / hosted |
| Enterprise features | **Removed** — no Teams, Organizations, Insights, Workflows, SSO | Included |
| **Managed users (multi-tenant)** | **Not available** | **Yes** — the thing we need |
| Intended for | Individuals and self-hosters | SaaS products embedding scheduling |

Their own README says it plainly: *"For any commercial and enterprise-ready scheduling infrastructure, use Cal.com, not Cal.diy."*

**So self-hosting the free MIT fork does not give us multi-tenancy.** If we self-host Cal.diy we'd be running one scheduler and building customer isolation ourselves — which puts us back to writing the hard part.

---

## Why Cal.com Platform fits our architecture

### It solves the credential problem

In the mid-call-tools doc I flagged this as the main blocker: n8n's built-in Google Calendar node uses **one fixed credential**, so it can't serve 500 customers with their own calendars.

Cal.com Platform's **managed users** solve it directly:

1. We create **one OAuth client** (ours).
2. At signup we create a **managed user** per customer — `POST` with their email; we get back a user id, access token, and refresh token.
3. The customer connects their own Google Calendar through Cal.com's `Connect.GoogleCalendar` component — **it handles the entire OAuth flow for us**.
4. Every API call we make on their behalf uses their access token.

Tokens expire after 60 minutes and refresh through a backend endpoint we host, so the client secret never reaches the browser. That's the whole multi-tenant calendar problem, handled.

### The API maps onto our two tools exactly

Cal.com API v2 has the endpoints our voice tools need:

| Our tool | Cal.com endpoint |
|---|---|
| `check_availability` | `GET /v2/slots` |
| `book_appointment` | `POST /v2/bookings` |
| `cancel_reschedule` | `PATCH`/`DELETE` on `/v2/bookings` |
| Appointment types per business | `/v2/event-types` |
| Working hours | `/v2/schedules` |
| Calendar connections | `/v2/calendars` |

### It gives us the mid-call moment for free

This is the part worth noticing. **Cal.com sends its own confirmation email/SMS the instant a booking is created.**

So we don't need to build a notification system to get the effect you wanted — the caller's phone buzzes while they're still on the line, because Cal.com sent it, not us.

That is also exactly how Fonio does it. Their own docs describe their email feature as *post-call*; the mid-call confirmation their users see comes from Cal.com/Calendly, not from Fonio.

---

## How it plugs into the current stack

Nothing about our architecture changes — Cal.com just becomes another service n8n talks to.

```
Caller: "Can I book Thursday at 2?"
   │
AgenticFlow  ──function tool──▶  n8n webhook
                                   │
                                   ├─ resolve tenant  (assistantId → customer)
                                   ├─ fetch their Cal.com access token
                                   ├─ GET  /v2/slots        ← availability
                                   ├─ POST /v2/bookings     ← book it
                                   │      └─ Cal.com emails/SMSes the caller NOW
                                   └─ respond to webhook
   │
Assistant: "Booked for Thursday at 2 — confirmation's on its way."
```

- **AgenticFlow** — unchanged, just a function tool pointed at n8n
- **n8n** — unchanged pattern, one more HTTP node
- **Supabase** — stores `customer_id → cal_managed_user_id + tokens`
- **Dashboard** — the "Book appointments" ability row finally does something

Latency is fine: a slots lookup plus a booking is well under 2 seconds, against a 20-second tool timeout.

---

## Cost

| Option | Cost | Multi-tenant? |
|---|---|---|
| **Cal.com Platform (hosted)** | Per-booking beyond plan quota — reported **$0.50–$0.99 per extra booking** depending on tier | Yes, native |
| Cal.com Teams/Orgs | ~$12/user/mo (Teams), ~$28/user/mo (Orgs), billed yearly | Per-seat — bad fit for many small customers |
| **Self-host Cal.diy (MIT)** | Free software; ~$100–300/mo infra, ~1 week setup | **No** — we'd build it |

**The per-booking model is worth modelling carefully.** At $0.50–0.99 a booking it could rival or exceed our entire per-minute voice cost, so it needs checking against realistic booking volumes before we commit. Cal.com's published Platform pricing is thin — get a real quote.

---

## Alternatives considered

| Project | Stars / License | Verdict |
|---|---|---|
| **Cal.diy** | 46.9k · MIT | Great software, but enterprise/multi-tenant features stripped. Only viable if we build isolation ourselves. |
| **Easy!Appointments** | 4.3k · GPL-3.0 | PHP, self-hosted, actively maintained. Single-business oriented; no managed-user model, no native Google multi-tenant OAuth. |
| **calrs** | 195 · AGPL-3.0 | Cal.com in Rust. Fast and interesting, but far too young to bet a product on. |
| **someday** | 1.1k · MIT | Availability picker on Google Calendar. Too thin — no booking management. |
| **Calendly** | Commercial | Fonio supports it, but their API is weaker for embedded multi-tenant use and pricing is per-seat. Worth supporting as a *customer-provided link*, not as our engine. |

---

## Recommendation

**Two-tier approach.**

**Tier 1 — ship this week: customer pastes their own link.**
Let the customer paste a Cal.com or Calendly booking link during onboarding. The assistant reads availability from it or simply texts the link. Almost no engineering, works immediately, and covers SMBs who already use one.

**Tier 2 — the real product: Cal.com Platform managed users.**
Full integration: managed user per customer, `Connect.GoogleCalendar` in our dashboard, `check_availability` and `book_appointment` as function tools. This is the version that feels native and beats Fonio.

**Don't self-host Cal.diy** unless per-booking pricing turns out to be prohibitive at our volumes — and if we do, be honest that we're taking on building multi-tenancy ourselves.

---

## Before committing

1. **Get real Platform pricing from Cal.com sales.** The $0.50–0.99/booking figure comes from third-party pricing round-ups, not Cal.com's own docs. At scale this is the deciding number.
2. **Confirm managed users are not in Cal.diy.** The README says enterprise features were removed; I did not verify the codebase directly. If managed users *did* survive the fork, self-hosting becomes far more attractive.
3. **Test slot-lookup latency from n8n.** Needs to stay under ~3s inside the tool call.
4. **Check India/UAE timezone and locale handling** — voice bookings say "Thursday at 2", and the mapping to a correct UTC instant is where schedulers usually break.

---

## References

- [Cal.com Platform](https://cal.com/platform) · [Quickstart — OAuth client & managed users](https://cal.com/docs/platform/quickstart) · [API v2 reference](https://cal.com/docs/api-reference/v2/introduction)
- [calcom/cal.diy](https://github.com/calcom/cal.diy) (MIT fork) · [Cal.com examples](https://github.com/calcom/examples)
- [Easy!Appointments](https://github.com/alextselegidis/easyappointments)
