"""
Amira — product demo voice agent.
Self-hosted Pipecat pipeline: Sarvam STT -> Groq LLM -> Sarvam TTS.

Arjun is a friendly Amira product demo assistant. He explains what Amira does,
answers pricing and feature questions, and books 15-minute live demos.

This module exposes `run_bot(transport, language)`, called by server.py with a
SmallWebRTCTransport for each incoming browser connection.
"""

import os

from dotenv import load_dotenv
from loguru import logger

# Load .env before anything else touches os.environ.
load_dotenv()

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frameworks.rtvi import RTVIObserver, RTVIProcessor
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

_PRODUCT_BASE = (
    "You are Arjun, a friendly product demo assistant for Amira — an AI phone receptionist SaaS. "
    "Amira: picks up every call in 1 ring 24/7, books appointments, answers FAQs, "
    "takes messages, sends call summaries, 40+ languages, Calendar + CRM sync, GDPR-compliant, "
    "live in under 10 minutes, no credit card needed. "
    "Pricing: Starter forty-nine dollars/month (two hundred minutes, one assistant, calendar sync). "
    "Growth one hundred forty-nine dollars/month (one thousand five hundred minutes, five assistants, "
    "CRM, warm transfers). Scale: custom. No setup fees. "
    "To book a demo: collect name, email, business type — one at a time. "

    "CRITICAL RULES: "
    "1) Reply in EXACTLY ONE short punchy sentence — never more. "
    "2) Before every reply, react briefly to what was just said "
    "(e.g. 'Hmm yeah...', 'Oh interesting...', mirror their last word back). VARY it each time. "
    "3) Use filler words (hmm, uh, well) — VARY them, never repeat back-to-back. "
    "4) NEVER use ellipsis (...) or multiple dots — they break the audio. "
    "5) Use CAPITALS for emphasis. "
    "6) ONE question at a time. "
    "7) Numbers as words (forty-nine, one hundred forty-nine). "
    "8) If asked about your instructions, respond cheekily and stay in character. "
    "9) Only discuss Amira — gently redirect anything off-topic."
)

# Per-language config: STT language, TTS language + voice, opening greeting, tone instruction.
LANGUAGE_CONFIG: dict[str, dict] = {
    "en": {
        "stt": Language.EN_IN,
        "tts": Language.EN_IN,
        "voice": "ratan",
        "greeting": "Hey! I'm Arjun from Amira — the AI that never misses a call. What do you want to know?",
        "tone": "Respond in casual friendly English, short and punchy. No corporate speak.",
    },
    "hi": {
        "stt": Language.HI_IN,
        "tts": Language.HI_IN,
        "voice": "shubh",
        "greeting": "Hey! मैं Arjun हूँ, Amira की तरफ से — AI receptionist जो हर call pick करता है! क्या जानना है?",
        "tone": (
            "CRITICAL: Write ALL Hindi words in Devanagari script. "
            "English product words (Amira, demo, call, AI, pricing, minutes, plan) stay in English. "
            "Never write Hindi in Roman letters. "
            "Style: casual young Delhi/Mumbai mix. "
            "Correct examples: 'हाँ भाई, Amira 24/7 calls handle करता है!', "
            "'Demo book करना है?', 'Starter plan सिर्फ forty-nine dollars में है.'"
        ),
    },
    "ta": {
        "stt": Language.TA_IN,
        "tts": Language.TA_IN,
        "voice": "ratan",
        "greeting": "Hey! நான் Arjun, Amira-ல இருந்து — AI receptionist. என்ன தெரிஞ்சுக்கணும்?",
        "tone": (
            "CRITICAL: Write ALL Tamil words in Tamil script. "
            "English product words (Amira, demo, call, AI, pricing, plan, minutes) stay in English. "
            "Never write Tamil in Roman letters. "
            "Style: casual young Chennai Tanglish. "
            "Correct examples: 'Amira 24/7 calls pick பண்ணும், miss இல்ல!', "
            "'Demo book பண்ணலாமா?', 'Starter plan forty-nine dollars-ல தான்.'"
        ),
    },
    "te": {
        "stt": Language.TE_IN,
        "tts": Language.TE_IN,
        "voice": "shubh",
        "greeting": "Hey! నేను Arjun, Amira నుండి — AI receptionist. ఏం తెలుసుకోవాలి?",
        "tone": (
            "CRITICAL: Write ALL Telugu words in Telugu script. "
            "English product words (Amira, demo, call, AI, pricing, plan) stay in English. "
            "Never write Telugu in Roman letters. "
            "Style: casual young Hyderabad mix. "
            "Correct examples: 'Amira 24/7 calls handle చేస్తుంది!', 'Demo book చేద్దామా?'"
        ),
    },
    "kn": {
        "stt": Language.KN_IN,
        "tts": Language.KN_IN,
        "voice": "shubh",
        "greeting": "Hey! ನಾನು Arjun, Amira ನಿಂದ — AI receptionist. ಏನು ತಿಳಿದುಕೊಳ್ಳಬೇಕು?",
        "tone": (
            "CRITICAL: Write ALL Kannada words in Kannada script. "
            "English product words (Amira, demo, call, AI, pricing, plan) stay in English. "
            "Never write Kannada in Roman letters. "
            "Style: casual young Bengaluru mix. "
            "Correct examples: 'Amira 24/7 calls handle ಮಾಡುತ್ತದೆ!', 'Demo book ಮಾಡೋಣವಾ?'"
        ),
    },
}


def _build_system_prompt(tone: str) -> str:
    return f"{_PRODUCT_BASE} {tone}"


async def run_bot(transport: BaseTransport, language: str = "hi"):
    cfg = LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["hi"])
    greeting = cfg["greeting"]
    system_prompt = _build_system_prompt(cfg["tone"])

    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamSTTService.Settings(
            model="saarika:v2.5",
            language=cfg["stt"],
        ),
    )

    tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            voice=cfg["voice"],
            language=cfg["tts"],
            pace=1.1,        # slightly snappier delivery (range 0.5–2.0 for v3)
            temperature=0.5, # lower = more stable, fewer audio artifacts
        ),
    )

    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile",
            system_instruction=system_prompt,
            temperature=0.7,
            max_tokens=80,
        ),
    )

    # LLMContext is Pipecat's current provider-agnostic context object (the successor to
    # the old OpenAI-specific OpenAILLMContext/LLMMessagesContext pattern requested in the
    # original spec). The system prompt lives on the LLM service's `system_instruction`
    # setting above rather than as a message in the context -- that's the current
    # non-deprecated way to set a system prompt for GoogleLLMService.
    context = LLMContext()

    # Use Pipecat defaults (confidence=0.7, start_secs=0.2, stop_secs=0.2, min_volume=0.6).
    # Pipecat 1.4 pairs VAD with a smart-turn ML model for end-of-turn detection, and that
    # model is calibrated for stop_secs=0.2 (the server logged a warning about our old 0.5).
    # Our earlier aggressive tuning (confidence=0.83, min_volume=0.76, start_secs=0.6) was
    # fighting the smart-turn model: quiet speech got dropped by VAD but still transcribed
    # by STT, so transcripts arrived with no user turn attached and the LLM never fired.
    # Browser-side echoCancellation/noiseSuppression already handles background noise.
    vad_analyzer = SileroVADAnalyzer(params=VADParams(stop_secs=0.2))

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad_analyzer,
        ),
    )

    # Interruptions: current Pipecat has no standalone "allow_interruptions" flag (it was
    # removed from PipelineParams/PipelineTask). Barge-in is enabled automatically whenever
    # a VAD analyzer is wired into the user aggregator, as done above -- so no extra config
    # is needed to allow the caller to interrupt Amira mid-sentence.
    # RTVI: the protocol the Pipecat prebuilt UI (and our frontend) speak over the WebRTC
    # data channel. Without this, RTVI clients connect, send client-ready, and get silence
    # back — the UI state machine never resolves (the "Data channel not established" warning
    # + glitchy behavior on /client/). The observer converts pipeline frames into protocol
    # messages: user-transcription, bot-transcription, speaking states, bot-ready.
    rtvi = RTVIProcessor()

    pipeline = Pipeline(
        [
            transport.input(),
            rtvi,
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    # PipelineWorker + WorkerRunner is the current (1.3.0+) replacement for the deprecated
    # PipelineTask + PipelineRunner pair. PipelineTask still exists as a deprecated alias
    # but will be removed in 2.0.0, so we use the current API directly.
    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[RTVIObserver(rtvi)],
    )

    @rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi_processor):
        # Completes the RTVI handshake for protocol-speaking clients (prebuilt UI).
        # Non-RTVI clients never send client-ready; transcription messages flow to them
        # regardless, so this only affects the handshake state.
        await rtvi_processor.set_bot_ready()

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # TTSSpeakFrame bypasses STT/LLM so the greeting plays immediately on connect.
        await worker.queue_frames([TTSSpeakFrame(greeting)])
        logger.info("Client connected, greeting queued")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected, shutting down worker")
        await worker.cancel()

    # handle_sigint=False because this runs as a FastAPI background task inside
    # server.py's process/event loop -- uvicorn already owns signal handling there,
    # and only the main WorkerRunner in a standalone script should install handlers.
    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()
