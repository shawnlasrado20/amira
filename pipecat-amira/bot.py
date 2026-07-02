"""
Amira - Tamil-speaking restaurant receptionist for Saffron House.
Self-hosted Pipecat pipeline: Sarvam STT -> Gemini LLM -> Sarvam TTS.

This module exposes `run_bot(transport)`, which server.py calls with a
SmallWebRTCTransport for each incoming browser connection. There's no
standalone CLI entry point anymore -- SmallWebRTC needs a signaling server
(the /api/offer endpoint in server.py) to set up the WebRTC connection before
a transport object even exists.
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
from pipecat.services.groq.llm import GroqLLMService
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.workers.runner import WorkerRunner

FIRST_MESSAGE = "Saffron House से बोल रहा हूँ! मैं Arjun हूँ — आपकी कैसे मदद कर सकता हूँ?"

SYSTEM_PROMPT = (
    "You are Arjun, the AI receptionist for Saffron House restaurant. ALWAYS respond in "
    "modern casual spoken Hindi, the kind people use in everyday Delhi/Mumbai conversations — "
    "informal, naturally mixed with some English words like ok, sure, booking, table, "
    "confirm. Do NOT use formal or literary Hindi. Sound like a friendly young man talking "
    "on the phone. If the caller speaks English, reply in English. Otherwise always use "
    "casual modern Hindi. Your job on every call: greet warmly, answer questions using the "
    "restaurant info below, take table bookings by getting name, date, time, and party size "
    "then repeating it back to confirm, answer menu questions and give recommendations, "
    "share opening hours and location when asked. If unsure say a team member will follow "
    "up. Never guess prices. Restaurant info: Name is Saffron House. Cuisine is North "
    "Indian with vegetarian, vegan, and gluten-free options. Opening hours Monday to "
    "Sunday, lunch 12pm to 3pm, dinner 6pm to 11pm. Location is Ground floor Marina Walk "
    "with free parking. Popular dishes are butter chicken, paneer tikka, dal makhani, "
    "garlic naan, Saffron House biryani. Bookings up to 30 days in advance, groups of 8 "
    "or more get a callback to confirm. Example of the Hindi style to use: Haan bhai, "
    "aapka naam kya hai? Ok, do logon ke liye booking kar deta hoon. Sure, confirm kar "
    "raha hoon — Saturday 7 baje, 4 log, sahi hai? Shukriya! Aur koi help chahiye? "
    "Style: 1 to 2 sentences per reply, casual warm and upbeat not robotic, always confirm "
    "booking details before ending, end the call politely."
)


async def run_bot(transport: BaseTransport):
    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamSTTService.Settings(
            model="saarika:v2.5",
            language=Language.HI_IN,
        ),
    )

    # bulbul:v3 + shubh: Sarvam's recommended male voice for hi-IN.
    tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            voice="shubh",
            language=Language.HI_IN,
        ),
    )

    llm = GroqLLMService(
        api_key=os.getenv("GROQ_API_KEY"),
        settings=GroqLLMService.Settings(
            model="llama-3.3-70b-versatile",
            system_instruction=SYSTEM_PROMPT,
            temperature=0.8,
            max_tokens=1024,
        ),
    )

    # LLMContext is Pipecat's current provider-agnostic context object (the successor to
    # the old OpenAI-specific OpenAILLMContext/LLMMessagesContext pattern requested in the
    # original spec). The system prompt lives on the LLM service's `system_instruction`
    # setting above rather than as a message in the context -- that's the current
    # non-deprecated way to set a system prompt for GoogleLLMService.
    context = LLMContext()

    # TODO: "Endpointing wait 0.3s / max delay 1.5s" from the original AgenticFlow config
    # doesn't map 1:1 onto a single Pipecat setting anymore. Best-effort mapping used here:
    #   - VADParams(stop_secs=0.3) -> how long of silence before Silero VAD decides the
    #     user stopped talking (the "endpointing wait").
    #   - LLMUserAggregatorParams(user_turn_stop_timeout=1.5) -> max time the user-turn
    #     aggregator waits before considering the turn finished (the "max delay").
    # Verify against real call behavior and tune both values if turns cut off too early/late.
    vad_analyzer = SileroVADAnalyzer(params=VADParams(stop_secs=0.3))

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=vad_analyzer,
            user_turn_stop_timeout=1.5,
        ),
    )

    # Interruptions: current Pipecat has no standalone "allow_interruptions" flag (it was
    # removed from PipelineParams/PipelineTask). Barge-in is enabled automatically whenever
    # a VAD analyzer is wired into the user aggregator, as done above -- so no extra config
    # is needed to allow the caller to interrupt Amira mid-sentence.
    pipeline = Pipeline(
        [
            transport.input(),
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
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        # TTSSpeakFrame is Pipecat's dedicated frame for sending literal text straight to
        # TTS, bypassing STT/LLM -- this is what lets the greeting play immediately instead
        # of waiting on a round trip through the LLM.
        await worker.queue_frames([TTSSpeakFrame(FIRST_MESSAGE)])
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


# -----------------------------------------------------------------------------
# Swapping the LLM from Gemini to Groq
# -----------------------------------------------------------------------------
# 1. Add GROQ_API_KEY= to .env and .env.example (get a key from console.groq.com).
# 2. Add "groq" to the pipecat-ai extras in requirements.txt:
#      pipecat-ai[sarvam,google,groq,silero,webrtc]
# 3. Replace the Google LLM import and service construction above with:
#
#      from pipecat.services.groq.llm import GroqLLMService
#
#      llm = GroqLLMService(
#          api_key=os.getenv("GROQ_API_KEY"),
#          settings=GroqLLMService.Settings(
#              model="llama-3.3-70b-versatile",
#              system_instruction=SYSTEM_PROMPT,
#              temperature=0.8,
#              max_tokens=1024,
#          ),
#      )
#
#    Everything else in the pipeline (STT, TTS, transport, context aggregators) stays
#    the same -- only the `llm` object and its import change.


# -----------------------------------------------------------------------------
# Switching back to Daily (e.g. for production, or once you have a Daily card on
# file) instead of local SmallWebRTC
# -----------------------------------------------------------------------------
# 1. Add "daily" back to the pipecat-ai extras in requirements.txt.
# 2. In server.py, replace the SmallWebRTC signaling (/api/offer, pcs_map, prebuilt
#    UI mount) with Daily room + meeting-token creation via the Daily REST API, and
#    launch the bot as a subprocess (`asyncio.create_subprocess_exec`) instead of a
#    FastAPI background task.
# 3. Change `run_bot`'s transport argument to a DailyTransport constructed from the
#    room_url/token, e.g.:
#
#      from pipecat.transports.daily.transport import DailyParams, DailyTransport
#
#      transport = DailyTransport(
#          room_url, token, "Amira",
#          DailyParams(audio_in_enabled=True, audio_out_enabled=True),
#      )
#
#    Note Daily uses "on_first_participant_joined" / "on_participant_left" event
#    names instead of SmallWebRTC's "on_client_connected" / "on_client_disconnected".
