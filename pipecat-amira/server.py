"""
FastAPI server for the Amira Pipecat bot.

Implements the standard pipecat RTVI two-step flow expected by the
SmallWebRTCPrebuiltUI client (v2.5+):

  1. POST /start  → registers a session, returns {sessionId, iceConfig}
  2. POST /sessions/{session_id}/api/offer  → WebRTC SDP handshake
  3. PATCH /sessions/{session_id}/api/offer → trickle ICE candidates

GET /          → cost dashboard (shows live metrics + "Open Voice UI" button)
GET /client/   → prebuilt WebRTC mic/connect UI
GET /metrics   → JSON cost metrics for the running server
"""

import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from http import HTTPMethod
from textwrap import dedent
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from loguru import logger
from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI

from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import IceServer, SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

import bot

load_dotenv()

# ---------------------------------------------------------------------------
# Cost rates (INR)
# Sarvam STT saarika:v2.5  ≈ ₹30 / hour  → ₹0.50 / min
# Sarvam TTS bulbul:v3     ≈ ₹30 / 10 k chars; ~600 chars/min → ₹1.80 / min
# Gemini 2.5 Flash         free tier / essentially ₹0
# SmallWebRTC              self-hosted, ₹0
# ---------------------------------------------------------------------------
RATE_STT_PER_MIN = 0.50
RATE_TTS_PER_MIN = 1.80
RATE_LLM_PER_MIN = 0.00
RATE_TOTAL_PER_MIN = RATE_STT_PER_MIN + RATE_TTS_PER_MIN + RATE_LLM_PER_MIN

# active_sessions: session_id → request body (from /start)
active_sessions: dict[str, dict[str, Any]] = {}

# pcs_map: pc_id → SmallWebRTCConnection (for renegotiation)
pcs_map: dict[str, SmallWebRTCConnection] = {}

# sessions_log: list of {start_time, end_time|None}
sessions_log: list[dict[str, float | None]] = []

ice_servers = [IceServer(urls="stun:stun.l.google.com:19302")]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await asyncio.gather(*(pc.disconnect() for pc in pcs_map.values()))
    pcs_map.clear()
    active_sessions.clear()


app = FastAPI(title="Amira Pipecat Server", lifespan=lifespan)

# The product frontend (localhost:3000) posts SDP offers to /sessions/{id}/api/offer
# from a different origin, so cross-origin requests must be allowed. Localhost-only
# today; tighten allow_origins when this is deployed anywhere public.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/client", SmallWebRTCPrebuiltUI)


# ---------------------------------------------------------------------------
# Cost dashboard HTML
# ---------------------------------------------------------------------------
DASHBOARD_HTML = dedent("""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Amira — Cost Dashboard</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #0f0f13;
      color: #e2e8f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 2.5rem 1rem;
    }
    h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.5px; }
    .subtitle { color: #94a3b8; font-size: 0.9rem; margin-top: 0.3rem; margin-bottom: 2rem; }
    .card {
      background: #1a1a24;
      border: 1px solid #2d2d3d;
      border-radius: 12px;
      padding: 1.5rem;
      width: 100%;
      max-width: 560px;
      margin-bottom: 1rem;
    }
    .card h2 { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; margin-bottom: 1rem; }
    .rate-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 0.5rem 0;
      border-bottom: 1px solid #2d2d3d;
      font-size: 0.92rem;
    }
    .rate-row:last-child { border-bottom: none; }
    .rate-row .label { color: #cbd5e1; }
    .rate-row .value { font-weight: 600; color: #a78bfa; }
    .rate-row.total .label { color: #e2e8f0; font-weight: 700; }
    .rate-row.total .value { color: #34d399; font-size: 1.05rem; }
    .stat-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 1rem;
    }
    .stat { text-align: center; }
    .stat .num { font-size: 2rem; font-weight: 700; color: #a78bfa; line-height: 1; }
    .stat .lbl { font-size: 0.75rem; color: #64748b; margin-top: 0.3rem; }
    .stat .num.green { color: #34d399; }
    .comparison { font-size: 0.82rem; color: #64748b; margin-top: 0.75rem; text-align: center; }
    .comparison span { color: #f87171; }
    .comparison strong { color: #34d399; }
    .btn {
      display: block;
      width: 100%;
      max-width: 560px;
      padding: 0.9rem;
      background: linear-gradient(135deg, #7c3aed, #4f46e5);
      color: #fff;
      font-size: 1rem;
      font-weight: 600;
      text-align: center;
      border-radius: 10px;
      text-decoration: none;
      margin-top: 0.5rem;
      transition: opacity 0.15s;
    }
    .btn:hover { opacity: 0.88; }
    .live-badge {
      display: inline-block;
      width: 8px; height: 8px;
      background: #34d399;
      border-radius: 50%;
      margin-right: 6px;
      animation: pulse 1.5s infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
    }
    .note { font-size: 0.75rem; color: #475569; margin-top: 1.5rem; max-width: 560px; text-align: center; }
  </style>
</head>
<body>
  <h1>🎙️ Amira</h1>
  <p class="subtitle">Tamil restaurant receptionist · Self-hosted Pipecat</p>

  <div class="card">
    <h2>Cost per minute</h2>
    <div class="rate-row">
      <span class="label">Sarvam STT (saarika:v2.5)</span>
      <span class="value">₹0.50 / min</span>
    </div>
    <div class="rate-row">
      <span class="label">Sarvam TTS (bulbul:v3 · ishita)</span>
      <span class="value">₹1.80 / min</span>
    </div>
    <div class="rate-row">
      <span class="label">Gemini 2.5 Flash (LLM)</span>
      <span class="value">₹0.00 (free tier)</span>
    </div>
    <div class="rate-row">
      <span class="label">WebRTC transport</span>
      <span class="value">₹0.00 (self-hosted)</span>
    </div>
    <div class="rate-row total">
      <span class="label">Total</span>
      <span class="value">₹2.30 / min</span>
    </div>
    <p class="comparison">
      vs AgenticFlow: <span>€0.26 / min (~₹23)</span> → self-hosted is <strong>~10× cheaper</strong>
    </p>
  </div>

  <div class="card">
    <h2><span class="live-badge"></span>This session (live)</h2>
    <div class="stat-grid">
      <div class="stat">
        <div class="num" id="total-calls">—</div>
        <div class="lbl">Total calls</div>
      </div>
      <div class="stat">
        <div class="num" id="total-mins">—</div>
        <div class="lbl">Total minutes</div>
      </div>
      <div class="stat">
        <div class="num green" id="total-cost">—</div>
        <div class="lbl">Est. cost (₹)</div>
      </div>
    </div>
  </div>

  <a href="/client/" class="btn">Open Voice Interface →</a>

  <p class="note">
    Metrics auto-refresh every 3 s. Costs are estimates based on Sarvam published rates.<br>
    TTS cost assumes ~600 chars / min of spoken output.
  </p>

  <script>
    async function refresh() {
      try {
        const r = await fetch('/metrics');
        const d = await r.json();
        document.getElementById('total-calls').textContent = d.total_sessions;
        document.getElementById('total-mins').textContent = d.total_minutes.toFixed(1);
        document.getElementById('total-cost').textContent = '₹' + d.estimated_cost_inr.toFixed(2);
      } catch(e) {}
    }
    refresh();
    setInterval(refresh, 3000);
  </script>
</body>
</html>
""")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics():
    now = time.time()
    total_minutes = sum(
        ((s["end_time"] or now) - s["start_time"]) / 60
        for s in sessions_log
    )
    active = sum(1 for s in sessions_log if s["end_time"] is None)
    return {
        "total_sessions": len(sessions_log),
        "active_sessions": active,
        "total_minutes": round(total_minutes, 2),
        "estimated_cost_inr": round(total_minutes * RATE_TOTAL_PER_MIN, 2),
        "rates": {
            "stt_per_min_inr": RATE_STT_PER_MIN,
            "tts_per_min_inr": RATE_TTS_PER_MIN,
            "llm_per_min_inr": RATE_LLM_PER_MIN,
            "total_per_min_inr": RATE_TOTAL_PER_MIN,
        },
    }


# ---------------------------------------------------------------------------
# RTVI /start endpoint
# ---------------------------------------------------------------------------
@app.post("/start")
async def start_session(request: Request):
    try:
        request_data = await request.json()
    except Exception:
        request_data = {}

    session_id = str(uuid.uuid4())
    active_sessions[session_id] = request_data.get("body", {})
    logger.info(f"Session registered: {session_id}")

    result: dict[str, Any] = {"sessionId": session_id}
    if request_data.get("enableDefaultIceServers"):
        result["iceConfig"] = {
            "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
        }
    return result


# ---------------------------------------------------------------------------
# WebRTC offer handling
# ---------------------------------------------------------------------------
async def _handle_offer(request_data: dict, background_tasks: BackgroundTasks):
    pc_id = request_data.get("pc_id")

    if pc_id and pc_id in pcs_map:
        connection = pcs_map[pc_id]
        logger.info(f"Renegotiating existing connection pc_id={pc_id}")
        await connection.renegotiate(
            sdp=request_data["sdp"],
            type=request_data["type"],
            restart_pc=request_data.get("restart_pc", False),
        )
    else:
        connection = SmallWebRTCConnection(ice_servers)
        await connection.initialize(sdp=request_data["sdp"], type=request_data["type"])

        language = request_data.get("language", "hi")

        session_entry: dict[str, float | None] = {
            "start_time": time.time(),
            "end_time": None,
        }
        sessions_log.append(session_entry)

        @connection.event_handler("closed")
        async def handle_disconnected(webrtc_connection: SmallWebRTCConnection):
            session_entry["end_time"] = time.time()
            duration = (session_entry["end_time"] - session_entry["start_time"]) / 60
            cost = duration * RATE_TOTAL_PER_MIN
            logger.info(
                f"Connection closed pc_id={webrtc_connection.pc_id} "
                f"duration={duration:.1f}min cost=₹{cost:.2f}"
            )
            pcs_map.pop(webrtc_connection.pc_id, None)

        transport = SmallWebRTCTransport(
            webrtc_connection=connection,
            params=TransportParams(
                audio_in_enabled=True,
                audio_out_enabled=True,
            ),
        )
        background_tasks.add_task(bot.run_bot, transport, language)

    answer = connection.get_answer()
    pcs_map[answer["pc_id"]] = connection
    return answer


@app.post("/api/offer")
async def offer_direct(request: dict, background_tasks: BackgroundTasks):
    return await _handle_offer(request, background_tasks)


@app.api_route(
    "/sessions/{session_id}/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
async def sessions_proxy(
    session_id: str, path: str, request: Request, background_tasks: BackgroundTasks
):
    if session_id not in active_sessions:
        return Response(content="Invalid or expired session_id", status_code=404)

    if path.endswith("api/offer"):
        try:
            request_data = await request.json()
        except Exception:
            return Response(content="Invalid JSON body", status_code=400)

        if request.method == HTTPMethod.POST.value:
            return await _handle_offer(request_data, background_tasks)

    return Response(status_code=200)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
