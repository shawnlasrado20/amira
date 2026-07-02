# AMIRA — Project Context & Handoff

> Read this first. It captures everything built so far, all the IDs/endpoints,
> the gotchas, and what's left. Written for a fresh Claude session to continue cold.

## What this project is

A fonio.ai-style **AI phone receptionist** product called **AMIRA**.
- **AgenticFlow** (`api.agenticflow.studio`) = the voice engine (assistants + phone numbers + call execution). We do NOT use its dashboard in the product.
- **n8n** (local, `localhost:5678`) = the backend/orchestration layer (webhooks → AgenticFlow API).
- **Custom static frontend** (`localhost:3000`) = the UI (plain HTML/CSS/JS, served by `npx serve`).

Data flow for the demo call:
```
frontend (index.html)  →  n8n webhook /amira-call  →  AgenticFlow POST /call  →  real phone rings
```

## File structure

```
/Users/abhaykamath/Desktop/AMIRA/
├── CLAUDE.md               ← this file
├── .env                    ← AGENTICFLOW_API_KEY (BLANK — user pastes; do NOT read it)
├── .env.example            ← safe template
├── .gitignore              ← ignores .env, .DS_Store, node_modules
├── .claude/launch.json     ← preview config: `npx serve -l 3000 frontend`
├── frontend/
│   ├── index.html          ← main product + demo page (header/hero/how-it-works/demo/features/pricing/footer)
│   ├── admin.html          ← internal: update assistant system prompt (has restaurant/clinic/realestate presets)
│   └── calls.html          ← internal: call-log table (5 HARDCODED sample rows)
└── setup/demo-prompts/
    ├── restaurant.txt
    ├── clinic.txt
    └── realestate.txt
```

Note: `serve` serves the `frontend/` dir as web root, so pages are at
`http://localhost:3000/index.html`, `/admin.html`, `/calls.html` (NOT `/frontend/...`).

## AgenticFlow reference

- Base URL: `https://api.agenticflow.studio`
- Auth: header `X-Api-Key: <key>` (docs at `docs.agenticflow.studio`)
- API is Vapi-shaped. Endpoints used so far: `POST /call`, `PATCH /assistant/{id}`,
  `POST /assistant`, `GET /assistant`, `GET /assistant/{id}`, `GET /call`, `GET /call/{id}`.

### Assistants in the account
| id | name | type | notes |
|----|------|------|-------|
| `c428c7f1-65bc-4207-8728-f08a214f2361` | AMIRA Demo - Restaurant | **pipeline / gold** | ✅ **ACTIVE demo target.** Works over the phone. voiceCardId `D9Thk1W7FRMgiOhy3zVI`, tierLanguage `en`. |
| `28d3ea61-...` | test bot | realtime / premium / holly | ❌ one-way audio on phone. Not used. |
| `fa73bb2d-...` | SGFX Outbound Test | realtime / premium / holly | ❌ original bot, one-way audio. Not used. |
| others | ForwardingTest, Outbound Hindi/Arabic/English | pipeline | pre-existing, SGFX trading content. |

**CRITICAL LEARNING:** `realtime` + `holly` voice assistants produce audio that does
NOT transcode onto the phone trunk → caller hears silence (but AgenticFlow's live
monitor plays it fine, which is misleading). **Use `pipeline`-type assistants for
telephony.** That's why the demo uses `c428c7f1…`.

### Phone number
- `6c8af7df-44de-447b-8c5e-73531fa072b6` — the outbound caller. Twilio SIP trunk
  (`af-...pstn.twilio.com`, trunk number `+493075936398`). This is the number that
  calls people; customers only enter their OWN number to receive the demo call.

## n8n reference

- Version 2.7.5, running locally on `:5678`, data in `~/.n8n` (sqlite).
- Credential: `Cr9PkI6wGX0golpr` = **"Header Auth account"** (type `httpHeaderAuth`),
  holds `X-Api-Key` = the AgenticFlow key. All workflows authenticate via this.

### Workflows
| id | name | state | webhook path | purpose |
|----|------|-------|--------------|---------|
| `BnpfV9RbpJexj8P3` | AMIRA - Outbound Call (Webhook API) | **active** | `/webhook/amira-call` | places demo calls |
| `7AGRTASxiqtHCxg9` | AMIRA - Update Assistant | **active** | `/webhook/amira-update-assistant` | PATCHes assistant systemPrompt |
| `QwfkMLbiLV39AsBy` | AMIRA - Outbound Call (Form UI) | parked | — | superseded, ignore/delete |
| `2ePlDJICQ9vZd4NB` | AMIRA - Book Appointment Tool | parked | — | incomplete inbound idea |

**Outbound Call workflow nodes:** Webhook → `Normalize Number & Build Payload`
(code: E.164 normalize, defaults `+971`; injects assistantId `c428c7f1…` + phoneNumberId
`6c8af7df…`) → `Place Call (POST /call)` (HTTP, credential `Cr9PkI6wGX0golpr`,
`onError: continueRegularOutput`) → `Format API Response` → `Respond to Frontend`.

Response contract (frontend depends on this):
- success: `{ success:true, callId, message:"AMIRA is calling you now", estimatedRingTime:"10 seconds" }`
- error: `{ success:false, error:"Could not initiate call", details:"<actual error>" }`

**Update Assistant workflow nodes:** Webhook → `Build Patch Body` (prepends businessName
into prompt; target assistantId defaults to `c428c7f1…`, overridable via body.assistantId)
→ `Update Assistant (PATCH)` (`PATCH /assistant/{id}`, sends only `{systemPrompt}`) →
`Format Result` → `Respond to Admin`. Returns `{success:true, message:"Assistant updated successfully"}`.

### ⚠️ n8n CLI restart quirk (IMPORTANT)
Editing workflows via CLI while n8n is running: `n8n import:workflow` **deactivates**
the workflow, and changes don't take effect until n8n restarts. The working pattern:
```
n8n import:workflow --input=<file>.json
n8n publish:workflow --id=<id>
# then restart the running process:
PID=$(lsof -ti :5678 -sTCP:LISTEN); kill $PID
# wait for port free, then:
nohup n8n start > /tmp/n8n.log 2>&1 & disown
# confirm: grep "Activated workflow" /tmp/n8n.log
```
Editing a node's credential link or code via CLI + this restart is how all workflow
changes were applied (the browser UI needs login which we avoided).

## Working agreements with the user (RESPECT THESE)

1. **Do NOT read or use the AgenticFlow API key, and do NOT call the AgenticFlow API
   directly, without asking permission first and explaining what you're about to do.**
   The key lives in the n8n credential; earlier in the project it was read via
   `n8n export:credentials --all --decrypted` for setup/debugging — the user has since
   asked to stop that.
2. **Assistant changes are the user's to run.** Give them the exact command or the
   admin-page steps; let them click. The `Update Assistant` workflow exists precisely
   so they self-serve (n8n uses the credential, not you).
3. `.env` is the user's canonical key store — created blank on purpose; never fill it.

## Cost note
Real calls cost ~€0.52 each (UAE mobile termination + STT/LLM/TTS, pipeline/gold voice
is pricier). Earlier automated wiring/test calls to fake numbers also incurred charges —
avoid automated real calls; let the user drive real calls from the frontend.

## Verified working
- Full outbound chain: frontend → n8n → AgenticFlow → real two-way phone conversation.
- All 3 pages render (checked in browser). Admin template presets populate fields.
- Both workflows active.

## Known gaps / next steps
- **Call log is sample data.** To make it live: add an AgenticFlow `end-of-call-report`
  webhook → n8n → store calls → serve to `calls.html` (needs n8n publicly reachable;
  `ngrok` is installed on the machine).
- **`.env` isn't wired into anything** — the live key is only in the n8n credential.
- **Suggested: rotate the AgenticFlow key** (it was read during early setup) and paste
  the fresh one into the n8n credential + `.env`.
- Parked workflows (`QwfkMLbiLV39AsBy`, `2ePlDJICQ9vZd4NB`) can be deleted.

## The build (all 4 phases complete)
1. n8n clean JSON response contract (above).
2. Full product landing page (`index.html`).
3. Admin page + `Update Assistant` workflow + 3 demo prompt files.
4. Call-log page (`calls.html`) + Admin link in main header (→ calls.html).
