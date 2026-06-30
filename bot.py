import asyncio
import os
import time
from datetime import datetime
import plivo

import aiohttp
from dotenv import load_dotenv
from google.genai.types import EndSensitivity, StartSensitivity, ThinkingConfig
from loguru import logger
from pipecat.adapters.schemas.direct_function import tool_options
from pipecat.frames.frames import LLMMessagesUpdateFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    AssistantTurnStoppedMessage,
    LLMContextAggregatorPair,
    UserTurnMessageAddedMessage,
)
from pipecat.runner.types import RunnerArguments
from pipecat.serializers.plivo import PlivoFrameSerializer
from pipecat.services.google.gemini_live.llm import (
    GeminiLiveLLMService,
    GeminiVADParams,
)
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

from database import (
    db_save_call,
    db_get_settings,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_WELCOME_MESSAGE,
)

load_dotenv()

# ── Loguru ──────────────────────────────────────────────────────────────────────
logger.remove()
logger.add(
    lambda msg: print(msg, end=""),
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    level="INFO",
    filter=lambda record: (
        record["name"].startswith("__main__")
        or record["name"] == "__mp_main__"
        or "bot" in record["name"]
        or record["level"].no >= 30
    ),
    colorize=True,
)

# ─── Config ────────────────────────────────────────────────────────────────────

ZOHO_API_URL: str = os.getenv(
    "ZOHO_ORDER_API_URL",
    "https://www.zohoapis.in/creator/custom/goodwind/Fetch_order_Status",
)
ZOHO_PUBLIC_KEY: str = os.getenv("ZOHO_API_PUBLIC_KEY", "FjhK5xdE8XD57tqm3Z0SeZYke")

# Injected as first user turn — tells Gemini to greet immediately
CONNECT_GREETING_TRIGGER = "[call connected] Greet the caller immediately."

# gemini-2.5-flash-native-audio-latest: ta-IN / ml-IN cause error 1007.
# STT is inherently multilingual — pass None to skip set_language() for those.
LANG_MAP = {
    "english":   (Language.EN_US, "en-US", "English"),
    "tamil":     (None,           "ta-IN", "Tamil"),
    "malayalam": (None,           "ml-IN", "Malayalam"),
}

# ─── Transcript printer ────────────────────────────────────────────────────────

def print_transcript_line(role: str, text: str, timestamp: str):
    if role == "user":
        print(f"\n  [{timestamp}] 👤 USER  : {text}")
    else:
        print(f"  [{timestamp}] 🤖 AGENT : {text}\n")

# ─── Bot Pipeline ──────────────────────────────────────────────────────────────

async def run_bot(
    transport: BaseTransport,
    handle_sigint: bool,
    call_uuid: str | None = None,
    host: str | None = None,
    caller_number: str | None = None,
) -> None:

    state = {
        "language": "english",
        "switch_in_progress": False,
    }

    settings = db_get_settings(bypass_cache=True)
    welcome_message = settings.get("welcome_message") or DEFAULT_WELCOME_MESSAGE
    system_prompt_template = settings.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
    resolved_system_prompt = system_prompt_template.replace("{welcome_message}", welcome_message)

    start_time = time.time()
    call_transcript = []
    order_number = ""
    call_forwarded = False

    llm: GeminiLiveLLMService | None = None
    context: LLMContext | None = None
    worker: PipelineWorker | None = None

    # Set when Gemini Live session is confirmed ready — used to fire greeting at the
    # exact right moment without any blind sleep.
    llm_ready = asyncio.Event()

    # ─── TOOLS ────────────────────────────────────────────────────────────────

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def check_order_status(params: FunctionCallParams, order_id: str) -> None:
        """Check the current status of a customer's order from our system.

        IMPORTANT: Only call this function AFTER the customer has spoken their 4-digit Order ID
        in their most recent message. Never call this speculatively.

        Args:
            order_id: The 4-digit numeric order ID spoken by the customer, e.g. "6180".
                      Convert spoken numbers to digits before calling.
        """
        logger.info(f"Zoho lookup → order_id={order_id}")

        url = f"{ZOHO_API_URL}?publickey={ZOHO_PUBLIC_KEY}"
        payload = {"order_id": order_id.strip()}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as resp:
                    data = await resp.json(content_type=None)

            status = data.get("result", "")
            logger.info(f"Zoho response → order={order_id} status={status!r}")
            nonlocal order_number
            order_number = order_id.strip()
            await params.result_callback({"status": status})

        except Exception as e:
            logger.error(f"Zoho API error for {order_id}: {e}")
            await params.result_callback({"error": "Failed to retrieve order status"})

    @tool_options(cancel_on_interruption=False, timeout_secs=8)
    async def set_language(params: FunctionCallParams, language: str) -> None:
        """Switch the conversation language. Call this automatically as soon as you detect
        the customer speaking Tamil or Malayalam. Also call if they explicitly request a switch.

        Args:
            language: One of "english", "tamil", or "malayalam".
        """
        lang_lower = language.lower().strip()

        if state["switch_in_progress"]:
            logger.warning(f"[LANG] Switch in progress — skipping duplicate for '{lang_lower}'")
            await params.result_callback("Switch already in progress.")
            return

        if state["language"] == lang_lower:
            await params.result_callback(f"Already in {lang_lower}.")
            return

        if lang_lower not in LANG_MAP:
            await params.result_callback(f"Unsupported language: {language}.")
            return

        state["switch_in_progress"] = True
        stt_lang, tts_lang, lang_label = LANG_MAP[lang_lower]
        logger.info(f"[LANG] {state['language']} → {lang_lower}")

        try:
            # Inject a system-level instruction so the model switches output language
            if context is not None:
                context.add_message({
                    "role": "system",
                    "content": (
                        f"LANGUAGE IS NOW {lang_label.upper()} ({tts_lang}). "
                        f"Speak ONLY in {lang_label} using its native script from this point. "
                        "Do NOT use any other language. "
                        "Do NOT mention the language change unless the customer explicitly asked — "
                        "if they did, confirm once in the new language only, then continue naturally."
                    ),
                })

            # Only call set_language for codes the model actually accepts (en-US only).
            # Tamil / Malayalam STT works automatically — calling set_language with those
            # codes triggers error 1007 and crashes the session.
            if llm and stt_lang is not None:
                llm.set_language(stt_lang)

            state["language"] = lang_lower
            await params.result_callback(f"Language set to {lang_label}.")

            # Push updated context to the live session.
            # NO _reconnect() — reconnecting mid-call tears down the Gemini WS and
            # causes audio stutter / gaps. The native-audio model handles multilingual
            # output via the system prompt alone; a reconnect is not needed.
            async def flush_context():
                try:
                    await asyncio.sleep(0.05)
                    if worker and context:
                        await worker.queue_frames([
                            LLMMessagesUpdateFrame(messages=context.messages),
                        ])
                        logger.info(f"[LANG] Context flushed → {lang_label}")
                except Exception as ex:
                    logger.error(f"[LANG] flush_context error: {ex}")
                finally:
                    state["switch_in_progress"] = False

            asyncio.create_task(flush_context())

        except Exception as e:
            logger.error(f"[LANG] set_language error: {e}")
            state["switch_in_progress"] = False
            await params.result_callback("Language switch failed.")

    @tool_options(cancel_on_interruption=False, timeout_secs=5)
    async def end_conversation(params: FunctionCallParams) -> None:
        """Hang up the call. Call as soon as the user says goodbye or no more help needed."""
        logger.info(f"[END] Hanging up call {call_uuid}")

        async def _hangup():
            await asyncio.sleep(3.0)
            if call_uuid:
                try:
                    client = plivo.RestClient(
                        os.getenv("PLIVO_AUTH_ID"),
                        os.getenv("PLIVO_AUTH_TOKEN"),
                    )
                    client.calls.hangup(call_uuid=call_uuid)
                except Exception as ex:
                    logger.error(f"[END] Hangup error: {ex}")
            if worker:
                await worker.cancel()

        asyncio.create_task(_hangup())
        await params.result_callback("Call ending.")

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def forward_call(params: FunctionCallParams, reason: str = "") -> None:
        """Forward the call to a support agent. Call immediately for anything other than
        order status, or if the customer asks to speak to a human.

        Args:
            reason: Short reason for the transfer.
        """
        logger.info(f"[FORWARD] Transferring call. Reason: {reason}")
        nonlocal call_forwarded
        call_forwarded = True

        async def _transfer():
            await asyncio.sleep(4.0)
            if call_uuid and host:
                try:
                    client = plivo.RestClient(
                        os.getenv("PLIVO_AUTH_ID"),
                        os.getenv("PLIVO_AUTH_TOKEN"),
                    )
                    response = client.calls.transfer(
                        call_uuid=call_uuid,
                        legs="aleg",
                        aleg_url=f"https://{host}/forward-call",
                        aleg_method="POST",
                    )
                    logger.info(f"[FORWARD] Transfer done: {response}")
                except Exception as ex:
                    logger.error(f"[FORWARD] Transfer error: {ex}")
            if worker:
                await worker.cancel()

        asyncio.create_task(_transfer())
        await params.result_callback("Transferring now.")

    # ─── CONTEXT + LLM ────────────────────────────────────────────────────────

    context = LLMContext(
        messages=[],
        tools=[check_order_status, set_language, end_conversation, forward_call],
    )

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "",
        settings=GeminiLiveLLMService.Settings(
            model="models/gemini-2.5-flash-native-audio-latest",
            voice="Sulafat",
            language=Language.EN_US,
            system_instruction=resolved_system_prompt,
            vad=GeminiVADParams(
                # Slightly shorter silence window — reduces cut-off lag between turns
                silence_duration_ms=400,
                start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
            ),
            thinking=ThinkingConfig(thinking_budget=0),
        ),
        tools=[check_order_status, set_language, end_conversation, forward_call],
    )

    # ── Signal greeting the instant the Gemini Live WS session is open ─────────
    # on_connected fires from inside GeminiLiveLLMService once the WebSocket
    # handshake with Google is complete — this is the earliest safe moment to send.
    @llm.event_handler("on_connected")
    async def on_llm_connected(service):
        logger.info("[LLM] Gemini Live session ready")

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        realtime_service_mode=True,
    )

    # ─── TRANSCRIPT ───────────────────────────────────────────────────────────

    @user_aggregator.event_handler("on_user_turn_message_added")
    async def on_user_turn_message_added(aggregator, message: UserTurnMessageAddedMessage):
        text = message.content
        if text and text != CONNECT_GREETING_TRIGGER:
            ts = datetime.now().strftime("%H:%M:%S")
            call_transcript.append({"role": "user", "text": text, "timestamp": ts})
            print_transcript_line("user", text, ts)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        text = message.content
        if text:
            ts = datetime.now().strftime("%H:%M:%S")
            call_transcript.append({"role": "agent", "text": text, "timestamp": ts})
            print_transcript_line("agent", text, ts)

    # ─── PIPELINE ─────────────────────────────────────────────────────────────

    pipeline = Pipeline([
        transport.input(),
        user_aggregator,
        llm,
        transport.output(),
        assistant_aggregator,
    ])

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=False,
            enable_usage_metrics=False,
        ),
    )

    # ─── TRANSPORT EVENTS ─────────────────────────────────────────────────────

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info(f"[CONNECT] Call connected | uuid={call_uuid} | caller={caller_number}")
        print(f"\n{'─'*60}")
        print(f"  📞 NEW CALL")
        print(f"  Caller  : {caller_number or 'Unknown'}")
        print(f"  UUID    : {call_uuid or 'N/A'}")
        print(f"  Time    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'─'*60}\n")

        # Pre-load the greeting trigger into context immediately.
        context.add_message({"role": "user", "content": CONNECT_GREETING_TRIGGER})

        # Queue the greeting run immediately. GeminiLiveLLMService buffers
        # frames internally until its WS handshake completes, so this is
        # already frame-accurate — no manual wait needed, and no 10s stall.
        if worker:
            await worker.queue_frames([LLMRunFrame()])
            logger.info("[CONNECT] Greeting frame queued")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("[DISCONNECT] Client disconnected")
        if worker:
            await worker.cancel()

    # ─── RUN ──────────────────────────────────────────────────────────────────

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)

    print(f"  🟢 Pipeline ready | Waiting for call...\n")

    try:
        await runner.run()
    finally:
        duration = int(time.time() - start_time)
        time_of_call = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n{'─'*60}")
        print(f"  📋 CALL SUMMARY")
        print(f"  Duration : {duration}s")
        print(f"  Language : {state['language']}")
        print(f"  Order    : {order_number or 'None'}")
        print(f"  Forwarded: {call_forwarded}")
        print(f"{'─'*60}\n")

        db_id = db_save_call(
            phone_number=caller_number or "Unknown",
            call_uuid=call_uuid or "",
            time_of_call=time_of_call,
            duration=duration,
            order_number=order_number,
            transcript=call_transcript,
            call_forwarded=call_forwarded,
        )
        logger.info(f"[DB] Saved | id={db_id} | duration={duration}s")


# ─── Entry Point ───────────────────────────────────────────────────────────────

async def bot(
    runner_args: RunnerArguments,
    call_uuid: str | None = None,
    host: str | None = None,
    caller_number: str | None = None,
) -> None:

    import json
    from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport

    websocket = runner_args.websocket

    try:
        first_msg_raw = await websocket.receive_text()
        first_msg = json.loads(first_msg_raw)
        start_data = first_msg.get("start", {})
        stream_id = start_data.get("streamId")
        call_id = start_data.get("callId")
        logger.info(f"[HANDSHAKE] stream_id={stream_id} call_id={call_id}")
    except Exception as e:
        logger.error(f"[HANDSHAKE] Failed: {e}")
        raise

    params = FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        add_wav_header=False,
        serializer=PlivoFrameSerializer(
            stream_id=stream_id,
            call_id=call_id,
            auth_id=os.getenv("PLIVO_AUTH_ID", ""),
            auth_token=os.getenv("PLIVO_AUTH_TOKEN", ""),
        ),
    )

    transport = FastAPIWebsocketTransport(websocket=websocket, params=params)

    # Disable auto hangup so call transfer succeeds before WebSocket closes
    try:
        serializer = transport._params.serializer
        if hasattr(serializer._params, "auto_hang_up"):
            serializer._params.auto_hang_up = False
            logger.info("[SERIALIZER] auto_hang_up disabled")
    except AttributeError:
        pass

    await run_bot(transport, runner_args.handle_sigint, call_uuid, host, caller_number)


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()