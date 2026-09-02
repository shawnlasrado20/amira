# Mid-Call Actions: Tool Calling with AgenticFlow + n8n

**Status:** Proposal · **Date:** July 2026
**Researched against:** AgenticFlow `openapi.yaml` (tool + webhook schemas), n8n node documentation, current RENI repo

---

## The problem

Today the assistant can *talk* about booking an appointment, but it can't actually **do** anything mid-call.

Confirmed in the RENI repo:

- **No tool-creation workflow exists.** Nothing in `setup/n8n-workflows/` ever calls `POST /tool`. Grep for `agenticflow.studio/tool` returns nothing.
- **The assistant is created with no tools attached.** `create-assistant.json` and `update-assistant.json` never send a `tools` field.
- **The dashboard shows abilities that don't exist.** "Book appointments", "Send SMS", "Send email", "Transfer calls" are UI rows with nothing behind them.
- **Notifications are post-call only.** `end-of-call-relay.json` runs `End of Call Report → … → Send Email`. It fires *after the caller hangs up*.

So a caller books a slot, finishes the call, and only then does anything happen. That's the bug.

---

## The mechanism that fixes it

AgenticFlow supports **function tools**. When the assistant's LLM decides to call one, AgenticFlow makes an HTTP POST to that tool's own `server.url` — **and that URL can be an n8n webhook.**

From the spec (`FunctionTool` schema):

```yaml
FunctionTool:
  required: [function, server]
  properties:
    name:        # display name; also the function name the LLM sees
    function:    # FunctionDefinition — name, description, JSON-schema parameters
    server:      # ServerConfig
    messages:    # ToolMessage[] — what the assistant says while it runs
    asyncMode:   # bool, default false
    folderId:
    metadata:
```

```yaml
ServerConfig:
  url:             # our n8n webhook
  secret:          # for request signing
  headers:         # merged into every request
  timeoutSeconds:  # default 20
```

**Two execution modes:**

| Mode | Behaviour | Use for |
|---|---|---|
| `asyncMode: false` *(default)* | **The LLM blocks and waits.** Your reply becomes the tool result, which the assistant then speaks. | Anything the caller needs an answer to — availability, booking confirmation, order status |
| `asyncMode: true` | Fire-and-forget. LLM gets an instant ack, your reply is discarded. | Logging, CRM writes, follow-ups nobody is waiting on |

**20 seconds** is the default timeout — generous. A Google Calendar check plus a Twilio SMS is comfortably under 2 seconds.

### Bonus: the assistant can talk while it works

`ToolMessage` has `type`, `content`, `blocking`, and `timingMilliseconds`. So you can configure:

- **on start:** *"Let me check the calendar for you…"*
- **if slow (after N ms):** *"Still checking, one moment…"*
- **on failure:** *"I'm having trouble reaching the calendar — can I take your number and call you back?"*

That's what makes it feel human rather than like dead air.

---

## What this makes possible

The flow you described, working properly:

```
Caller: "Can I book Thursday at 2?"
   │
   ├─ LLM calls check_availability          [sync, ~600ms]
   │    → n8n → Google Calendar → free/busy
   │    ← "Thursday 2pm and 4pm are open"
   │
Assistant: "Thursday at 2 works. Can I get your name and number?"
   │
   ├─ LLM calls book_appointment            [sync, ~1.2s]
   │    → n8n → create calendar event
   │           → send SMS confirmation      ← ARRIVES NOW, mid-call
   │           → respond to webhook
   │    ← "Booked. Confirmation sent."
   │
Assistant: "Done — you're booked for Thursday at 2, and I've just
            texted you the confirmation."
   │
   └─ n8n continues after responding: send email, write to CRM
```

The caller's phone buzzes **while they're still on the call.** That's the moment that sells the product.

---

## Tool catalog to build

| Tool | Mode | What n8n does | Assistant can say |
|---|---|---|---|
| `check_availability` | sync | Google Calendar free/busy, or Cal.com slots | "Thursday 2pm or Friday morning" |
| `book_appointment` | sync | Create event → send SMS → respond → then email | "Booked, just texted you" |
| `cancel_reschedule` | sync | Find event, move or delete, notify | "Moved to Friday, confirmation sent" |
| `send_details` | **async** | SMS the address / menu / price list | "Sending that to you now" |
| `lookup_customer` | sync | CRM / sheet lookup by phone number | "Welcome back — same address?" |
| `check_order_status` | sync | Query orders DB | "Your order ships tomorrow" |
| `take_message` | **async** | Write to CRM + email the owner | "I'll pass that on right away" |
| `capture_lead` | **async** | Push to CRM, tag source | (silent) |

Plus AgenticFlow's native **transfer** tool — which supports a *dynamic destination resolver*: when the requested destination doesn't match a static one, it calls your endpoint with `function.name = "get_transfer_destination"` and you reply with `{"destination": {...}}`. So n8n can decide who to transfer to at runtime — on-call doctor, whoever's free, department by topic.

---

## The n8n workflow pattern

The key trick for sync tools: **respond as soon as you have the answer, then keep working.**

n8n's `Respond to Webhook` node sends the response and the workflow *continues executing*. So:

```
Webhook (responseMode: responseNode)
  → Verify signature
  → Resolve tenant  (assistantId → customer → their calendar credentials)
  → Check calendar
  → Create event
  → Send SMS                      ← ~400ms, do it BEFORE responding
  → RESPOND TO WEBHOOK            ← LLM unblocks, assistant speaks
  → Send email                    ← after; nobody checks email in 3 seconds
  → Write to CRM
  → Log
```

**Why SMS before the response:** so the assistant can truthfully say *"I've just texted you."* Twilio's send is ~300–500ms — negligible inside a 20-second budget, and it makes the claim honest.

**Why email after:** nobody opens email mid-call. Don't spend latency on it.

---

## Multi-tenant considerations

This is the part that needs care, and it's easy to get wrong.

### One shared tool, tenant resolved at runtime

Don't create a separate tool per customer. Create **one** `book_appointment` tool and attach it to every assistant. The webhook payload includes call context (`call.assistantId`), so n8n resolves:

```
assistantId → our DB → customer → their calendar + notification settings
```

One tool definition, hundreds of customers.

### ⚠️ The credential problem

**n8n's built-in Google Calendar node uses a single configured credential.** That's fine for one calendar. It does **not** work for 500 customers each with their own Google account.

For multi-tenant you need:

- Each customer **OAuth-connects their calendar** during onboarding
- We store their refresh token (encrypted) in our DB
- n8n uses the **HTTP Request node** with a token fetched per-request — *not* the built-in Google Calendar node

Same pattern for Cal.com (API key per user) and any CRM.

This is a real piece of work — OAuth flow, token storage, refresh handling — and it's the main reason "book appointments" isn't a weekend feature.

**Simpler v1 alternative:** let customers paste a **Cal.com booking link** or API key rather than full OAuth. Much less to build, covers most SMBs, and you can add native Google OAuth later.

---

## Reliability and safety

| Concern | Handling |
|---|---|
| **Duplicate calls** | LLMs sometimes call a tool twice. Make booking idempotent — dedupe on `(callId, slot)` and return the existing booking rather than double-booking. |
| **Failures** | Never return a raw error. Return something speakable: `{"error": "calendar unavailable", "say": "I can't reach the calendar right now — can I take your number?"}` The LLM will say it. |
| **Timeouts** | Keep sync tools under ~3s. If an integration is slow, respond with "I've started that" and finish async. |
| **Request signing** | `ServerConfig.secret` exists — use it. Verify the signature in n8n's first node so nobody else can POST to your booking webhook. |
| **Wrong-tenant writes** | Resolve the tenant from `assistantId` on **every** request and scope all downstream calls to it. Never trust an id passed in the tool arguments. |
| **Hallucinated arguments** | Validate against the JSON schema before acting. If the LLM invents a date of "next Tuesdayish", reject and let it re-ask. |

---

## Suggested build order

**Phase 1 — prove the loop (~3 days)**
Build one tool end to end: `check_availability`, sync, hardcoded to a single test calendar. Create it via `POST /tool`, attach to a test assistant, call in, ask about availability, confirm the assistant speaks a real answer. This validates the whole mechanism before any multi-tenant work.

**Phase 2 — booking + mid-call notifications (~1 week)**
`book_appointment` with the respond-then-continue pattern. SMS before response, email after. Add `ToolMessage` filler phrases so there's no dead air. This is the demo moment — caller's phone buzzes mid-call.

**Phase 3 — multi-tenant credentials (~1–2 weeks)**
Cal.com link/API key first (cheap), Google OAuth after. Per-customer token storage and refresh. Tenant resolution from `assistantId`.

**Phase 4 — the rest of the catalog (~1 week)**
`send_details`, `take_message`, `capture_lead`, `lookup_customer` — mostly async and much simpler once the pattern is established.

**Phase 5 — wire the dashboard**
The ability rows already exist in the UI. Make toggling "Book appointments" actually attach the tool to that customer's assistant via `PATCH /assistant`.

---

## Why this matters competitively

Fonio's pitch is that the assistant *does things*, not just answers. Right now our assistant talks and then a summary email arrives later — which reads as a demo, not a product.

Mid-call tool calls are what turn it into a receptionist: the caller hears "booked, just texted you," feels the phone buzz, and hangs up with proof. That single moment is worth more than any feature list on the pricing page.

---

## Open questions

1. **Are there rate limits on tool calls?** Undocumented. A busy assistant could fire several per call.
2. **Does `timeoutSeconds` cap above 20?** Default is 20; unclear whether it can be raised for slow integrations.
3. **Cal.com vs Google Calendar first?** Cal.com is far cheaper to integrate multi-tenant (API key vs full OAuth). Worth deciding before Phase 3.
4. **Does the transfer tool's dynamic resolver share the 20s budget?** It uses the same payload shape — assume yes until confirmed.

---

## References

- AgenticFlow — [Tool function call webhook](https://docs.agenticflow.studio/api-reference/webhooks/tool-function-call), [Create Tool](https://docs.agenticflow.studio/api-reference/tool/create-tool)
- n8n — [Respond to Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.respondtowebhook), [Webhook](https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.webhook), [Google Calendar](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.googlecalendar), [Twilio](https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.twilio)
