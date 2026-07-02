# n8n workflows

Exported from n8n (v2.7.5). These are the two **active** workflows behind AMIRA.

| file | workflow | webhook path | purpose |
|------|----------|--------------|---------|
| `outbound-call.json` | AMIRA - Outbound Call (Webhook API) | `/webhook/amira-call` | places the demo call (frontend → AgenticFlow `POST /call`) |
| `update-assistant.json` | AMIRA - Update Assistant | `/webhook/amira-update-assistant` | updates the assistant system prompt (`PATCH /assistant/{id}`) |

## Import

```bash
n8n import:workflow --input=outbound-call.json
n8n import:workflow --input=update-assistant.json
```

Then, in n8n:

1. Open each workflow → the **HTTP Request** node → set its **Header Auth** credential.
   Create one of type *Header Auth* with **Name** `X-Api-Key` and **Value** = your
   AgenticFlow API key. (The exported JSON references a credential by id/name only —
   the actual key is never included.)
2. Confirm the assistant id / phone number id in the code node match your account.
3. **Activate** each workflow.

> Note: importing via CLI while n8n is running deactivates the workflow; publish it and
> restart the n8n process for changes to take effect. See `../../CLAUDE.md` for the exact
> restart pattern and all account-specific IDs.
