"""Relay streams with optional remote control."""

import argparse
import asyncio
import logging
import multiprocessing as mp
import platform
from logging.handlers import QueueHandler
from threading import Event, Thread

from pylsl import ContinuousResolver

import pylsltools.resolve as lsl_resolve
from pylsltools import ControlStates, socket_options
from pylsltools.logging import init_logging
from pylsltools.streams import (
    ControlReceiver,
    LslInletOptions,
    LslOutletOptions,
    RelayStream,
)

logger = logging.getLogger(__name__)


class Relay:
    """Relay matching streams."""

    controller = None
    control_states = ControlStates

    def __init__(
        self,
        resolver,
        inlet_options,
        outlet_options,
        re_encode_timestamps,
        output,
        monitor,
        monitor_interval,
        control_name,
        log_queue,
    ):
        # Event to terminate the main process.
        self.stop_event = Event()
        self._sentinel = None

        # Set class attributes.
        self.resolver = resolver
        self.inlet_options = inlet_options
        self.outlet_options = outlet_options
        self.re_encode_timestamps = re_encode_timestamps
        self.output = output
        self.monitor = monitor
        self.monitor_interval = monitor_interval
        self.control_name = control_name
        self.log_queue = log_queue

        self.active_streams = {}
        # For receiving messages from sub-processes.
        self.recv_message_queue = mp.Queue()
        # For receiving messages from a controller thread.
        if control_name:
            self.controller = ControlReceiver(control_name)

    def start(self):
        # Start remote control thread if initialised.
        if self.controller:
            self.controller.start()

        # Use asyncio to handle asynchronous messages in the main thread.
        logger.debug("Start handle messages")
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.handle_messages())
        logger.debug("End handle messages")

        # # TODO: Wrap this in a class or co-routine.
        # self.thread = Thread(
        #     target=self.run,
        #     args=[
        #         # FIXME: Only inlet.
        #         self.inletParams.max_chunk_size,
        #         self.inletParams.max_buffer_size,
        #         self.re_encode_timestamps,
        #         self.output,
        #         self.monitor,
        #         self.monitor_interval,
        #     ],
        # )
        # self.thread.start()

    async def handle_messages(self):
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.resolver.task())
                tg.create_task(self.stream_manager_task())
                # tg.create_task(self.recv_from_streams())
        # except* Exception as exc:
        #     print(exc)
        #     raise exc
        finally:
            logger.debug("End handle messages task group")

    async def stream_manager_task(self):
        """Coroutine to handle messages from resolver."""
        try:
            while not self.is_stopped():
                # Await until message received.
                message = await self.resolver.get()
                if message is self._sentinel:
                    logger.debug("Resolver thread returned")
                    # Notify resolver sentinel has been handled.
                    self.resolver.task_done()
                    break
                match message[0]:
                    case "NEW":
                        logger.debug((f"New stream: {message[1].name}"))
                        self.create_relay_stream(message[1])
                    case "LOST":
                        logger.debug((f"Lost stream: {message[1].name}"))
                    case _:
                        logger.debug(f"Unknown state: {message}")
                # Notify resolver message has been handled.
                self.resolver.task_done()
        finally:
            logger.debug("End stream manager task")

        if self.controller:
            # Block until controller returns.
            self.controller.join()

        # Block until resolver thread returns.
        self.thread.join()

    def create_relay_stream(self, info):
        new_stream = RelayStream(
            info,
            self.inlet_options,
            self.outlet_options,
            re_encode_timestamps=self.re_encode_timestamps,
            output=self.output,
            monitor=self.monitor,
            monitor_interval=self.monitor_interval,
            # Each sub-process has a unique recv_message queue.
            recv_message_queue=mp.Queue(),
            # Each sub-process shares the same queue for sending message to the
            # main process.
            send_message_queue=self.recv_message_queue,
            # Each sub-process shares a log queue.
            log_queue=self.log_queue,
            log_level=logger.getEffectiveLevel()
        )
        stream_key = info.key()
        self.active_streams[stream_key] = new_stream
        new_stream.start()
        logger.debug(f"New stream added: {info.name}.")
        # FIXME: With --no-inlet-recover we keep processes around forever, just
        # in case the stream comes back.
        self.remove_lost_streams()

    # FIXME: Not actually used.
    # async def handle_messages(self):
    #     try:
    #         async with asyncio.TaskGroup() as tg:
    #             tg.create_task(self.recv_from_streams())
    #             if self.controller:
    #                 tg.create_task(self.recv_from_controller())
    #     finally:
    #         print("End handle messages.")

    # def send_message_to_streams(self, message):
    #     for stream in self.active_streams.values():
    #         if stream.is_alive():
    #             stream.recv_message_queue.put(message)

    # async def recv_from_streams(self):
    #     """Coroutine to handle messages from sub-processes."""
    #     try:
    #         while not self.is_stopped() or (not self.recv_message_queue.empty()):
    #             # Block here until message received.
    #             message = await asyncio.to_thread(self.recv_message_queue.get)
    #             if message is self._sentinel:
    #                 #logger.debug("Resolver thread returned")
    #                 # Notify resolver sentinel has been handled.
    #                 #self.resolver.task_done()
    #                 break
    #             logger.debug(f"Sub-process message: {message}")
    #     finally:
    #         logger.debug("End stream messaging.")
    #         self.stop()

    # async def recv_from_controller(self):
    #     """Coroutine to handle controller messages."""
    #     try:
    #         while not self.controller.is_stopped() or (
    #             not self.controller.send_message_queue.empty()
    #         ):
    #             # Loop here waiting for messages.
    #             # Blocking.
    #             # FIXME: Controller using timeout, use either sentinel or make
    #             # threaded streams asyncio?
    #             message = await asyncio.to_thread(self.controller.get_message)
    #             if message is self._sentinel:
    #                 logger.debug("Controller thread returned")
    #                 # Notify resolver sentinel has been handled.
    #                 #self.resolver.task_done()
    #                 break
    #             logger.debug(f"Controller message: {message}")
    #             self.send_message_to_streams(message)
    #     finally:
    #         logger.debug("End controller messaging.")
    #         self.stop()

    def streams_stopped(self, streams):
        for stream in streams:
            if not stream.is_stopped():
                return False
        return True

    def stop(self):
        if not self.is_stopped():
            self.stop_event.set()
        # Unblock messaging thread.
        # FIXME: This shouldn't be putting!
        self.recv_message_queue.put("")
        # Stop all stream processes.
        for stream in self.active_streams.values():
            if not stream.is_stopped():
                stream.stop()
        for stream in self.active_streams.values():
            stream.join()
        if self.controller and not self.controller.is_stopped():
            self.controller.stop()
            self.controller.join()

    def is_stopped(self):
        return self.stop_event.is_set()

    def remove_lost_streams(self):
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
                stream.type(),
                str(stream.channel_count()),
                stream.source_id(),
                stream.hostname(),
            ]
        )
        return key


def add_cli_args(parser):
    group = parser.add_argument_group(title="relay options")
    group.add_argument(
        "--non-local", action="store_true", help="Enable relay of non-local streams."
    )
    group.add_argument(
        "--re-encode-timestamps",
        action="store_true",
        help="Re-encode stream timestamps.",
    )


def main():
    """Start an LSL relay stream."""

    # Use multiprocessing spawn on all platforms.
    mp.set_start_method("spawn")

    parser = argparse.ArgumentParser(
        description="""Create an LSL relay with optional remote control.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    lsl_resolve.add_cli_args(parser, pred_only=True)
    socket_options.add_socket_args(parser, inlet=True, outlet=True)
    add_cli_args(parser)

    parser.add_argument(
        "--output",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Disable relay output.",
    )
    parser.add_argument(
        "--monitor",
        default=False,
        action=argparse.BooleanOptionalAction,
        help="Enable monitoring stream.",
    )
    parser.add_argument(
        "--monitor-interval",
        type=int,
        default=5,
        help="Monitoring interval in seconds.",
    )
    parser.add_argument("--control-name", help="Control stream name.")
    parser.add_argument(
        "--verbose", action="store_true", help="Print extra debugging information."
    )
    args = parser.parse_args()

    # Logging
    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG

    log_queue, log_listener = init_logging(log_level)
    logger.debug("Logging initialised")

    # Add additional predicates.
    pred = "" if args.pred is None else args.pred

    if len(pred) > 0:
        pred = (
            "not(starts-with(name, '_relay_')) and "
            + "not(starts-with(name, '_monitor_')) and "
            + "not(type='control') and "
            + pred
        )
    else:
        pred = (
            "not(starts-with(name, '_relay_')) and "
            + "not(starts-with(name, '_monitor_')) and "
            + "not(type='control')"
        )
    if not args.non_local:
        pred = f"hostname='{platform.node()}' and " + pred
    logger.info(f"Stream matching predicate: {repr(pred)}")

    if args.re_encode_timestamps and (not args.chunk_size == 1):
        logger.info("Setting chunk size to 1 for timestamp re-encoding.")
        args.chunk_size = 1

    resolver = lsl_resolve.StreamResolver(
        pred=pred,
        forget_after=args.forget_after,
        refresh_rate=args.refresh_rate,
        notify_lost=args.notify_lost,
    )

    inlet_options = LslInletOptions(
        args.inlet_max_buffer_size,
        args.inlet_max_chunk_size,
        args.inlet_recover,
        args.inlet_processing_flags,
    )

    outlet_options = LslOutletOptions(
        args.outlet_max_buffer_size,
        args.outlet_max_chunk_size,
    )

    relay = Relay(
        resolver,
        inlet_options=inlet_options,
        outlet_options=outlet_options,
        re_encode_timestamps=args.re_encode_timestamps,
        output=args.output,
        monitor=args.monitor,
        monitor_interval=args.monitor_interval,
        control_name=args.control_name,
        log_queue=log_queue,
    )

    try:
        relay.start()
    except Exception as exc:
        relay.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main")
        relay.stop()
    finally:
        print("finally")
        log_listener.stop()
        print("Main exit")
