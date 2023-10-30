"""Test stream class."""

import os
import time

from pylsl import StreamOutlet, local_clock
from pylsltools.streams import DataStream


class TestStream (DataStream):

    def __init__(self, stream_idx, generators, name, content_type,
                 channel_count, nominal_srate, channel_format, *,
                 source_id=None, channel_labels=None, channel_types=None,
                 channel_units=None, start_time=None, latency=None,
                 max_time=None, max_samples=None, chunk_size=None,
                 max_buffered=None, debug=False, **kwargs):
        print('TestStream', stream_idx, generators, name, content_type,
              channel_count, nominal_srate, channel_format, source_id,
              channel_labels, channel_types, channel_units, start_time,
              latency, max_time, max_samples, chunk_size, max_buffered, debug,
              kwargs)
        self.stream_idx = stream_idx
        self.channel_count = channel_count
        if name:
            name = f'{name} test stream {stream_idx} {" ".join(g for g in generators)}'
        else:
            name = f'Test stream {stream_idx} {" ".join(g for g in generators)}'
        # Use script name and PID to identify source. If stream is
        # interrupted due to network outage consumers should be able to
        # recover. However, if the script is restarted the PID will be
        # different an appear as a new stream.
        if source_id is None:
            source_id = f'{os.path.basename(__file__)}:{os.getpid()}'

        super().__init__(name, content_type, channel_count,
                         nominal_srate, channel_format,
                         source_id=source_id,
                         channel_labels=channel_labels,
                         channel_types=channel_types,
                         channel_units=channel_units, **kwargs)

        # Initialise local attributes.
        self.generators = generators
        self.start_time = start_time
        self.latency = latency
        self.max_time = max_time
        self.max_samples = max_samples
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.debug = debug
        self.outlet = StreamOutlet(self.info, self.chunk_size,
                                   self.max_buffered)

    def run(self):
        if self.start_time is None:
            self.start_time = local_clock()
        sample_count = 0
        logical_time = self.start_time
        delta = 1 / self.info.nominal_srate()
        try:
            while not self.stop.is_set():
                now = local_clock()
                elapsed_time = logical_time - self.start_time
                sample = self.generate_sample(sample_count)
                if self.debug:
                    print(f'{self.name}: {logical_time:.3f} {now} {sample} {elapsed_time:.3f}',
                          flush=True)
                self.outlet.push_sample(sample, timestamp=logical_time +
                                        self.latency)
                sample_count = sample_count + 1
                self.check_continue(elapsed_time, sample_count, self.max_time,
                                    self.max_samples)
                logical_time = logical_time + delta
                # Avoid drift.
                time.sleep(max(0, logical_time - local_clock()))
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}')
            self.stop.set()
        print(f'Ended: {self.name}.')

    def check_continue(self, elapsed_time, sample_count, max_time,
                       max_samples):
        if not self.stop.is_set():
            if max_time is not None:
                if elapsed_time >= max_time:
                    print(f'{self.name} max time reached.')
                    self.stop.set()
            if max_samples is not None:
                if sample_count >= max_samples:
                    print(f'{self.name} max samples reached.')
                    self.stop.set()

    def generate_sample(self, sample_idx):
        sample = [self.generate_channel_data(sample_idx, channel_idx)
                  for channel_idx in range(self.channel_count)]
        return sample

    def generate_channel_data(self, sample_idx, channel_idx):
        generator = self.generators[channel_idx % len(self.generators)]
        if generator == 'stream-id':
            return self.stream_idx
        if generator == 'stream-seq':
            return self.stream_idx + channel_idx
        if generator == 'counter':
            return sample_idx
        if generator == 'counter+':
            return (sample_idx * self.channel_count) + channel_idx
        if generator == 'impulse':
            if sample_idx % self.sample_rate == 0:
                return 1
            else:
                return 0
