"""Test programme to simulate LSL streams."""

import argparse
import asyncio
import multiprocessing as mp
import threading
import time

from pylsl import local_clock

from pylsltools import ControlStates
from pylsltools.streams import ControlReceiver, TestDataStream, TestMarkerStream


class Simulate:
    """Test stream generator."""

    controller = None
    control_states = ControlStates

    def __init__(
        self,
        # Data streams
        num_streams,
        functions,
        name,
        content_type,
        channel_count,
        nominal_srate,
        channel_format,
        source_id,
        # Marker streams
        num_marker_streams,
        marker_channel_count,
        marker_nominal_srate,
        marker_functions,
        marker_name,
        marker_content_type,
        marker_source_id,
        # Control stream
        control_name=None,
        debug=False,
    ):
        """Initialise simulation test.

        Optionally can receive messages from an input LSL control stream.
        """
        # Event to terminate the main process.
        self.stop_event = threading.Event()

        # Set class attributes.
        # Override channel count if more generator functions are provided.
        if channel_count < len(functions):
            channel_count = len(functions)
        if marker_channel_count < len(marker_functions):
            marker_channel_count = len(marker_functions)

        # Data streams
        self.num_streams = num_streams
        self.functions = functions
        self.name = name
        self.content_type = content_type
        self.channel_count = channel_count
        self.nominal_srate = nominal_srate
        self.channel_format = channel_format
        self.source_id = source_id

        # Marker streams
        self.num_marker_streams = num_marker_streams
        self.marker_functions = marker_functions
        self.marker_name = marker_name
        self.marker_content_type = marker_content_type
        self.marker_channel_count = marker_channel_count
        self.marker_nominal_srate = marker_nominal_srate
        self.marker_source_id = marker_source_id

        # Control stream
        if control_name:
            self.controller = ControlReceiver(control_name, debug=debug)

        self.debug = debug

        # Barrier for sub-process synchronisation.
        self.barrier = mp.Barrier(num_streams + num_marker_streams)
        # Queue for receiving messages from sub-processes.
        self.recv_message_queue = mp.SimpleQueue()
        # Controller for receiving messages from a control stream.

    def start(
        self,
        sync,
        max_time,
        max_samples,
        chunk_size,
        max_buffered,
        latency=0.2,
        start_delay=0,
    ):
        """Start test streams with synchronised start time."""
        # Start remote control thread if initialised.
        if self.controller:
            self.controller.start()

        # Create sub-processes
        data_streams = [
            TestDataStream(
                stream_idx,
                self.functions,
                self.name,
                self.content_type,
                self.channel_count,
                self.nominal_srate,
                channel_format=self.channel_format,
                source_id=self.source_id,
                max_time=max_time,
                max_samples=max_samples,
                chunk_size=chunk_size,
                max_buffered=max_buffered,
                # Each sub-process has a unique recv_message queue.
                recv_message_queue=mp.SimpleQueue(),
                # Each sub-process shares the same queue for sending message to
                # the main process.
                send_message_queue=self.recv_message_queue,
                barrier=self.barrier,
                debug=self.debug,
            )
            for stream_idx in range(self.num_streams)
        ]

        marker_streams = [
            TestMarkerStream(
                stream_idx,
                self.marker_functions,
                self.marker_name,
                self.marker_content_type,
                self.marker_channel_count,
                self.marker_nominal_srate,
                source_id=self.marker_source_id,
                max_time=max_time,
                max_samples=max_samples,
                chunk_size=chunk_size,
                max_buffered=max_buffered,
                # Each sub-process has a unique recv_message queue.
                recv_message_queue=mp.SimpleQueue(),
                # Each sub-process shares the same queue for sending message to
                # the main process.
                send_message_queue=self.recv_message_queue,
                barrier=self.barrier,
                debug=self.debug,
            )
            for stream_idx in range(self.num_marker_streams)
        ]

        self.streams = data_streams + marker_streams

        for stream in self.streams:
            # Start sub-processes.
            stream.start()

        # Initialise start time.
        if not self.controller:
            if start_delay:
                print(f"Start delay: {start_delay}")
                time.sleep(start_delay)
            if sync:
                # Get start time in the main thread to synchronise streams.
                start_time = local_clock() + latency
            else:
                start_time = None
            self.send_message_to_streams(
                {
                    "state": self.control_states.START,
                    "time_stamp": start_time,
                    "latency": latency,
                }
            )

        # Use asyncio to handle asynchronous messages in the main thread.
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.handle_messages())

        for stream in self.streams:
            # Block until all child processes return.
            stream.join()

        if self.controller:
            # Block until controller returns.
            self.controller.join()

    async def handle_messages(self):
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.recv_from_streams())
                if self.controller:
                    tg.create_task(self.recv_from_controller())
        finally:
            print("End handle messages.")

    def send_message_to_streams(self, message):
        for stream in self.streams:
            if stream.is_alive():
                stream.recv_message_queue.put(message)

    async def recv_from_streams(self):
        """Coroutine to handle messages from sub-processes."""
        try:
            while not self.streams_stopped() or (not self.recv_message_queue.empty()):
                # Block here until message received.
                message = await asyncio.to_thread(self.recv_message_queue.get)
                if self.debug and message:
                    print(f"{__class__} sub-process message: {message}")
        finally:
            if self.debug:
                print("End stream messaging.")
            self.stop()

    async def recv_from_controller(self):
        """Coroutine to handle controller messages."""
        try:
            while not self.controller.is_stopped() or (
                not self.controller.send_message_queue.empty()
            ):
                # Loop here waiting for messages.
                # Blocking.
                message = await asyncio.to_thread(self.controller.get_message)
                if self.debug and message:
                    print(f"{self.__class__} controller message: {message}")
                if message:
                    self.send_message_to_streams(message)
        finally:
            if self.debug:
                print("End controller messaging.")
            self.stop()

    def streams_stopped(self):
        for stream in self.streams:
            if not stream.is_stopped():
                return False
        return True

    def stop(self):
        if not self.is_stopped():
            self.stop_event.set()
        # Stop all stream processes.
        for stream in self.streams:
            if not stream.is_stopped():
                stream.stop()
        for stream in self.streams:
            stream.join()
        if self.controller and not self.controller.is_stopped():
            self.controller.stop()
            self.controller.join()

    def is_stopped(self):
        return self.stop_event.is_set()


def main():
    """Generate synthetic LSL streams."""

    # Use multiprocessing spawn on all platforms.
    mp.set_start_method("spawn")

    parser = argparse.ArgumentParser(
        description="""Create test LSL data streams using synthetic data."""
    )

    # Data streams
    parser.add_argument(
        "-n",
        "--num-streams",
        default=1,
        type=int,
        help="Number of streams to simulate.",
    )
    parser.add_argument(
        "-c",
        "--num-channels",
        default=1,
        type=int,
        help="Number of channels per stream.",
    )
    parser.add_argument(
        "-s",
        "--sample-rate",
        default=512,
        type=int,
        help="Synthetic data stream sample rate.",
    )
    parser.add_argument(
        "--fn",
        nargs="+",
        default=["counter"],
        choices=[
            "stream-id",
            "stream-seq",
            "counter",
            "counter+",
            "counter-mod-fs",
            "impulse",
            "sine",
            "sine+",
        ],
        help="""Function(s) to use to simulate channel data. If multiple
        function names are provided the last function will be reused to match
        the number of channels.""",
    )
    parser.add_argument(
        "--name", help="Additional identifier to append to stream name."
    )
    parser.add_argument("--content-type", default="eeg", help="Stream content type.")
    parser.add_argument(
        "--channel-format",
        default="float32",
        choices=["float32", "double64", "string", "int64", "int32", "int16", "int8"],
        help="Channel datatype.",
    )
    parser.add_argument(
        "--source-id", default="", help="Unique identifier for stream source."
    )

    # Marker streams
    parser.add_argument(
        "-m",
        "--num-marker-streams",
        default=0,
        type=int,
        help="Number of marker streams to simulate.",
    )
    parser.add_argument(
        "--num-marker-channels",
        default=1,
        type=int,
        help="Number of channels per marker stream.",
    )
    parser.add_argument(
        "--marker-sample-rate",
        default=1,
        type=int,
        help="Synthetic marker stream sample rate.",
    )
    parser.add_argument(
        "--marker-fn",
        nargs="+",
        default=["counter"],
        choices=[
            "stream-id",
            "stream-seq",
            "counter",
            "counter+",
            "counter-mod-fs",
            "impulse",
            "sine",
            "sine+",
        ],
        help="""Function(s) to use to simulate marker channel data. If multiple
        function names are provided the last function will be reused to match
        the number of channels.""",
    )
    parser.add_argument(
        "--marker-name", help="Additional identifier to append to marker stream name."
    )
    parser.add_argument(
        "--marker-content-type", default="marker", help="Stream content type."
    )
    parser.add_argument(
        "--marker-source-id",
        default="",
        help="Unique identifier for marker stream source.",
    )

    # Simulation arguments.
    parser.add_argument(
        "--max-time", type=float, help="Maximum run-time for test streams."
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        help="""Maximum number of samples to generate by each test stream.""",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="""Desired outlet chunk size in samples. Inlets can override
        this.""",
    )
    parser.add_argument(
        "--max-buffered",
        type=int,
        default=360,
        help="""Maximum amount of data to buffer - in seconds if there is a
        nominal sampling rate, otherwise x100 in samples.""",
    )
    parser.add_argument(
        "--sync",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Synchronise timestamps across all streams.",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print extra debugging information."
    )

    # Controller sub-commands
    subparsers = parser.add_subparsers(
        title="Controllers", dest="controller", required=True
    )
    external_control_parser = subparsers.add_parser("external")
    external_control_parser.add_argument(
        "control_name",
        help="Control stream name. Control stream will set latency.",
    )

    internal_control_parser = subparsers.add_parser("internal")
    internal_control_parser.add_argument(
        "--latency",
        type=float,
        default=0.2,
        help="Scheduling latency in seconds.",
    )
    internal_control_parser.add_argument(
        "--start-delay",
        type=float,
        default=0,
        help="Start time delay in seconds.",
    )
    args = parser.parse_args()

    if args.controller == "external":
        control_name = args.control_name
        latency = None
        start_delay = None
    if args.controller == "internal":
        control_name = None
        latency = args.latency
        start_delay = args.start_delay

    simulate = Simulate(
        # Data streams
        args.num_streams,
        args.fn,
        args.name,
        args.content_type,
        args.num_channels,
        args.sample_rate,
        args.channel_format,
        args.source_id,
        # Marker streams
        num_marker_streams=args.num_marker_streams,
        marker_functions=args.marker_fn,
        marker_name=args.marker_name,
        marker_content_type=args.marker_content_type,
        marker_channel_count=args.num_marker_channels,
        marker_nominal_srate=args.marker_sample_rate,
        marker_source_id=args.marker_source_id,
        # Control stream
        control_name=control_name,
        debug=args.debug,
    )
    try:
        simulate.start(
            args.sync,
            latency=latency,
            start_delay=start_delay,
            max_time=args.max_time,
            max_samples=args.max_samples,
            chunk_size=args.chunk_size,
            max_buffered=args.max_buffered,
        )
    except Exception as exc:
        # Stop all streams if one raises an error.
        simulate.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main.")
        simulate.stop()
    finally:
        print("Main exit.")
