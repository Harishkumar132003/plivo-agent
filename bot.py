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
from pipecat.frames.frames import LLMRunFrame, TTSSpeakFrame, STTUpdateSettingsFrame, TTSUpdateSettingsFrame
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

SYSTEM_PROMPT = """You are a friendly and professional customer support voice agent for Wizzgeeks.
Your job is to assist customers who are calling to check their order status.

IMPORTANT RULES:
- You are in a PHONE CALL. Keep responses SHORT and natural for speech — 1 or 2 sentences max.
- Do NOT use special characters, markdown, bullet points, or emojis.
- Speak clearly and naturally, like a real human customer support agent.
- You must respond in the language chosen by the customer.

CONVERSATION FLOW:
1. Greet the customer warmly and ask them to select a language: English, Tamil, or Malayalam. (Spoken automatically by Plivo XML at startup).
2. Call `set_language` immediately when they select a language. The tool will automatically speak the language switch confirmation and ask them for their 4-digit Order ID.
3. Once the language is set, do NOT say anything else. Just wait for the customer to say their 4-digit Order ID.
4. When the customer gives their Order ID, call check_order_status immediately. Do not say any conversational filler, confirmation, or unwanted statements.
5. Relay the order status result naturally and clearly in the selected language.
6. Ask if there is anything else you can help with.
7. If not, or if they say thank you / goodbye / no more help needed, call the `end_conversation` tool immediately to hang up. Do not say any final goodbye yourself.

ORDER ID EXTRACTION:
- The Order ID is always a 4-digit number.
- If the customer says digit by digit (e.g. "six one eight zero"), treat it as 6180.
- Do not say or repeat the order ID back to the customer before checking.

DO NOT make up order status. Only relay what check_order_status returns."""


# ─── Bot Pipeline ──────────────────────────────────────────────────────────────

async def run_bot(transport: BaseTransport, handle_sigint: bool, call_uuid: str = None) -> None:
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
            language=Language.EN_IN,
        ),
    )

    tts = SarvamTTSService(
        api_key=os.getenv("SARVAM_API_KEY"),
        sample_rate=8000,
        settings=SarvamTTSService.Settings(
            model="bulbul:v3",
            language="en-IN",
            voice="ishita",
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
                    speak_text = "உங்கள் ஆர்டர் நிலை அனுப்பப்பட்டது. உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
                elif is_quoted:
                    speak_text = "உங்கள் ஆர்டர் நிலை கோரப்பட்டது. உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
                else:
                    speak_text = f"உங்கள் ஆர்டர் நிலை {status}. உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
            elif lang == "malayalam":
                if is_dispatched:
                    speak_text = "നിങ്ങളുടെ ഓർഡർ സ്ഥിതി അയച്ചു. നിങ്ങൾക്ക് കൂടുതൽ സഹായം ആവശ്യമുണ്ടോ?"
                elif is_quoted:
                    speak_text = "നിങ്ങളുടെ ഓർഡർ സ്ഥിതി കോട്ട് ചെയ്തു. നിങ്ങൾക്ക് കൂടുതൽ സഹായം ആവശ്യമുണ്ടോ?"
                else:
                    speak_text = f"നിങ്ങളുടെ ഓർഡർ സ്ഥിതി {status}. നിങ്ങൾക്ക് കൂടുതൽ സഹായം ആവശ്യമുണ്ടോ?"
            else: # English
                if is_dispatched:
                    speak_text = "Your order status is Dispatched. Do you need help with anything else?"
                elif is_quoted:
                    speak_text = "Your order status is Quoted. Do you need help with anything else?"
                else:
                    speak_text = f"Your order status is {status}. Do you need help with anything else?"

            await params.llm.push_frame(TTSSpeakFrame(speak_text))
            await params.result_callback(f"The order status has been communicated directly to the user in their language: '{speak_text}'. Do not repeat the status or ask again; just wait for their response.")

        except Exception as e:
            print(f"\n>>> [ZOHO API ERROR] Failed for order {order_id}: {e}\n")
            logger.error(f"Zoho API error for {order_id}: {e}")
            
            lang = state["language"]
            if lang == "tamil":
                error_speak = "உங்கள் ஆர்டர் நிலையை என்னால் பெற முடியவில்லை. உங்களுக்கு வேறு ஏதேனும் உதவி தேவையா?"
            elif lang == "malayalam":
                error_speak = "നിങ്ങളുടെ ഓർഡർ വിവരങ്ങൾ ലഭ്യമല്ല. നിങ്ങൾക്ക് കൂടുതൽ സഹായം ആവശ്യമുണ്ടോ?"
            else:
                error_speak = "I was unable to retrieve your order status at this time. Do you need help with anything else?"
                
            await params.llm.push_frame(TTSSpeakFrame(error_speak))
            await params.result_callback("An error occurred. The user has been notified. Do not repeat the error message; just wait for their response.")

    @tool_options(cancel_on_interruption=False, timeout_secs=5)
    async def set_language(params: FunctionCallParams, language: str) -> None:
        """Set the conversation and voice language. Call this immediately when the customer states their language preference.

        Args:
            language: The language selected by the customer. Must be one of: "english", "tamil", or "malayalam".
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

            confirmations = {
                "english": "Language set to English. Please tell me your 4-digit Order ID.",
                "tamil": "மொழி தமிழ் என மாற்றப்பட்டது. உங்கள் 4 இலக்க ஆர்டர் ஐடியை கூறவும்.",
                "malayalam": "ഭാഷ മലയാളത്തിലേക്ക് മാറ്റിയിരിക്കുന്നു. ദയവായി നിങ്ങളുടെ 4 അക്ക ഓർഡർ ഐഡി പറയുക."
            }
            confirm_text = confirmations.get(lang_lower, "Language updated.")
            await params.llm.push_frame(TTSSpeakFrame(confirm_text))

            await params.result_callback(f"Language set to {language} and user was prompted with: '{confirm_text}'. Do not say anything else; just wait for their 4-digit Order ID.")
        else:
            await params.result_callback(f"Unsupported language: {language}")

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

        await params.result_callback("The goodbye message has been spoken and the call is hanging up.")

    context = LLMContext(tools=[check_order_status, set_language, end_conversation])
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
        greeting = "Welcome to Wizzgeeks Support. Please select your preferred language. Say English, Tamil, or Malayalam."
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

async def bot(runner_args: RunnerArguments, call_uuid: str = None) -> None:
    """Main bot entry point compatible with Pipecat Cloud."""

    transport_params = {
        "plivo": lambda: FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)
    await run_bot(transport, runner_args.handle_sigint, call_uuid)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
