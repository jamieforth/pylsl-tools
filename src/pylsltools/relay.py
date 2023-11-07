"""Relay a local stream with remote control."""

import argparse
import asyncio
import multiprocessing as mp
import platform
from threading import Event, Thread

from pylsl import ContinuousResolver

from pylsltools import ControlStates
from pylsltools.streams import ControlReceiver, RelayStream


class Relay:
    """Relay matching streams."""

    controller = None
    control_states = ControlStates

    def __init__(self, pred, control_name, debug=False):
        # Event to terminate the main process.
        self.stop_event = Event()

        # Set class attributes.
        self.pred = pred
        self.control_name = control_name
        self.stop_event = Event()
        self.active_streams = {}
        # For receiving messages from sub-processes.
        self.recv_message_queue = mp.SimpleQueue()
        # For receiving messages from a controller thread.
        if control_name:
            self.controller = ControlReceiver(control_name,
                                              debug=debug)
        self.debug = debug

    def start(self, chunk_size, max_buffered, re_encode_timestamps, output,
              monitor, monitor_interval):

        # Start remote control thread if initialised.
        if self.controller:
            self.controller.start()

        # TODO: Wrap this in a class or co-routine.
        self.thread = Thread(target=self.run, args=[chunk_size, max_buffered,
                                                    re_encode_timestamps,
                                                    output, monitor,
                                                    monitor_interval])
        self.thread.start()

        # Use asyncio to handle asynchronous messages in the main thread.
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.handle_messages())

        if self.controller:
            # Block until controller returns.
            self.controller.join()

        # Block until resolver thread returns.
        self.thread.join()


    def run(self, chunk_size, max_buffered, re_encode_timestamps, output,
            monitor, monitor_interval):

        resolver = ContinuousResolver(pred=self.pred, forget_after=1)

        while not self.is_stopped():
            # FIXME: Improve this? Continuous resolver always returns a
            # new StreamInfo object so we need to continually regenerate
            # the key to check if we've seen it before.
            streams = resolver.results()
            for stream in streams:
                stream_key = self.make_stream_key(stream)
                if stream_key not in self.active_streams.keys():
                    new_stream = RelayStream(
                        stream.name(),
                        stream.type(),
                        stream.channel_count(),
                        stream.nominal_srate(),
                        stream.channel_format(),
                        stream.source_id(),
                        stream.hostname(),
                        re_encode_timestamps=re_encode_timestamps,
                        output=output,
                        monitor=monitor,
                        monitor_interval=monitor_interval,
                        chunk_size=chunk_size,
                        max_buffered=max_buffered,
                        # Each sub-process has a unique recv_message queue.
                        recv_message_queue=mp.SimpleQueue(),
                        # Each sub-process shares the same queue for sending
                        # message to the main process.
                        send_message_queue=self.recv_message_queue,
                        debug=self.debug)
                    self.active_streams[stream_key] = new_stream
                    new_stream.start()
                    print(f'New stream added: {stream.name()}.')
            self.remove_lost_streams()
            self.stop_event.wait(1)

    async def handle_messages(self):
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.recv_from_streams())
                if self.controller:
                    tg.create_task(self.recv_from_controller())
        finally:
            print('End handle messages.')

    def send_message_to_streams(self, message):
        for stream in self.active_streams.values():
            if stream.is_alive():
                stream.recv_message_queue.put(message)

    async def recv_from_streams(self):
        """Coroutine to handle messages from sub-processes."""
        try:
            while not self.is_stopped() or (
                    not self.recv_message_queue.empty()):
                # Block here until message received.
                message = await asyncio.to_thread(self.recv_message_queue.get)
                if self.debug and message:
                    print(f'{__class__} sub-process message: {message}')
        finally:
            if self.debug:
                print('End stream messaging.')
            self.stop()

    async def recv_from_controller(self):
        """Coroutine to handle controller messages."""
        try:
            while not self.controller.is_stopped() or (
                    not self.controller.send_message_queue.empty()):
                # Loop here waiting for messages.
                # Blocking.
                message = await asyncio.to_thread(self.controller.get_message)
                if self.debug and message:
                    print(f'{self.__class__} controller message: {message}')
                if message:
                    self.send_message_to_streams(message)
        finally:
            if self.debug:
                print('End controller messaging.')
            self.stop()

    def streams_stopped(self, streams):
        for stream in streams:
            if not stream.is_stopped():
                return False
        return True

    def stop(self):
        if not self.is_stopped():
            self.stop_event.set()
        # Unblock messaging thread.
        self.recv_message_queue.put('')
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
                print(f'Removing: {stream.name}')
                del self.active_streams[stream_key]
        #print(f'Total active streams: {len(self.active_streams)}')

    def make_stream_key(self, stream):
        key = ':'.join([
            stream.name(),
            stream.type(),
            str(stream.channel_count()),
            stream.source_id(),
            stream.hostname()])
        return key

def main():
    """Start an LSL relay stream."""
    parser = argparse.ArgumentParser(description="""Create an LSL relay
    with optional remote control.""")
    parser.add_argument(
        '-p',
        '--pred',
        default='',
        help='Predicate string to resolve streams.')
    parser.add_argument(
        '--non-local',
        action='store_true',
        help='Enable relay of non-local streams.')
    parser.add_argument(
        '--output',
        default=True,
        action=argparse.BooleanOptionalAction,
        help='Disable relay output.')
    parser.add_argument(
        '--monitor',
        default=True,
        action=argparse.BooleanOptionalAction,
        help='Enable monitoring stream.')
    parser.add_argument(
        '--monitor-interval',
        type=int,
        default=5,
        help='Monitoring interval in seconds.')
    parser.add_argument(
        '--re-encode-timestamps',
        action='store_true',
        help='Do not re-encode stream timestamps.')
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=1,
        help="""Desired chunk size in samples. Consumers can override
        this.""")
    parser.add_argument(
        '--max-buffered',
        type=int,
        default=360,
        help="""Maximum amount of data to buffer - in seconds if there is
        a nominal sampling rate, otherwise x100 in samples.""")
    parser.add_argument(
        '--control-name',
        help='Control stream name.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print extra debugging information.')
    args = parser.parse_args()

    # Add additional predicates.
    pred = args.pred

    if len(pred) > 0:
        pred = ("not(starts-with(name, '_relay_')) and " +
                "not(starts-with(name, '_monitor_')) and " +
                "not(type='control')) and " +
                "not(type='Markers')) and ") + pred
    else:
        pred = ("not(starts-with(name, '_relay_')) and " +
                "not(starts-with(name, '_monitor_')) and " +
                "not(type='control') and " +
                "not(type='Markers')")
    if not args.non_local:
        pred = f"hostname='{platform.node()}' and " + pred
    print(f'Stream matching predicate: {repr(pred)}')

    if args.re_encode_timestamps and (
            not args.chunk_size == 1):
        print('Setting chunk size to 1 for timestamp re-encoding.')
        args.chunk_size = 1

    relay = Relay(pred, control_name=args.control_name, debug=args.debug)

    try:
        relay.start(args.chunk_size,
                    args.max_buffered,
                    args.re_encode_timestamps,
                    args.output,
                    args.monitor,
                    args.monitor_interval)
    except Exception as exc:
        relay.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        relay.stop()
    finally:
        print('Main exit.')
