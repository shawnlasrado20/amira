# Multi-Tenant Architecture on AgenticFlow

**Status:** Proposal · **Date:** July 2026
**Verified against:** `docs.agenticflow.studio` (189 API reference pages + full `openapi.yaml`)

---

## TL;DR

Self-serve signup **works** — fonio-style: pick a plan, pick a template, add business details, go live. No human touches AgenticFlow's dashboard.

The unlock is that AgenticFlow supports **folders** and **metadata** on every resource. One org holds all customers; each customer gets their own folder. That's the tenant boundary.

Two hard constraints to design around:

1. **There is no API to create an organization.** Orgs are made by hand in AgenticFlow's dashboard. So we run **one** org, not one-per-customer.
2. **AgenticFlow does not sell phone numbers.** `POST /phone-number` requires you to already own the number (your Twilio credentials or a SIP trunk). We pre-buy a pool.

---

## What the API actually gives us

Verified directly in the OpenAPI spec:

| Capability | Confirmed |
|---|---|
| `POST /assistant` accepts `folderId` | Yes |
| `POST /assistant` accepts free-form `metadata` object | Yes |
| `FolderResourceType` enum | `assistant`, `phone_number`, `tool`, `file` |
| `GET /assistant?folderId=…` filters by folder | Yes |
| `GET /assistant` pagination | `skip`, `limit`, `search` |
| `POST /organization` or `/workspace` | **Does not exist** |
| Number search / purchase endpoint | **Does not exist** |

The full list of API resources is: `/assistant`, `/call`, `/chat`, `/file`, `/folders`, `/knowledge-base`, `/messaging`, `/phone-number`, `/sip-trunk`, `/tool`, `/widget`.

Auth is a **workspace-scoped API key** (`X-Api-Key` header). Per the spec: *"Keys are scoped to a single workspace."* There is no header to switch org context per request.

---

## The model: one org, one folder per customer

```
AgenticFlow org — "Amira Production"      ← one API key, ours, server-side only
│
├─ folder: cust_8f2a · Sunrise Bakery      resourceType=assistant
│   └─ assistant "Reception"               metadata:{ customer_id: "cust_8f2a" }
│
├─ folder: cust_8f2a · Sunrise Bakery      resourceType=phone_number
│   └─ +971 4 xxx xxxx                     → routes to their assistant
│
├─ folder: cust_3b91 · Dr. Khan Clinic     resourceType=assistant
│   └─ assistant "Front Desk"              metadata:{ customer_id: "cust_3b91" }
│
└─ folder: cust_…                          one per customer, created at signup
```

**Three rules:**

- **The folder is the tenant boundary.** Created automatically at signup via `POST /folders`.
- **Metadata is the backup index.** Stamping `customer_id` on each assistant means ownership stays readable from the object itself, even if a folder is renamed or something is moved.
- **Our database is the source of truth.** Never list-and-scan AgenticFlow to determine ownership. Store the mapping on our side; use folders for structure and operator sanity.

---

## Signup flow — fully automated

| # | Step | API call |
|---|---|---|
| 1 | Customer picks plan and pays | Razorpay (India) / Stripe (UAE) — our stack |
| 2 | Create their folders (assistant + phone_number) | `POST /folders { resourceType, name }` |
| 3 | Customer picks a template (restaurant / clinic / salon) and fills in business details → we create the assistant in their folder | `POST /assistant { …, folderId, metadata:{customer_id} }` |
| 4 | Attach a number from our pre-bought pool, pointed at their assistant | `POST /phone-number { number, twilioAccountSid, twilioAuthToken, assistantId, folderId }` |
| 5 | Live — customer configures in the dashboard | existing dashboard |

Every step is an API call. Nothing waits on a human.

---

## Running it day to day

| Concern | How it's handled |
|---|---|
| Which assistant belongs to whom | Our DB maps `customer_id → assistant_id`. Folder + metadata mirror it in AgenticFlow as a cross-check. |
| Preventing cross-tenant access | Every request resolves `customer_id` from the session, then only touches ids owned by that customer. This check lives in **one** place. |
| Per-customer usage & billing | `GET /call` filtered to their assistant ids; sum durations into a usage table; enforce plan caps from it. |
| Operator view | Folders make AgenticFlow's own dashboard navigable per customer — no DB query needed to eyeball a setup. |
| Listing at scale | Always query one folder (`folderId` + `skip`/`limit`), never the whole org. |
| Offboarding | Delete the folder with cascade, release the number back to the pool, mark the row inactive. |

---

## Risks

### Isolation is enforced by our code, not by AgenticFlow
Folders organize; they do **not** enforce. AgenticFlow will happily return customer B's assistant to customer A's session if we ask it to. One missed ownership filter leaks data between customers.

**Mitigation:** put the ownership check in a single thin API service rather than duplicating it across 13 n8n workflows. One place to get right, one place to audit.

### One key, full blast radius
The workspace key can read and delete every customer's data.

**Mitigation:** key stays server-side only — never in the browser, never behind an unauthenticated webhook. Rotate on any suspicion of exposure.

### Rate limits are undocumented
The spec returns `429`s but publishes no numbers. Fine at 10 customers; unknown at 500.

**Mitigation:** ask AgenticFlow directly. Build retry-with-backoff regardless.

### Phone number inventory
Signup stalls the moment the pool runs dry — numbers can't be bought instantly because India and UAE require Twilio KYC bundles (identity documents, in-country address). Numbers without them get disconnected by carriers.

**Mitigation:** alert below a threshold and buy in batches ahead of demand. Keep free trials **browser-only** (the existing LiveKit web-call path) so trials don't consume numbers.

---

## Graduation path: dedicated orgs for enterprise

Some clients will contractually require their data in a separate workspace. That's fine — create the org by hand and store its API key against their account.

**Design for this now:** make the API key a nullable per-customer field in our schema from day one. It stays `null` for every self-serve customer and gets populated only for enterprise. Costs nothing today; avoids a painful migration later.

---

## Open questions for AgenticFlow

1. **Is there a partner / reseller API for creating organizations?** The public docs have none, but platforms often expose provisioning privately. If it exists, org-per-customer becomes viable and this design changes.
2. **What are the rate limits, and is there a max assistants-per-org?** These decide whether one org holds at scale.
3. **Can multiple numbers in one org route to different assistants?** The schema implies yes (`assistantId` is a field on the phone number), but this is the linchpin — worth a real test before building on it.

---

## Appendix: what does *not* work

For the record, so nobody re-proposes these:

- **"Customer pays → their org appears automatically."** No org-creation endpoint exists.
- **"We assign them a number instantly at signup."** Only from a pre-bought pool. AgenticFlow can't buy numbers.
- **"Ask the customer for their own Twilio credentials."** Technically supported (`provider: twilio`), but asking an SMB owner to create a Twilio account and paste API credentials will kill conversion. Keep as an option for technical customers, not the default path.
