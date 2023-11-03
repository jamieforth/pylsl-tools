"""Test programme to simulate LSL streams."""

import argparse
from multiprocessing import Barrier

from pylsl import local_clock

from pylsltools.streams import ControlReceiver, TestStream


class Simulate:
    """Generate test synthetic data streams."""

    controller = None

    def __init__(self, num_streams, functions, name, content_type,
                 channel_count, nominal_srate, channel_format, source_id,
                 channel_labels=None, channel_types=None, channel_units=None,
                 control_name=None):
        """Initialise simulation test.

        Optionally set up an input control stream.
        """
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
        if control_name:
            self.controller = ControlReceiver(control_name)

    def start(self, sync, latency, max_time=None, max_samples=None,
              chunk_size=None, max_buffered=None, debug=None):
        """Start test streams with a synchronised start time."""
        start_time = None
        if self.controller:
            self.controller.start()
        elif sync:
            # Get start time in the main thread to synchronise streams.
            start_time = local_clock()
        # Create barrier for sub-process synchronisation.
        self.barrier = Barrier(self.num_streams)
        streams = [TestStream(stream_idx, self.functions, self.name,
                              self.content_type, self.channel_count,
                              self.nominal_srate, self.channel_format,
                              source_id=self.source_id,
                              channel_labels=self.channel_labels,
                              channel_types=self.channel_types,
                              channel_units=self.channel_units,
                              start_time=start_time,
                              latency=latency,
                              max_time=max_time,
                              max_samples=max_samples,
                              chunk_size=chunk_size,
                              max_buffered=max_buffered,
                              barrier=self.barrier,
                              controller=self.controller,
                              debug=debug)
                   for stream_idx in range(self.num_streams)]
        print('Streams created.')
        self.streams = streams

        for stream in self.streams:
            stream.start()
        print('Streams started.')

        if self.controller:
            # Block until controller thread returns.
            self.controller.join()
        for stream in self.streams:
            # Block until all child processes return.
            stream.join()

    def stop(self):
        """Stop all stream processes."""
        for stream in self.streams:
            if not stream.is_stopped():
                print(f'Stopping: {stream.name}.')
                stream.stop()
        for stream in self.streams:
            # Block until all child processes return.
            stream.join()


def main():
    """Generate synthetic LSL streams."""
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
                        control_name=args.control_name)
    try:
        simulate.start(args.sync,
                       args.latency,
                       max_time=args.max_time,
                       max_samples=args.max_samples,
                       chunk_size=args.chunk_size,
                       max_buffered=args.max_buffered,
                       debug=args.debug)
    except Exception as exc:
        # Stop all streams if one raises an error.
        simulate.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        simulate.stop()
    print('Main exit.')
