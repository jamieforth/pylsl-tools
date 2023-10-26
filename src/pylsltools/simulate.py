"""Test programme to simulate LSL streams."""

import argparse
import concurrent.futures

from pylsl import local_clock

from pylsltools.streams.test_stream import TestStream
from pylsltools.streams.control_stream import ControlClient


class Simulate:
    """Generate test synthetic data streams."""

    controller = None
    latency = 0.2

    def __init__(self, num_streams, channel_count, sample_rate, generators,
                 name, content_type, channel_format, channel_type,
                 control_name):
        """Return a list of TestStream objects.

        Optionally set up an input control stream.
        """
        self.num_streams = num_streams

        streams = [TestStream(stream_idx, channel_count, sample_rate,
                              generators, name, content_type=content_type,
                              channel_format=channel_format,
                              channel_types=channel_type) for stream_idx in
                   range(num_streams)]
        print('Streams created')
        self.streams = streams

        if control_name:
            self.controller = ControlClient(control_name, self)

    def start(self, start_time=None, max_time=None, max_samples=None,
              chunk_size=None, max_buffered=None, debug=None):
        """Start test streams with a synchronised start time."""
        if start_time is None:
            # Get start time in the main thread to synchronise streams.
            start_time = local_clock() + self.latency

        with concurrent.futures.ThreadPoolExecutor(
                len(self.streams)) as executor:
            # Run each stream in a separate thread.
            futures = [executor.submit(stream.run,
                                       start_time=start_time,
                                       max_time=max_time,
                                       max_samples=max_samples,
                                       chunk_size=chunk_size,
                                       max_buffered=max_buffered,
                                       debug=debug)
                       for stream in self.streams]
            print('Streams started')
            # Wait until threads return. Stop all threads if one raises
            # and exception.
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    print(f'result: {result}')
                except Exception as exc:
                    self.stop()
                    raise exc

    def stop(self):
        """Stop all stream threads."""
        print('Stopping all streams 2.')
        for stream in self.streams:
            stream.is_running = False

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
        '-g',
        '--generators',
        nargs='+',
        default=['counter'],
        choices=['stream-id', 'stream-seq', 'counter', 'counter+', 'impulse'],
        help="""Generator to use to simulate channel data. If multiple
        generators are provided they will be recycled to match the
        number of channels.""")
    parser.add_argument(
        '--name',
        help='Unique identifier.')
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
        '-t',
        '--channel-type',
        default='misc',
        help='Synthetic data channel type.')
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
        '--debug',
        action=argparse.BooleanOptionalAction,
        help='Print extra debugging information.')
    args = parser.parse_args()
    debug = args.debug
    simulate = Simulate(args.num_streams, args.num_channels, args.sample_rate,
                        args.generators, args.name,
                        content_type=args.content_type,
                        channel_format=args.channel_format,
                        channel_type=args.channel_type,
                        control_name=args.control_name)
    try:
        if simulate.controller:
            # Block here until controller quits or keyboard interrupt.
            simulate.controller.start()
        else:
            # Start streams now and block until all stream threads
            # return or keyboard interrupt.
            print('before start')
            simulate.start(max_time=args.max_time,
                           max_samples=args.max_samples,
                           chunk_size=args.chunk_size,
                           max_buffered=args.max_buffered, debug=debug)
            print('after start')
    except Exception as exc:
        simulate.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping all streams.')
        simulate.stop()
        print('All streams closed.')
