# n8n workflows

## Current (Pipecat backend)

| file | workflow | webhook path | purpose |
|------|----------|--------------|---------|
| `start-pipecat-session.json` | AMIRA - Start Pipecat Session | `/webhook/amira-start` | creates a voice session (frontend → Pipecat `POST /start`), returns `{success, sessionId, iceConfig}` |

The frontend then does the WebRTC SDP handshake **directly** with Pipecat at
`POST http://localhost:8000/sessions/{sessionId}/api/offer` — n8n is only in the
loop for session creation (and future post-call logging).

### Import (Docker n8n)

If n8n runs in Docker (container name may differ):

```bash
docker cp start-pipecat-session.json <container>:/tmp/wf.json
docker exec <container> n8n import:workflow --input=/tmp/wf.json
docker restart <container>
```

Notes:
- The HTTP Request node targets `http://host.docker.internal:8000/start` because
  n8n-in-Docker can't reach the Mac host via `localhost`. If n8n runs directly on
  the host, change it to `http://localhost:8000/start`.
- No credential needed — Pipecat has no auth (localhost only).
- If the CLI import hits `SqliteWriteConnectionMutex` timeouts or the workflow
  won't activate, import via the n8n UI instead (Workflows → Import from File),
  then toggle it active.

## Legacy (AgenticFlow era — no longer used)

| file | workflow | webhook path | purpose |
|------|----------|--------------|---------|
| `outbound-call.json` | AMIRA - Outbound Call (Webhook API) | `/webhook/amira-call` | placed phone demo calls (frontend → AgenticFlow `POST /call`) |
| `update-assistant.json` | AMIRA - Update Assistant | `/webhook/amira-update-assistant` | updated the assistant system prompt (`PATCH /assistant/{id}`) |

Kept for reference. They require an AgenticFlow `X-Api-Key` Header Auth credential
and account-specific assistant/phone-number IDs — see `../../CLAUDE.md`.
