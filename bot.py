#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""
Plivo AI Voice Agent
- Greets the caller with an AI voice introduction
- Asks for the customer's Order ID
- Calls the Zoho API to fetch order status via LLM function calling
- Reads out whether the order has been dispatched
"""

import asyncio
import os
import time
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
from pipecat.runner.utils import create_transport
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
    db_append_transcript,
    db_create_call,
    db_set_duration,
    db_set_forwarded,
    db_update_order,
)

load_dotenv()


# ─── Config ────────────────────────────────────────────────────────────────────

ZOHO_API_URL: str = os.getenv(
    "ZOHO_ORDER_API_URL",
    "https://www.zohoapis.in/creator/custom/goodwind/Fetch_order_Status",
)
ZOHO_PUBLIC_KEY: str = os.getenv("ZOHO_API_PUBLIC_KEY", "FjhK5xdE8XD57tqm3Z0SeZYke")


# ─── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a voice support agent for Goodwind Technologies handling inbound calls.

RULES:
- Phone call. Max 1-2 short sentences per response. No markdown, bullets, or emojis.
- Speak at a brisk, natural phone-call pace. Never speak slowly or add long pauses.
- Respond immediately after the caller finishes — do not hesitate or overthink.
- Always reply in whatever language the customer speaks (English, Tamil, or Malayalam). Detect it automatically. Never ask them to choose.
- Never fabricate order information. Only relay what check_order_status returns.

FLOW:

STEP 1 — GREET IMMEDIATELY: As soon as the call connects, YOU speak first. One warm sentence as Goodwind Technologies support asking how you can help. Never wait for the caller to speak first.

STEP 2 — After customer speaks, classify IMMEDIATELY and act:
  A. ORDER STATUS → ask for their 4-digit Order ID (once only), call check_order_status, relay result.
  B. ANYTHING ELSE (refunds, cancellations, returns, complaints, sales, speak to human) → say "I'll transfer you to a support agent now, please hold on." in their language, then call forward_call.
  C. UNCLEAR → one short clarifying question, then classify.

STEP 3 — ORDER RESULT:
  - Dispatched → say order is dispatched.
  - Quoted → say status is Quoted.
  - Error/not found → say unable to retrieve right now.
  Ask if anything else needed.

STEP 4 — CLOSE: Warm goodbye in their language, call end_conversation.

ORDER ID: 4 digits only. Words like "six one eight zero" = 6180. Do NOT read it back. Call check_order_status immediately.

FORWARD: Say "I'll transfer you to a support agent now, please hold on." first, then call forward_call immediately.

STRICT: Never answer refunds/cancellations/complaints/sales/returns. Always forward these."""

# Seeded as the first user turn so Gemini Live speaks on connect (initial context only).
CONNECT_GREETING_TRIGGER = "[call connected] Greet the caller immediately."

# ─── Bot Pipeline ──────────────────────────────────────────────────────────────

async def run_bot(
    transport: BaseTransport,
    handle_sigint: bool,
    call_uuid: str | None = None,
    host: str | None = None,
    caller_number: str | None = None,
) -> None:
    """Set up and run the Pipecat pipeline."""

    state = {
        "language": "english"
    }

    db_id = db_create_call(caller_number or "Unknown", call_uuid=call_uuid or "")
    start_time = time.time()

    # Placeholders for nested function access
    llm: GeminiLiveLLMService | None = None
    context: LLMContext | None = None

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def check_order_status(params: FunctionCallParams, order_id: str) -> None:
        """Check the current status of a customer's order from our system.

        IMPORTANT: Only call this function AFTER the customer has spoken their 4-digit Order ID in their most recent message. Never call this speculatively or before you have asked for and received the Order ID.

        Args:
            order_id: The 4-digit numeric order ID spoken by the customer, e.g. "6180". Convert spoken numbers to digits before calling.
        """
        print(f"\n>>> [ZOHO API] Checking status for order ID: {order_id}")
        logger.info(f"Calling Zoho API for order ID: {order_id}")

        url = f"{ZOHO_API_URL}?publickey={ZOHO_PUBLIC_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {"order_id": order_id.strip()}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=12),
                ) as resp:
                    data = await resp.json(content_type=None)
                    print(f"\n>>> [ZOHO API RESPONSE] Status: {resp.status} | Data: {data}\n")
                    logger.info(f"Zoho API response for {order_id}: {data}")

            status = data.get("result", "")
            if db_id:
                db_update_order(db_id, order_id)
            await params.result_callback({"status": status})

        except Exception as e:
            print(f"\n>>> [ZOHO API ERROR] Failed for order {order_id}: {e}\n")
            logger.error(f"Zoho API error for {order_id}: {e}")
            await params.result_callback({"error": "Failed to retrieve order status"})

    @tool_options(cancel_on_interruption=False, timeout_secs=5)
    async def set_language(params: FunctionCallParams, language: str) -> None:
        """Switch the conversation language. Call this automatically as soon as you detect the customer speaking Tamil or Malayalam — do NOT wait for them to explicitly ask. Also call this if the customer asks to switch language mid-call.

        Args:
            language: The detected or requested language. Must be one of: "english", "tamil", or "malayalam".
        """
        print(f"\n>>> [SET LANGUAGE] Switching to: {language}")
        logger.info(f"Switching language to: {language}")

        lang_map = {
            "english": (Language.EN_US, "en-US"),
            "tamil": (Language.TA_IN, "ta-IN"),
            "malayalam": (Language.ML_IN, "ml-IN"),
        }

        lang_lower = language.lower().strip()
        if lang_lower in lang_map:
            stt_lang, tts_lang = lang_map[lang_lower]
            state["language"] = lang_lower

            # Update settings on the Gemini Live LLM service only for supported languages (en-US)
            if llm and stt_lang == Language.EN_US:
                llm.set_language(stt_lang)

            # Restrict the LLM strictly to the chosen language
            if context is not None:
                context.add_message({
                    "role": "system",
                    "content": (
                        f"The user selected {language.upper()} ({tts_lang}). "
                        f"From now on, you MUST converse ONLY in {language.upper()} using its script. "
                        "Do NOT respond in English, Tamil, Malayalam, or any other language "
                        "except the one selected. Keep the rule absolute."
                    )
                })

            await params.result_callback(f"Language set to {language} successfully.")
        else:
            await params.result_callback(f"Unsupported language: {language}.")

    @tool_options(cancel_on_interruption=False, timeout_secs=5)
    async def end_conversation(params: FunctionCallParams) -> None:
        """Hang up the phone call immediately. Call this function as soon as the user says thank you, says no more help is needed, or says goodbye to end the conversation."""
        print(f"\n>>> [END CONVERSATION] Hanging up call {call_uuid}...\n")
        logger.info(f"Ending conversation and closing call {call_uuid}")

        # Call Plivo API to hang up the call after a short delay
        if call_uuid:
            async def hangup_plivo_call():
                await asyncio.sleep(3.0) # let Gemini finish playing its goodbye sentence
                try:
                    auth_id = os.getenv("PLIVO_AUTH_ID")
                    auth_token = os.getenv("PLIVO_AUTH_TOKEN")
                    client = plivo.RestClient(auth_id, auth_token)
                    client.calls.hangup(call_uuid=call_uuid)
                    print(f"Plivo call {call_uuid} hung up successfully via REST API.")
                except Exception as ex:
                    print(f"Error hanging up call via Plivo API: {ex}")
                await worker.cancel()

            asyncio.create_task(hangup_plivo_call())
        else:
            async def cancel_worker_delayed():
                await asyncio.sleep(3.0)
                await worker.cancel()
            asyncio.create_task(cancel_worker_delayed())

        await params.result_callback("Goodbye spoken. Call hanging up.")

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def forward_call(params: FunctionCallParams, reason: str = "") -> None:
        """Forward the call to a customer support agent. Call this immediately if the customer's query/intent is NOT about checking order status, or if they ask to speak to a human, or have any other query.

        Args:
            reason: The reason for forwarding the call.
        """
        print(f"\n>>> [FORWARD CALL] Forwarding call {call_uuid} due to: {reason}\n")
        logger.info(f"Forwarding call {call_uuid} to support agent. Reason: {reason}")

        if db_id:
            db_set_forwarded(db_id, True)

        if call_uuid and host:
            async def transfer_plivo_call():
                await asyncio.sleep(4.0) # Let Gemini finish speaking the transfer message
                try:
                    auth_id = os.getenv("PLIVO_AUTH_ID")
                    auth_token = os.getenv("PLIVO_AUTH_TOKEN")
                    client = plivo.RestClient(auth_id, auth_token)
                    forward_url = f"https://{host}/forward-call"
                    logger.info(f"Transferring call {call_uuid} to {forward_url}")
                    response = client.calls.transfer(
                        call_uuid=call_uuid,
                        legs="aleg",
                        aleg_url=forward_url,
                        aleg_method="POST"
                    )
                    logger.info(f"Plivo call {call_uuid} transferred/forwarded successfully. Response: {response}")
                except Exception as ex:
                    logger.error(f"Error transferring call via Plivo API: {ex}")
                await worker.cancel()

            asyncio.create_task(transfer_plivo_call())
        else:
            logger.warning("Cannot forward call: call_uuid or host is not set.")
            async def cancel_worker_delayed():
                await asyncio.sleep(4.0)
                await worker.cancel()
            asyncio.create_task(cancel_worker_delayed())

        await params.result_callback("Call forwarding initiated.")

    context = LLMContext(
        messages=[{"role": "user", "content": CONNECT_GREETING_TRIGGER}],
        tools=[check_order_status, set_language, end_conversation, forward_call],
    )

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "",
        settings=GeminiLiveLLMService.Settings(
            model="models/gemini-2.5-flash-native-audio-latest",
            voice="Sulafat",  # Charon is more adaptive to accent instructions via system prompt
            language=Language.EN_US,  # en-IN is unsupported by native-audio model; accent via system prompt
            system_instruction=SYSTEM_PROMPT,
            vad=GeminiVADParams(
                silence_duration_ms=500,
                start_sensitivity=StartSensitivity.START_SENSITIVITY_HIGH,
                end_sensitivity=EndSensitivity.END_SENSITIVITY_HIGH,
            ),
            thinking=ThinkingConfig(thinking_budget=0),
        ),
        tools=[check_order_status, set_language, end_conversation, forward_call],
    )

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        realtime_service_mode=True
    )

    @user_aggregator.event_handler("on_user_turn_message_added")
    async def on_user_turn_message_added(aggregator, message: UserTurnMessageAddedMessage):
        user_transcript = message.content
        if user_transcript and db_id:
            db_append_transcript(db_id, "user", user_transcript)

    @assistant_aggregator.event_handler("on_assistant_turn_stopped")
    async def on_assistant_turn_stopped(aggregator, message: AssistantTurnStoppedMessage):
        agent_transcript = message.content
        if agent_transcript and db_id:
            db_append_transcript(db_id, "agent", agent_transcript)

    pipeline = Pipeline(
        [
            transport.input(),       # Audio in from Plivo WebSocket
            user_aggregator,         # Accumulate user turn
            llm,                     # GeminiLiveLLMService (LLM + STT + TTS)
            transport.output(),      # Audio out to Plivo WebSocket
            assistant_aggregator,    # Accumulate assistant turn
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):  # noqa: ANN001
        """Kick off the conversation with an AI greeting when the call connects."""
        logger.info("Client connected — triggering immediate greeting")

        # Push frames IMMEDIATELY (no delay). The Gemini session takes ~500ms to open.
        # If these frames arrive before the session opens, GeminiLive sets
        # _run_llm_when_session_ready=True, so it fires _create_initial_response
        # the moment the session is ready — guaranteeing the agent speaks first.
        # LLMRunFrame is a fallback in case the session was already open.
        logger.info("Pushing LLMMessagesUpdateFrame + LLMRunFrame immediately to trigger greeting")
        await worker.queue_frames([
            LLMMessagesUpdateFrame(messages=context.messages),
            LLMRunFrame(),
        ])
        logger.info("Greeting frames queued — agent should speak now")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):  # noqa: ANN001
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    try:
        await runner.run()
    finally:
        duration = int(time.time() - start_time)
        if db_id:
            db_set_duration(db_id, duration)


# ─── Entry Points ──────────────────────────────────────────────────────────────

async def bot(
    runner_args: RunnerArguments,
    call_uuid: str | None = None,
    host: str | None = None,
    caller_number: str | None = None,
) -> None:
    """Main bot entry point compatible with Pipecat Cloud."""

    transport_params = {
        "plivo": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    # Disable automatic call hangup on pipeline cancel/end. This prevents Plivo from
    # immediately terminating the call when the WebSocket finishes, allowing our
    # REST API transfer/forwarding logic to succeed and bridge the caller.
    transport_params_obj = getattr(transport, "_params", None)
    if transport_params_obj and hasattr(transport_params_obj, "serializer"):
        serializer = getattr(transport_params_obj, "serializer", None)
        if serializer:
            serializer_params = getattr(serializer, "_params", None)
            if serializer_params and hasattr(serializer_params, "auto_hang_up"):
                setattr(serializer_params, "auto_hang_up", False)
                logger.info("Disabled serializer auto_hang_up to allow call transfer/forwarding to succeed.")

    await run_bot(transport, runner_args.handle_sigint, call_uuid, host, caller_number)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
