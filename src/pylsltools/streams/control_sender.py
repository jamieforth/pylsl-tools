import asyncio
import json
import platform

from aioconsole import ainput
from pylsl import StreamOutlet, local_clock

from pylsltools import ControlStates
from pylsltools.streams import MarkerStreamThread


class ControlSender(MarkerStreamThread):
    """Control stream sending thread."""

    control_states = ControlStates

    def __init__(
        self,
        name,
        latency=0.5,
        *,
        content_type="control",
        source_id="",
        manufacturer="pylsltools",
        debug=False,
        **kwargs,
    ):
        # Use host name to identify source if unspecified. If stream is
        # interrupted due to network outage or the controller is
        # restarted receivers should be able to recover.
        if not source_id:
            source_id = platform.node()

        super().__init__(
            name, content_type, source_id=source_id, manufacturer=manufacturer, **kwargs
        )

        # Set class attributes.
        self.latency = latency
        self.debug = debug

    def run(self):
        info = self.make_stream_info()

        self.outlet = StreamOutlet(info, chunk_size=1)

        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.cli())

    async def cli(self):
        """REPL interface for sending control messages."""
        while not self.is_stopped():
            state = await ainput("Enter a command: start, pause, stop.\n")
            if state == "start":
                self.outlet.push_sample(
                    [
                        json.dumps(
                            {
                                "state": self.control_states.START,
                                "latency": self.latency,
                            }
                        )
                    ],
                    local_clock() + self.latency,
                )
            elif state == "pause":
                self.outlet.push_sample(
                    [json.dumps({"state": self.control_states.PAUSE})],
                    local_clock() + self.latency,
                )
            elif state == "stop":
                self.outlet.push_sample(
                    [json.dumps({"state": self.control_states.STOP})],
                    local_clock() + self.latency,
                )
                self.stop()
            else:
                print(f"Undefined command: {state}")
