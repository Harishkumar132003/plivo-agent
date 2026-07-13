"""
Local test runner — NOT used in production.

Lets you test the exact same run_bot() logic (greeting, tools, language
switching, transcript capture, DB save) from your browser mic instead of
a real Plivo phone call. Your production bot.py / Plivo webhook are
completely untouched by this file.

Run:
    uv run local_test.py
    # or: python local_test.py

Then open the URL it prints (usually http://localhost:7860) in your
browser, allow mic access, and talk to the bot.
"""

from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.transports.base_transport import TransportParams

from bot import run_bot
from audio_logger import LoggingRNNoiseFilter


async def bot(runner_args: RunnerArguments) -> None:
    """Entry point picked up by Pipecat's local dev runner (SmallWebRTC)."""

    # audio_filter = LoggingRNNoiseFilter(run_id="local_test")

    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            # audio_in_filter=audio_filter,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(
        transport,
        runner_args.handle_sigint,
        call_uuid=None,
        host=None,
        caller_number="1234567890",
    )


if __name__ == "__main__":
    from pipecat.runner.run import main
    main()