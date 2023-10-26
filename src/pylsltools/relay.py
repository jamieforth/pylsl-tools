"""Relay a local stream with remote control."""

import argparse
import platform
from threading import Thread
from time import sleep

from pylsl import ContinuousResolver

from pylsltools.streams.relay_stream import RelayStream


class Relay:
    """Relay matching streams."""

    is_running = False
    active_streams = {}

    def __init__(self, pred, control_name):
        self.pred = pred
        self.control_name = control_name

    def start(self, chunk_size, max_buffered, keep_orig_timestamps, monitor,
              debug):
        resolver = ContinuousResolver(pred=self.pred)

        self.thread = Thread(target=self.run, args=[resolver, chunk_size,
                                                    max_buffered,
                                                    keep_orig_timestamps,
                                                    monitor,
                                                    debug])
        self.thread.start()
        # Block main thread until resolver thread returns.
        self.thread.join()

    def run(self, resolver, chunk_size, max_buffered, keep_orig_timestamps,
            monitor, debug):
        self.is_running = True
        while self.is_running:
            # FIXME: Improve this? Continuous resolver always returns a
            # new StreamInfo object so we need to continually regenerate
            # the key to check if we've seen it before.
            streams = resolver.results()
            for stream in streams:
                stream_key = self.make_stream_key(stream)
                if stream_key not in self.active_streams.keys():
                    self.active_streams[stream_key] = RelayStream(
                        stream).start(chunk_size=chunk_size,
                                      max_buffered=max_buffered,
                                      keep_orig_timestamps=keep_orig_timestamps,
                                      monitor=monitor,
                                      debug=debug)
                    print('New stream added.')
            self.cleanup()
            sleep(1)

    def stop(self):
        """Stop relay thread and all relay stream threads."""
        print('Stopping all relay streams.')
        for stream in self.active_streams.values():
            stream.stop()
        self.is_running = False

    def cleanup(self):
        for stream_key in list(self.active_streams):
            stream = self.active_streams[stream_key]
            if not stream.is_running:
                print(f'Removing: {stream_key}')
                del self.active_streams[stream_key]
        # print(f'Total active streams: {len(self.active_streams)}')

    def make_stream_key(self, stream):
        key = ':'.join([
            stream.name(),
            stream.source_id(),
            stream.hostname(),
            str(stream.channel_count())])
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
        '--monitor',
        action='store_true',
        help='Enable monitoring/disable relay.')
    parser.add_argument(
        '--keep-orig-timestamps',
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
        if not args.monitor:
            pred = ("not(starts-with(name, '_relay_')) and " +
                    "not(starts-with(name, '_monitor_')) and ") + pred
        else:
            pred = "starts-with(name, '_monitor_') and " + pred
    else:
        if not args.monitor:
            pred = ("not(starts-with(name, '_relay_')) and " +
                    "not(starts-with(name, '_monitor_'))")
        else:
            pred = "starts-with(name, '_monitor_')"
    if not args.non_local:
        pred = f"hostname='{platform.node()}' and " + pred
    print(f'Stream matching predicate: {repr(pred)}')

    if not args.keep_orig_timestamps:
        if not args.chunk_size == 1:
            print('Setting chunk size to 1 for timestamp re-encoding.')
            args.chunk_size = 1

    relay = Relay(pred, args.control_name)

    # Block here unless keyboard interrupt.
    try:
        relay.start(chunk_size=args.chunk_size,
                    max_buffered=args.max_buffered,
                    keep_orig_timestamps=args.keep_orig_timestamps,
                    monitor=args.monitor,
                    debug=args.debug)
    except Exception as exc:
        relay.stop()
        raise exc
    except KeyboardInterrupt:
        relay.stop()
        print('Main thread ended.')
