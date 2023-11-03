"""Script to monitor data streams over LSL."""

import os
import argparse
from threading import Event, Thread
from time import sleep

from pylsl import ContinuousResolver
from pylsltools.streams import MonitorReceiver


class Monitor:
    """Monitor matching streams."""

    def __init__(self, pred):
        self.pred = pred
        self.stop_event = Event()
        self.active_streams = {}

    def start(self, debug=False):
        resolver = ContinuousResolver(pred=self.pred, forget_after=1)

        self.thread = Thread(target=self.run, args=[resolver, debug])
        self.thread.start()
        # Block main thread until resolver thread returns.
        self.thread.join()

    def run(self, resolver, debug):
        while not self.is_stopped():
            # FIXME: Improve this? Continuous resolver always returns a
            # new StreamInfo object so we need to continually regenerate
            # the key to check if we've seen it before.
            streams = resolver.results()
            for stream in streams:
                stream_key = self.make_stream_key(stream)
                if stream_key not in self.active_streams.keys():
                    new_stream = MonitorReceiver(stream, debug)
                    self.active_streams[stream_key] = new_stream
                    new_stream.start()
                    print(f'New stream added {new_stream.info.name()}.')
            self.cleanup()
            sleep(1)

    def stop(self):
        """Stop monitor thread and all monitor stream threads."""
        print('Stopping all monitor streams.')
        self.stop_event.set()
        for stream in self.active_streams.values():
            stream.stop()
        for stream in self.active_streams.values():
            stream.join()

    def is_stopped(self):
        return self.stop_event.is_set()

    def cleanup(self):
        for stream_key in list(self.active_streams):
            stream = self.active_streams[stream_key]
            if stream.is_stopped():
                print(f'Removing: {stream.name}')
                del self.active_streams[stream_key]
        #print(f'Total active streams: {len(self.active_streams)}')

    def make_stream_key(self, stream):
        key = ':'.join([
            stream.name(),
            stream.source_id(),
            stream.hostname(),
            str(stream.channel_count())])
        return key

def main():
    """Monitor marker streams."""
    parser = argparse.ArgumentParser(description="""Create an LSL
    monitor.""")
    parser.add_argument(
        '-p',
        '--pred',
        default='',
        help='Predicate string to resolve monitor streams.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print extra debugging information.')

    args = parser.parse_args()

    # Add additional predicates.
    pred = args.pred

    if len(pred) > 0:
        pred = "starts-with(name, '_monitor_') and " + pred
    else:
        pred = "starts-with(name, '_monitor_')"

    monitor = Monitor(pred)

    # Start continuous resolver and block unless keyboard interrupt.
    try:
        monitor.start(debug=args.debug)
    except Exception as exc:
        monitor.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        monitor.stop()
    print('Main exit.')
