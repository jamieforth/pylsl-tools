"""Script to monitor data streams over LSL."""

import argparse
import asyncio
import os
import queue
import sys
import textwrap
from threading import Event, Thread

from pylsl import ContinuousResolver

from pylsltools.streams import MonitorReceiver
from pylsltools.utils import dev_to_name


class Monitor:
    """Monitor matching streams."""

    def __init__(self, pred, json=False, debug=False):
        self.pred = pred
        self.json = json
        self.debug = debug
        self.stop_event = Event()
        self.active_streams = {}
        # For receiving messages from sub-processes.
        self.recv_message_queue = queue.SimpleQueue()
        # Dictionary to keep track of all seen streams and status
        # logging.
        self.stream_log = {}

    def start(self):
        self.thread = Thread(target=self.run)
        self.thread.start()

        print("Starting message handler.")
        # Use asyncio to handle asynchronous messages in the main thread.
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.handle_messages())

        # Block main thread until resolver thread returns.
        print("Handle messages returned, waiting for resolver.")
        self.thread.join()
        print("after join")

    def run(self):
        resolver = ContinuousResolver(pred=self.pred, forget_after=1)

        while not self.is_stopped():
            # FIXME: Improve this? Continuous resolver always returns a new
            # StreamInfo object so we need to continually regenerate the key to
            # check if we've seen it before.
            streams = resolver.results()
            for stream in streams:
                stream_key = self.make_stream_key(stream)
                if stream_key not in self.active_streams.keys():
                    new_stream = MonitorReceiver(
                        stream.name(),
                        stream.type(),
                        stream.hostname(),
                        stream.source_id(),
                        send_message_queue=self.recv_message_queue,
                        json=self.json,
                        debug=self.debug,
                    )
                    self.active_streams[stream_key] = new_stream
                    new_stream.start()
                    print(f"New stream added {stream.name()}.")
            self.cleanup()
            self.stop_event.wait(1)
        print("Resolver stopped")

    def stop(self):
        """Stop monitor thread and all monitor stream threads."""
        if not self.is_stopped():
            self.stop_event.set()
            for stream in self.active_streams.values():
                stream.stop()
            for stream in self.active_streams.values():
                stream.join()
            # Unblock receive message queue.
            # self.recv_message_queue.put('')

    async def handle_messages(self):
        try:
            # async with asyncio.TaskGroup() as tg:
            #     tg.create_task(self.recv_from_streams())
            await self.recv_from_streams()
        finally:
            if self.debug:
                print("End handle messages.")

    async def recv_from_streams(self):
        """Coroutine to handle messages from other threads."""
        try:
            while not self.is_stopped():
                if not self.recv_message_queue.empty():
                    # Block here until message received.
                    message = self.recv_message_queue.get(timeout=0.1)
                    if message:
                        self.stream_log[message["source_id"]] = message
                        if self.debug:
                            print(f"{__class__} received message: {message}")
                        else:
                            self.print_log()
                await asyncio.sleep(0.1)
        finally:
            if self.debug:
                print(self.__class__, "End stream messaging.")
            # self.stop()

    def print_log(self):
        # if 'win32' in sys.platform:
        #     os.system('cls')
        # else:
        #     # Posix
        #     os.system('clear')

        for stream, state in sorted(self.stream_log.items()):
            # FIXME: Add custom hostname mapping.
            print(
                textwrap.fill(
                    textwrap.dedent(f"""\
            {state["name"]} \t
            sample count: {state["sample_count"]} \t
            new samples: {state["sample_diff"]:04} \t
            stream OK: {not state["stream_lost"]}
            """),
                    200,
                )
            )

    def is_stopped(self):
        return self.stop_event.is_set()

    def cleanup(self):
        for stream_key in list(self.active_streams):
            stream = self.active_streams[stream_key]
            if stream.is_stopped():
                print(f"Removing: {stream.name}")
                del self.active_streams[stream_key]
        # print(f'Total active streams: {len(self.active_streams)}')

    def make_stream_key(self, stream):
        key = ":".join(
            [
                stream.name(),
                stream.source_id(),
                stream.hostname(),
                str(stream.channel_count()),
            ]
        )
        return key


def main():
    """Monitor marker streams."""
    parser = argparse.ArgumentParser(
        description="""Create an LSL
    monitor."""
    )
    parser.add_argument(
        "-p", "--pred", default="", help="Predicate string to resolve monitor streams."
    )
    parser.add_argument("--json", action="store_true", help="Receive JSON messages.")
    parser.add_argument(
        "--debug", action="store_true", help="Print extra debugging information."
    )

    args = parser.parse_args()

    # Add additional predicates.
    pred = args.pred

    if len(pred) > 0:
        pred = "starts-with(name, '_monitor_') and " + pred
    else:
        pred = "starts-with(name, '_monitor_')"

    monitor = Monitor(pred, json=args.json, debug=args.debug)

    # Start continuous resolver and block unless keyboard interrupt.
    try:
        monitor.start()
    except Exception as exc:
        monitor.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main.")
        monitor.stop()
    print("Main exit.")
