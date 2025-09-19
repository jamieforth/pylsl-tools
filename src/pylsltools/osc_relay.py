"""Relay streams to Open Sound Control."""

import argparse
import asyncio
import logging
import multiprocessing as mp
import platform
import threading
from logging.handlers import QueueHandler

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer

import pylsltools.osc.sc as sc
import pylsltools.relay as lsl_relay
import pylsltools.resolve as lsl_resolve
from pylsltools.logging import init_logging
from pylsltools.streams import OscRelayStream, LslInletParams, StreamInfoData

logger = logging.getLogger(__name__)


class OscRelay:
    """Relay matching streams to OSC."""

    def __init__(
        self,
        resolver,
        inlet_params,
        osc_device,
        re_encode_timestamps,
        max_streams,
    ):
        # Set class attributes.
        self.resolver = resolver
        self.inlet_params = inlet_params
        self.osc_device = osc_device
        self.max_streams = max_streams

        self.stop_event = threading.Event()
        self.active_streams = {}

        # For receiving messages from sub-processes.
        # self.recv_message_queue = mp.Queue()

    def start(self):
        # Use asyncio to handle asynchronous messages in the main thread.
        logger.debug("Start handle messages")
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.handle_messages())
        logger.debug("End handle messages")

    # def createRelayStream(self, info):
    #     # Check max number of streams.
    #     if len(self.active_streams) >= self.max_streams:
    #         logger.info(f"Maximum number of streams {self.max_streams}")
    #         return None

    #     if info.source_id in self.active_streams:
    #         logger.info(f"Stream with source_id already exists: {info.source_id}")
    #         return None

    #     new_stream = OscRelayStream(
    #         len(self.active_stream),
    #         info,
    #         self.sc_args,
    #         self.stream_args,
    #         # Each sub-process has a unique recv_message queue.
    #         recv_message_queue=mp.Queue(),
    #         # Each sub-process shares the same queue for sending
    #         # message to the main process.
    #         send_message_queue=self.recv_message_queue,
    #     )
    #     self.active_streams[stream_key] = new_stream
    #     new_stream.start()
    #     print(f'New stream added: {stream.name()}.')
    #     if self.debug:
    #         print(stream.as_xml())
    # self.remove_lost_streams()
    # self.stop_event.wait(1)

    async def handle_messages(self):
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.resolver.task())
                tg.create_task(self.stream_manager_task())
                # tg.create_task(self.recv_osc())
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
                if message is None:
                    logger.debug("Resolver thread returned")
                    # Notify resolver sentinel has been handled.
                    self.resolver.task_done()
                    break
                match message[0]:
                    case "NEW":
                        logger.debug((f"New stream: {message[1].name}"))
                        # self.create_relay_stream(message[1])
                    case "LOST":
                        logger.debug((f"Lost stream: {message[1].name}"))
                    case _:
                        logger.debug(f"Unknown state: {message}")
                # Notify resolver message has been handled.
                self.resolver.task_done()
        finally:
            logger.debug("End stream manager task")

    def send_message_to_streams(self, message):
        for stream in self.active_streams.values():
            if stream.is_alive():
                stream.recv_message_queue.put(message)

    def find_stream(self, stream_id):
        for stream in self.active_streams.values():
            if stream.id == stream_id:
                return stream

    def default_handler(self, address, *args):
        print("DEFAULT", address, args)

    def lsl_init(
        self, address, stream_id, bus_index, bufnum, eeg_group, eeg_synth, eeg_bus
    ):
        if self.debug:
            print(
                "SET_BUS_ID",
                address,
                stream_id,
                bus_index,
                bufnum,
                eeg_group,
                eeg_synth,
                eeg_bus,
            )
        stream = self.find_stream(stream_id)
        if stream:
            stream.recv_message_queue.put(
                [address, bus_index, bufnum, eeg_group, eeg_synth, eeg_bus]
            )
        else:
            print("stream not found")

    async def recv_osc(self):
        osc_dispatcher = Dispatcher()
        # FIXME: Huh?
        osc_dispatcher.set_default_handler(self.default_handler)
        osc_dispatcher.map("/lsl/init", self.lsl_init)
        self.osc_server = AsyncIOOSCUDPServer(
            ("127.0.0.1", 47465), osc_dispatcher, asyncio.get_event_loop()
        )
        self.transport, self.protocol = await self.osc_server.create_serve_endpoint()

    # async def recv_from_streams(self):
    #     """Coroutine to handle messages from sub-processes."""
    #     try:
    #         while not self.is_stopped() or (not self.recv_message_queue.empty()):
    #             # Block here until message received.
    #             message = await asyncio.to_thread(self.recv_message_queue.get)
    #             if self.debug and message:
    #                 print(f"{__class__} sub-process message: {message}")
    #     finally:
    #         if self.debug:
    #             print("End stream messaging")
    #         self.stop()

    def streams_stopped(self, streams):
        for stream in streams:
            if not stream.is_stopped():
                return False
        return True

    def stop(self):
        print("stop")
        if not self.is_stopped():
            self.stop_event.set()
        # Unblock messaging thread.
        # self.recv_message_queue.put("")
        # Stop OSC server.
        # self.transport.close()
        # Stop all stream processes.
        # for stream in self.active_streams.values():
        #     if not stream.is_stopped():
        #         stream.stop()
        # for stream in self.active_streams.values():
        #     stream.join()

    def is_stopped(self):
        return self.stop_event.is_set()


def main():
    """Start an LSL to SC relay."""
    parser = argparse.ArgumentParser(
        description="""Relay LSL streams to Open Sound Control.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    lsl_resolve.add_cli_args(parser, pred_only=True)
    sc.add_cli_args(parser)
    lsl_relay.add_cli_args(parser, inlet=True, outlet=False)

    parser.add_argument(
        "--max-streams",
        type=int,
        default=12,
        help="""Maximum number of LSL streams to relay.""",
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
    logger.debug(f"Stream matching predicate: {repr(pred)}")

    resolver = lsl_resolve.StreamResolver(
        pred=pred,
        forget_after=args.forget_after,
        refresh_rate=args.refresh_rate,
        notify_lost=args.notify_lost,
    )

    if args.re_encode_timestamps and (not args.inlet_max_chunk_size == 1):
        logger.info("Setting chunk size to 1 for timestamp re-encoding")
        args.inlet_max_chunk_size = 1

    inletParams = LslInletParams(
        args.inlet_max_buffer_size,
        args.inlet_max_chunk_size,
        args.inlet_recover,
        args.inlet_processing_flags,
    )

    osc_device = sc.SuperCollider(
        args.sclang_ip,
        args.sclang_port,
        args.scsynth_ip,
        args.scsynth_port,
        args.osc_latency,
    )

    relay = OscRelay(
        resolver,
        inletParams,
        osc_device,
        args.re_encode_timestamps,
        args.max_streams,
    )

    try:
        relay.start()
    except Exception as exc:
        relay.stop()
        raise exc
    except KeyboardInterrupt:
        logging.debug("Stopping main")
        relay.stop()
    finally:
        print("Main exit")
