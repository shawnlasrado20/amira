# Amira — Self-Hosted Pipecat Voice AI (Tamil Restaurant Receptionist)

## What this is

A self-hosted [Pipecat](https://github.com/pipecat-ai/pipecat) voice AI pipeline that
replicates a Tamil-language restaurant receptionist ("Amira" for Saffron House)
currently running on AgenticFlow. The goal is to test whether this stack can replace
AgenticFlow entirely and cut cost from **€0.26/minute** to near zero.

Pipeline: browser (local WebRTC) → Sarvam STT (`saarika:v2.5`, `ta-IN`) → Google Gemini
2.5 Flash → Sarvam TTS (`bulbul:v2`, voice `arya`, `ta-IN`) → browser (local WebRTC).

The transport is Pipecat's own **SmallWebRTC** transport, not Daily — no third-party
voice platform account, no payment method, no per-minute or per-room cost. Your browser
connects peer-to-peer straight to your local server.

## Cost comparison

| Component      | AgenticFlow Cost         | Self-hosted Cost                    |
|-----------------|---------------------------|--------------------------------------|
| Voice platform  | €0.26 / minute           | Free (local WebRTC, no account)     |
| Sarvam STT      | Included                 | ~₹30 / hour                          |
| Sarvam TTS      | Included                 | ~₹30 / 10,000 characters             |
| LLM             | Included                 | Gemini free tier / near zero         |
| **Total**       | **~€0.52 / 2-min call**  | **~₹2–4 / 2-min call**               |

## Prerequisites

- Python 3.11 or higher
- Two API keys:
  - **Google** — sign in at [aistudio.google.com](https://aistudio.google.com), click
    "Get API key", copy it.
  - **Sarvam** — get a key from [dashboard.sarvam.ai](https://dashboard.sarvam.ai).
- No Daily account or payment method needed for local testing.

## Installation

```bash
cd pipecat-amira
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Then open `.env` and fill in `SARVAM_API_KEY` and `GOOGLE_API_KEY`.
(`DAILY_API_KEY` is only needed if you switch back to Daily later — see below.)

## How to run

```bash
python server.py
```

The server listens on `http://0.0.0.0:8000`.

## How to test

Open **http://localhost:8000/** in your browser (it redirects to the built-in client UI
at `/client/`). Click connect, allow microphone access, and speak Tamil to Amira — she
should greet you immediately with the configured first message.

Health check:

```bash
curl http://localhost:8000/health
```

## Swapping the LLM from Gemini to Groq

1. Add `GROQ_API_KEY=` to `.env` and `.env.example`.
2. Add `groq` to the `pipecat-ai` extras in `requirements.txt`.
3. In `bot.py`, replace the `GoogleLLMService` import and construction with
   `GroqLLMService` (model `llama-3.3-70b-versatile`), exactly as shown in the comment
   block at the bottom of `bot.py`.

## Switching back to Daily

Daily was the original transport but requires a payment method on file even for free-tier
usage, which blocked local testing — so this project defaults to Pipecat's local
SmallWebRTC transport instead (no account needed). If you later want Daily (e.g. for
sharing a call with someone remote, or as a stepping stone to phone integration), see the
comment block at the bottom of `bot.py` for exactly what to change in `bot.py` and
`server.py`.

## Known issues

- Sarvam `saarika:v2.5` is used instead of `saaras:v3` deliberately — it's the more
  stable, currently-supported model for straight transcription and avoids version
  compatibility issues around the newer `mode` parameter on `saaras:v3`.
- For real phone calls, the SmallWebRTC transport must be replaced with a Twilio or
  Exotel SIP transport (both Daily and SmallWebRTC are browser/WebRTC only, not PSTN).
- The "endpointing wait 0.3s / max delay 1.5s" values from the original AgenticFlow
  config are approximated in `bot.py` via `VADParams(stop_secs=0.3)` and
  `LLMUserAggregatorParams(user_turn_stop_timeout=1.5)` — see the `TODO` comment there.
  Pipecat's current version doesn't expose a single unified "endpointing" setting, so
  these two values may need tuning after real call testing.
- SmallWebRTC is peer-to-peer WebRTC with a local STUN server for NAT traversal — fine
  for local testing on one machine, but not meant for public/production traffic the way
  Daily's managed infrastructure is.

## Next steps

- Replace the WebRTC transport with an Exotel SIP transport for real phone calls.
- Add an N8N webhook integration for post-call logging.
- Deploy to a VPS for production use.
