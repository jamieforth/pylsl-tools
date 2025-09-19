"""Test programme to simulate LSL streams."""

import argparse
import asyncio
import logging
import multiprocessing as mp
import threading
import time

from pylsl import local_clock

from pylsltools import ControlStates, socket_options
from pylsltools.logging import init_logging
from pylsltools.streams import (
    ControlReceiver,
    LslOutletOptions,
    StreamInfoData,
    TestDataStream,
    TestMarkerStream,
)

logger = logging.getLogger(__name__)


class Simulate:
    """Test stream generator."""

    controller = None
    control_states = ControlStates

    def __init__(
        self,
        # Data streams
        num_streams,
        functions,
        info,
        # Marker streams
        num_marker_streams,
        marker_functions,
        marker_info,
        # Outlets
        outlet_options,
        # Control
        sync,
        start_delay,
        latency,
        max_time,
        max_samples,
        control_name,
        # Logging
        log_queue,
    ):
        """Initialise simulation test.

        Optionally can receive messages from an input LSL control stream.
        """
        # Event to terminate the main process.
        self.stop_event = threading.Event()
        self._sentinel = None

        # Set class attributes.
        # Override channel count if more generator functions are provided.
        if info.channel_count < len(functions):
            info.channel_count = len(functions)
        if marker_info.channel_count < len(marker_functions):
            marker_info.channel_count = len(marker_functions)

        # Data streams
        self.num_streams = num_streams
        self.functions = functions
        self.info = info

        # Marker streams
        self.num_marker_streams = num_marker_streams
        self.marker_functions = marker_functions
        self.marker_info = marker_info

        # Outlets
        self.outlet_options = outlet_options

        # Control
        self.sync = sync
        self.start_delay = start_delay
        self.latency = latency
        self.max_time = max_time
        self.max_samples = max_samples
        if control_name:
            self.controller = ControlReceiver(control_name)

        # Barrier for sub-process synchronisation.
        self.barrier = mp.Barrier(num_streams + num_marker_streams)
        # Queue for receiving messages from sub-processes.
        self.recv_message_queue = mp.Queue()
        # Controller for receiving messages from a control stream.

        # Logging
        self.log_queue=log_queue

    def start(self):
        """Start test streams with synchronised start time."""

        # Start remote control thread if initialised.
        if self.controller:
            self.controller.start()

        # Create sub-processes
        data_streams = [
            TestDataStream(
                self.info,
                self.outlet_options,
                stream_idx,
                self.functions,
                self.barrier,
                max_time=self.max_time,
                max_samples=self.max_samples,
                # Each sub-process has a unique recv_message queue.
                recv_message_queue=mp.Queue(),
                # Each sub-process shares the same queue for sending message to
                # the main process.
                send_message_queue=self.recv_message_queue,
                log_queue=self.log_queue,
                log_level=logger.getEffectiveLevel()
            )
            for stream_idx in range(self.num_streams)
        ]

        marker_streams = [
            TestMarkerStream(
                self.marker_info,
                self.outlet_options,
                stream_idx,
                self.marker_functions,
                self.barrier,
                max_time=self.max_time,
                max_samples=self.max_samples,
                # Each sub-process has a unique recv_message queue.
                recv_message_queue=mp.Queue(),
                # Each sub-process shares the same queue for sending message to
                # the main process.
                send_message_queue=self.recv_message_queue,
            )
            for stream_idx in range(self.num_marker_streams)
        ]

        self.streams = data_streams + marker_streams

        for stream in self.streams:
            # Start sub-processes.
            stream.start()

        # Initialise start time.
        if not self.controller:
            if self.start_delay:
                print(f"Start delay: {self.start_delay}")
                time.sleep(self.start_delay)
            if self.sync:
                # Get start time in the main thread to synchronise streams.
                start_time = local_clock() + self.latency
            else:
                start_time = None
            self.send_message_to_streams(
                {
                    "state": self.control_states.START,
                    "time_stamp": start_time,
                    "latency": self.latency,
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
                if message is self._sentinel:
                    logger.debug("Stream returned")
                    # Notify resolver sentinel has been handled.
                    self.resolver.task_done()
                    break
                logger.debug(f"Sub-process message: {message}")
        finally:
            logger.debug("End stream messaging.")
            self.stop()

    async def recv_from_controller(self):
        """Coroutine to handle controller messages."""
        try:
            while not self.controller.is_stopped() or (
                not self.controller.send_message_queue.empty()
            ):
                # Loop here waiting for messages.
                # Blocking.
                # FIXME: Refactor like resolver.
                message = await asyncio.to_thread(self.controller.get_message)
                if message is self._sentinel:
                    logger.debug("Controller thread returned")
                    # Notify resolver sentinel has been handled.
                    self.resolver.task_done()
                    break
                logger.debug(f"Controller message: {message}")
                self.send_message_to_streams(message)
        finally:
            logger.debug("End controller messaging.")
            self.stop()

    def streams_stopped(self):
        for stream in self.streams:
            if not stream.is_stopped():
                return False
        return True

    def stop(self):
        print("STOP")
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
        description="""Create test LSL data streams using synthetic data.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
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

    socket_options.add_stream_args(parser)

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
        "--sync",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Synchronise timestamps across all streams.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print extra debugging information."
    )

    socket_options.add_socket_args(parser, inlet=True, outlet=True)

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

    # Logging
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG

    log_queue, log_listener = init_logging(log_level)
    logger.debug("Logging initialised")

    if args.controller == "external":
        control_name = args.control_name
        latency = None
        start_delay = None
    if args.controller == "internal":
        control_name = None
        latency = args.latency
        start_delay = args.start_delay

    info = StreamInfoData(
        args.name,
        args.content_type,
        args.num_channels,
        args.sample_rate,
        args.channel_format,
        args.source_id,
    )

    marker_info = StreamInfoData(
        args.marker_name,
        args.marker_content_type,
        args.num_marker_channels,
        args.marker_sample_rate,
        str,
        args.marker_source_id,
    )

    outlet_options = LslOutletOptions(
        args.outlet_max_buffer_size,
        args.outlet_max_chunk_size,
    )

    simulate = Simulate(
        # Data streams
        args.num_streams,
        args.fn,
        info,
        # Marker streams
        args.num_marker_streams,
        args.marker_fn,
        marker_info,
        # Outlet
        outlet_options,
        # Control
        sync=args.sync,
        start_delay=start_delay,
        latency=latency,
        max_time=args.max_time,
        max_samples=args.max_samples,
        control_name=control_name,
        log_queue=log_queue,
    )
    try:
        simulate.start()
    except Exception as exc:
        # Stop all streams if one raises an error.
        simulate.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main.")
        simulate.stop()
    finally:
        print("Main exit.")
