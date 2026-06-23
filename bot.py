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

import os

import aiohttp
from dotenv import load_dotenv
from loguru import logger
from pipecat.adapters.schemas.direct_function import tool_options
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame, STTUpdateSettingsFrame, TTSUpdateSettingsFrame, FunctionCallResultProperties
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.sarvam.stt import SarvamSTTService
from pipecat.services.sarvam.tts import SarvamTTSService
from pipecat.transcriptions.language import Language
from pipecat.turns.user_mute import AlwaysUserMuteStrategy
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams
from pipecat.workers.runner import WorkerRunner

load_dotenv()

# Pre-warm Silero VAD to load/download the model at startup instead of during the first call connection
logger.info("Pre-warming Silero VAD analyzer...")
try:
    from pipecat.audio.vad.vad_analyzer import VADParams
    _dummy_vad = SileroVADAnalyzer(params=VADParams(stop_secs=0.5, start_secs=0.1))
    logger.info("Silero VAD analyzer pre-warmed successfully")
except Exception as e:
    logger.error(f"Failed to pre-warm Silero VAD: {e}")


# ─── Config ────────────────────────────────────────────────────────────────────

ZOHO_API_URL: str = os.getenv(
    "ZOHO_ORDER_API_URL",
    "https://www.zohoapis.in/creator/custom/goodwind/Fetch_order_Status",
)
ZOHO_PUBLIC_KEY: str = os.getenv("ZOHO_API_PUBLIC_KEY", "FjhK5xdE8XD57tqm3Z0SeZYke")


# ─── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a voice customer support agent for Goodwind Technologies. You handle inbound calls from customers.

CORE CONSTRAINTS
- This is a phone call. Every response must be 1–2 sentences max — short, clear, and natural to speak aloud.
- Never use markdown, bullet points, special characters, or emojis.
- Always respond in the customer's language.
- Never fabricate order information. Only relay what check_order_status returns.

CONVERSATION FLOW
Follow these steps in order:

1. GREET — Warmly welcome the caller. Do NOT ask them to choose a language.
2. DETECT LANGUAGE & INTENT — When the customer speaks, identify their language (English, Tamil, or Malayalam) and detect their intent.
   - Call `set_language` immediately with the identified language (e.g. "english", "tamil", or "malayalam") to lock the language settings. Do NOT ask them to choose; detect it dynamically.
   - If the customer's query or intent is NOT about checking order status (e.g. they ask about sales, cancellation, returns, other general inquiries, or ask to speak to a human/agent), immediately call `forward_call` to transfer them to a human support agent.
3. ASK ORDER ID — If the customer wants to check order status, ask the customer for their 4-digit Order ID. Ask this ONLY ONCE. Do NOT repeat or re-ask for the Order ID under any circumstances.
4. CHECK ORDER — Once the customer provides the ID, call `check_order_status` immediately.
5. RELAY STATUS — The `check_order_status` function will speak the result directly. Do NOT generate any response yourself after calling it.
6. OFFER HELP — After a short pause, ask if there's anything else you can assist with. Do this ONLY ONCE.
7. CLOSE OR FORWARD — 
   - If the customer asks for further help that is NOT about checking another order status, immediately call `forward_call`.
   - If the customer says no or nothing else is needed, call `end_conversation` to thank them and hang up.

ORDER ID HANDLING
- The Order ID is always exactly 4 digits.
- If a customer reads digits individually (e.g. "six one eight zero"), interpret it as the 4-digit number (e.g. 6180).
- Do NOT read the Order ID back to confirm. Just call `check_order_status` immediately with the provided ID.

STRICT RULES
- If the customer asks/queries about anything other than checking order status, you MUST call `forward_call` to redirect the call. Do NOT try to answer inquiries about refunds, cancellations, sales, or other things yourself.
- Do NOT ask for the Order ID more than once.
- Do NOT speak after `check_order_status` completes — it handles its own response and follow-up.
- Do NOT repeat offers to help."""

# ─── Bot Pipeline ──────────────────────────────────────────────────────────────

async def run_bot(transport: BaseTransport, handle_sigint: bool, call_uuid: str = None, host: str = None) -> None:
    """Set up and run the Pipecat pipeline."""
    from pipecat.audio.vad.vad_analyzer import VADParams

    state = {
        "language": "english"
    }

    llm = OpenAILLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILLMService.Settings(
            model="gpt-4o-mini",
            system_instruction=SYSTEM_PROMPT,
        ),
    )

    stt = SarvamSTTService(
        api_key=os.getenv("SARVAM_API_KEY"),
        sample_rate=8000,
        settings=SarvamSTTService.Settings(
            model="saaras:v3",
            language=None,
        ),
    )

    tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        sample_rate=24000,
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            language="en-IN",
            voice="simran",
        ),
    )

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def check_order_status(params: FunctionCallParams, order_id: str) -> None:
        """Check the current status of a customer's order from our system.

        Args:
            order_id: The 4-digit numeric order ID provided by the customer, e.g. "6180".
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
            is_dispatched = status.lower() == "dispatched"
            is_quoted = status.lower() == "quoted"

            lang = state["language"]
            if lang == "tamil":
                if is_dispatched:
                    speak_text = "உங்கள் ஆர்டர் நிலை அனுப்பப்பட்டது."
                elif is_quoted:
                    speak_text = "உங்கள் ஆர்டர் நிலை கோரப்பட்டது."
                else:
                    speak_text = f"உங்கள் ஆர்டர் நிலை {status}."
            elif lang == "malayalam":
                if is_dispatched:
                    speak_text = "നിങ്ങളുടെ ഓർഡർ സ്ഥിതി അയച്ചു."
                elif is_quoted:
                    speak_text = "നിങ്ങളുടെ ഓർഡർ സ്ഥിതി കോട്ട് ചെയ്തു."
                else:
                    speak_text = f"നിങ്ങളുടെ ഓർഡർ സ്ഥിതി {status}."
            else: # English
                if is_dispatched:
                    speak_text = "Your order status is Dispatched."
                elif is_quoted:
                    speak_text = "Your order status is Quoted."
                else:
                    speak_text = f"Your order status is {status}."

            # Speak the status, then pause 3 seconds, then ask for anything else
            import asyncio
            lang = state["language"]
            if lang == "tamil":
                follow_up = "உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
            elif lang == "malayalam":
                follow_up = "നിങ്ങൾക്ക് കൂടുതൽ സഹായം ആവശ്യമുണ്ടോ?"
            else:
                follow_up = "Is there anything else I can help you with?"

            await params.llm.push_frame(TTSSpeakFrame(speak_text))
            await asyncio.sleep(3.0)
            await params.llm.push_frame(TTSSpeakFrame(follow_up))
            await params.result_callback(
                f"Order status: {status}. Follow-up asked.",
                properties=FunctionCallResultProperties(run_llm=False),
            )

        except Exception as e:
            print(f"\n>>> [ZOHO API ERROR] Failed for order {order_id}: {e}\n")
            logger.error(f"Zoho API error for {order_id}: {e}")
            
            import asyncio
            lang = state["language"]
            if lang == "tamil":
                error_speak = "உங்கள் ஆர்டர் நிலையை என்னால் பெற முடியவில்லை."
                follow_up = "உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
            elif lang == "malayalam":
                error_speak = "നിങ്ങളുടെ ഓർഡർ വിവരങ്ങൾ ലഭ്യമല്ല."
                follow_up = "നിങ്ങൾക്ക് കൂടുതൽ സഹായം ആവശ്യമുണ്ടോ?"
            else:
                error_speak = "I was unable to retrieve your order status at this time."
                follow_up = "Is there anything else I can help you with?"

            await params.llm.push_frame(TTSSpeakFrame(error_speak))
            await asyncio.sleep(3.0)
            await params.llm.push_frame(TTSSpeakFrame(follow_up))
            await params.result_callback(
                "Error fetching order status. User notified.",
                properties=FunctionCallResultProperties(run_llm=False),
            )

    @tool_options(cancel_on_interruption=False, timeout_secs=5)
    async def set_language(params: FunctionCallParams, language: str) -> None:
        """Set the conversation and voice language. Call this immediately based on the language the customer speaks or asks their question in to lock the language settings.

        Args:
            language: The language used by the customer. Must be one of: "english", "tamil", or "malayalam".
        """
        print(f"\n>>> [SET LANGUAGE] Switching to: {language}")
        logger.info(f"Switching language to: {language}")

        lang_map = {
            "english": (Language.EN_IN, "en-IN"),
            "tamil": (Language.TA_IN, "ta-IN"),
            "malayalam": (Language.ML_IN, "ml-IN"),
        }

        lang_lower = language.lower().strip()
        if lang_lower in lang_map:
            stt_lang, tts_lang = lang_map[lang_lower]
            state["language"] = lang_lower

            # 1. Update settings directly on the service instances for instant effect
            await stt.set_language(stt_lang)
            tts._settings.language = tts_lang

            # 2. Queue update settings frames via worker to propagate down the pipeline
            await worker.queue_frames([
                STTUpdateSettingsFrame(delta=SarvamSTTService.Settings(language=stt_lang)),
                TTSUpdateSettingsFrame(delta=SarvamTTSService.Settings(language=tts_lang))
            ])

            # Restrict the LLM strictly to the chosen language
            context.add_message({
                "role": "system",
                "content": (
                    f"The user selected {language.upper()} ({tts_lang}). "
                    f"From now on, you MUST converse ONLY in {language.upper()} using its script. "
                    "Do NOT respond in English, Tamil, Malayalam, or any other language "
                    "except the one selected. Keep the rule absolute."
                )
            })

            await params.result_callback(
                f"Language set to {language} successfully.",
                properties=FunctionCallResultProperties(run_llm=True),
            )
        else:
            await params.result_callback(
                f"Unsupported language: {language}.",
                properties=FunctionCallResultProperties(run_llm=False),
            )

    @tool_options(cancel_on_interruption=False, timeout_secs=5)
    async def end_conversation(params: FunctionCallParams) -> None:
        """Hang up the phone call immediately. Call this function as soon as the user says thank you, says no more help is needed, or says goodbye to end the conversation."""
        print(f"\n>>> [END CONVERSATION] Hanging up call {call_uuid}...\n")
        logger.info(f"Ending conversation and closing call {call_uuid}")

        lang = state["language"]
        if lang == "tamil":
            goodbye = "எங்களை அழைத்தமைக்கு நன்றி, நல்ல நாள்!"
        elif lang == "malayalam":
            goodbye = "ഞങ്ങളെ വിളിച്ചതിന് നന്ദി, നല്ലൊരു ദിവസം ആശംസിക്കുന്നു!"
        else:
            goodbye = "Thank you for calling. Have a great day!"

        await params.llm.push_frame(TTSSpeakFrame(goodbye))

        # Call Plivo API to hang up the call after a short delay
        if call_uuid:
            import asyncio
            async def hangup_plivo_call():
                await asyncio.sleep(3.5) # let TTS finish playing
                try:
                    import plivo
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
            import asyncio
            async def cancel_worker_delayed():
                await asyncio.sleep(3.5)
                await worker.cancel()
            asyncio.create_task(cancel_worker_delayed())

        await params.result_callback(
            "Goodbye spoken. Call hanging up.",
            properties=FunctionCallResultProperties(run_llm=False),
        )

    @tool_options(cancel_on_interruption=False, timeout_secs=15)
    async def forward_call(params: FunctionCallParams, reason: str = "") -> None:
        """Forward the call to a customer support agent. Call this immediately if the customer's query/intent is NOT about checking order status, or if they ask to speak to a human, or have any other query.

        Args:
            reason: The reason for forwarding the call.
        """
        print(f"\n>>> [FORWARD CALL] Forwarding call {call_uuid} due to: {reason}\n")
        logger.info(f"Forwarding call {call_uuid} to support agent. Reason: {reason}")

        lang = state["language"]
        if lang == "tamil":
            speak_text = "உங்கள் அழைப்பை எங்கள் வாடிக்கையாளர் சேவை பிரதிநிதிக்கு மாற்றுகிறேன், தயவுசெய்து காத்திருக்கவும்."
        elif lang == "malayalam":
            speak_text = "ഞാൻ നിങ്ങളുടെ കോൾ ഞങ്ങളുടെ കസ്റ്റമർ സപ്പോർട്ട് ഏജന്റിലേക്ക് കൈമാറുകയാണ്, ദയവായി കാത്തിരിക്കുക."
        else:
            speak_text = "I am transferring your call to a customer support agent. Please hold on."

        await params.llm.push_frame(TTSSpeakFrame(speak_text))

        if call_uuid and host:
            import asyncio
            async def transfer_plivo_call():
                await asyncio.sleep(3.5) # Let TTS finish speaking
                try:
                    import plivo
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
            import asyncio
            async def cancel_worker_delayed():
                await asyncio.sleep(3.5)
                await worker.cancel()
            asyncio.create_task(cancel_worker_delayed())

        await params.result_callback(
            "Call forwarding initiated.",
            properties=FunctionCallResultProperties(run_llm=False),
        )

    context = LLMContext(tools=[check_order_status, set_language, end_conversation, forward_call])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    stop_secs=1.2,       # Natural 1.2-second gap before responding
                    start_secs=0.3,      # Ignore transient noises/echoes shorter than 0.3s
                )
            ),
            user_mute_strategies=[AlwaysUserMuteStrategy()],
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),       # Audio in from Plivo WebSocket
            stt,                     # Speech-to-Text (Sarvam)
            user_aggregator,         # Accumulate user turn
            llm,                     # LLM inference (OpenAI)
            tts,                     # Text-to-Speech (Sarvam)
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
        logger.info("Client connected — sending greeting directly")
        greeting = "Welcome to Goodwind Technologies. How can i help you ?"
        context.add_message({
            "role": "assistant",
            "content": greeting
        })
        await worker.queue_frames([TTSSpeakFrame(greeting)])

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):  # noqa: ANN001
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


# ─── Entry Points ──────────────────────────────────────────────────────────────

async def bot(runner_args: RunnerArguments, call_uuid: str = None, host: str = None) -> None:
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
    if hasattr(transport, "_params") and hasattr(transport._params, "serializer"):
        serializer = transport._params.serializer
        if hasattr(serializer, "_params") and hasattr(serializer._params, "auto_hang_up"):
            serializer._params.auto_hang_up = False
            logger.info("Disabled serializer auto_hang_up to allow call transfer/forwarding to succeed.")

    await run_bot(transport, runner_args.handle_sigint, call_uuid, host)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
