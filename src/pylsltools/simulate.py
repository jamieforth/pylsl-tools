"""Test programme to simulate LSL streams."""

import argparse
import asyncio
import multiprocessing as mp
import threading

from pylsl import local_clock

from pylsltools import ControlStates
from pylsltools.streams import ControlReceiver, TestStream


class Simulate:
    """Generate test synthetic data streams."""

    controller = None
    control_states = ControlStates

    def __init__(self, num_streams, functions, name, content_type,
                 channel_count, nominal_srate, channel_format, source_id,
                 channel_labels=None, channel_types=None, channel_units=None,
                 control_name=None, debug=False):
        """Initialise simulation test.

        Optionally can receive messages from an input LSL control
        stream.
        """
        # Event to terminate the main process.
        self.stop_event = threading.Event()

        # Set class attributes.
        self.num_streams = num_streams
        self.functions = functions
        self.name = name
        self.content_type = content_type
        self.channel_count = channel_count
        self.nominal_srate = nominal_srate
        self.channel_format = channel_format
        self.source_id = source_id
        self.channel_labels = channel_labels
        self.channel_types = channel_types
        self.channel_units = channel_units
        # Create barrier for sub-process synchronisation.
        self.barrier = mp.Barrier(self.num_streams)
        # For receiving messages from sub-processes.
        self.recv_message_queue = mp.SimpleQueue()
        # For receiving messages from a controller thread.
        if control_name:
            self.controller = ControlReceiver(control_name,
                                              debug=debug)
        self.debug = debug

    def start(self, sync, latency, max_time=None, max_samples=None,
              chunk_size=None, max_buffered=None):
        """Start test streams with a synchronised start time."""

        # Start remote control thread if initialised.
        if self.controller:
            self.controller.start()

        # Create sub-processes.
        streams = [TestStream(stream_idx, self.functions, self.name,
                              self.content_type, self.channel_count,
                              self.nominal_srate, self.channel_format,
                              source_id=self.source_id,
                              channel_labels=self.channel_labels,
                              channel_types=self.channel_types,
                              channel_units=self.channel_units,
                              latency=latency,
                              max_time=max_time,
                              max_samples=max_samples,
                              chunk_size=chunk_size,
                              max_buffered=max_buffered,
                              barrier=self.barrier,
                              # Each sub-process has a unique
                              # recv_message queue.
                              recv_message_queue=mp.SimpleQueue(),
                              # Each sub-process shares the same queue
                              # for sending message to the main process.
                              send_message_queue=self.recv_message_queue,
                              debug=self.debug)
                   for stream_idx in range(self.num_streams)]

        self.streams = streams

        for stream in self.streams:
            # Start sub-processes.
            stream.start()

        # Initialise start time.
        if not self.controller:
            if sync:
                # Get start time in the main thread to synchronise streams.
                start_time = local_clock()
            else:
                start_time = None
            self.send_message_to_streams({'state': self.control_states.START,
                                          'time_stamp': start_time})

        # Use asyncio to handle asynchronous messages in the main thread.
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.handle_messages())

        for stream in self.streams:
            # Block until all child processes return.
            stream.join()

        if self.controller:
            self.controller.join()

    async def handle_messages(self):
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.recv_from_streams())
                if self.controller:
                    tg.create_task(self.recv_from_controller())
        finally:
            print('End handle messages.')

    def send_message_to_streams(self, message):
        for stream in self.streams:
            if stream.is_alive():
                stream.recv_message_queue.put(message)

    async def recv_from_streams(self):
        """Coroutine to handle messages from sub-processes."""
        try:
            while not self.streams_stopped(self.streams) or (
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
        # # Stop all stream processes.
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
    import multiprocessing
    multiprocessing.set_start_method('spawn')

    parser = argparse.ArgumentParser(description="""Create test LSL data
    streams using synthetic data.""")
    parser.add_argument(
        '-n',
        '--num-streams',
        default=1,
        type=int,
        help='Number of streams to simulate.')
    parser.add_argument(
        '-c',
        '--num-channels',
        default=30,
        type=int,
        help='Number of channels per stream.')
    parser.add_argument(
        '-s',
        '--sample-rate',
        default=500,
        type=int,
        help='Synthetic data stream sample rate.')
    parser.add_argument(
        '--fn',
        nargs='+',
        default=['counter'],
        choices=['stream-id', 'stream-seq', 'counter', 'counter+', 'impulse',
                 'sine'],
        help="""Function(s) to use to simulate channel data. If multiple
        function names are provided they will be recycled to match the
        number of channels.""")
    parser.add_argument(
        '--name',
        help='Additional identifier to append to stream name.')
    parser.add_argument(
        '--content-type',
        default='data',
        help='Content type: e.g. `eeg`.')
    parser.add_argument(
        '--channel-format',
        default='float32',
        choices=['float32', 'double64', 'string', 'int64', 'int32', 'int16',
                 'int8'],
        help='Channel datatype.')
    parser.add_argument(
        '--source-id',
        help='Unique identifier for stream source.')
    parser.add_argument(
        '-t',
        '--channel-type',
        default='misc',
        help='Synthetic data channel type.')
    parser.add_argument(
        '--channel-unit',
        help='Synthetic data channel unit.')
    parser.add_argument(
        '--max-time',
        type=float,
        default=None,
        help='Maximum run-time for test streams.')
    parser.add_argument(
        '--max-samples',
        type=int,
        default=None,
        help="""Maximum number of samples to generate by each test
        stream.""")
    parser.add_argument(
        '--chunk-size',
        type=int,
        default=0,
        help="""Desired outlet chunk size in samples. Inlets can
        override this.""")
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
        '--sync',
        default=True,
        action=argparse.BooleanOptionalAction,
        help='Synchronise timestamps across all streams.')
    parser.add_argument(
        '--latency',
        type=float,
        default=0.2,
        help='Scheduling latency in seconds.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print extra debugging information.')
    args = parser.parse_args()
    simulate = Simulate(args.num_streams, args.fn, args.name,
                        args.content_type, args.num_channels, args.sample_rate,
                        args.channel_format, args.source_id,
                        channel_types=args.channel_type,
                        channel_units=args.channel_unit,
                        control_name=args.control_name,
                        debug=args.debug)
    try:
        simulate.start(args.sync,
                       args.latency,
                       max_time=args.max_time,
                       max_samples=args.max_samples,
                       chunk_size=args.chunk_size,
                       max_buffered=args.max_buffered)
    except Exception as exc:
        # Stop all streams if one raises an error.
        simulate.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        simulate.stop()
    finally:
        print('Main exit.')
