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


async def bot(runner_args: RunnerArguments) -> None:
    """Entry point picked up by Pipecat's local dev runner (SmallWebRTC)."""

    transport_params = {
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    # call_uuid=None / host=None disables the Plivo hangup + transfer REST calls
    # (those branches are already guarded with `if call_uuid:` / `if host:` in
    # run_bot, so they just no-op locally — end_conversation and forward_call
    # will still be called by the model and logged, just without an actual
    # phone leg to hang up or transfer).
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