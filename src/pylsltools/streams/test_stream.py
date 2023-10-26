"""Test stream class."""

import os
import platform
import time
import threading

from pylsl import StreamOutlet, local_clock
from pylsltools.streams import BaseDataStream


class TestStream (BaseDataStream):

    is_running = False

    def __init__(self, stream_id, channel_count, sample_rate, generators, name,
                 content_type=None, channel_format=None, channel_labels=None,
                 channel_types=None, channel_units=None):
        if name:
            name = f'{name} test stream {stream_id} {" ".join(g for g in generators)}'
        else:
            name = f'Test stream {stream_id} {" ".join(g for g in generators)}'
        # Use hostname to identify source. If stream is stopped and
        # resumed consumers should be able to recover.
        source_id = f'{os.path.basename(__file__)}'

        super().__init__(stream_id, name, channel_count, content_type,
                         channel_format, sample_rate, source_id,
                         channel_labels=channel_labels,
                         channel_types=channel_types,
                         channel_units=channel_units)
        self.generators = generators

    # def start(self, start_time, max_time=None, max_samples=None, chunk_size=None,
    #           max_buffered=None, debug=False):

    def run(self, start_time, max_time=None, max_samples=None, chunk_size=None,
            max_buffered=None, debug=False):
        self.is_running = True
        info = self.make_stream_info()
        print(info.as_xml())
        outlet = StreamOutlet(info, chunk_size, max_buffered)
        sample_count = 0
        logical_time = start_time
        delta = 1 / self.sample_rate
        now = local_clock()
        if now < start_time:
            # Synchronise start time.
            time.sleep(start_time - now)
        while self.is_running:
            elapsed_time = logical_time - start_time
            sample = self.generate_sample(sample_count)
            if debug:
                print(f'{self.name}: {logical_time:.3f} {sample} {elapsed_time:.3f}')
            outlet.push_sample(sample, timestamp=logical_time)
            sample_count = sample_count + 1
            self.check_continue(elapsed_time, sample_count, max_time,
                                max_samples)
            logical_time = logical_time + delta
            time.sleep(max(0, logical_time - local_clock()))
        return f'Completed: {self.name}'

    def check_continue(self, elapsed_time, sample_count, max_time,
                       max_samples):
        if self.is_running:
            if max_time is not None:
                if elapsed_time >= max_time:
                    print(f'{self.name} max time reached.')
                    self.is_running = False
            if max_samples is not None:
                if sample_count >= max_samples:
                    print(f'{self.name} max samples reached.')
                    self.is_running = False

    def generate_sample(self, sample_idx):
        sample = [self.generate_channel_data(sample_idx, channel_idx)
                  for channel_idx in range(self.channel_count)]
        return sample

    def generate_channel_data(self, sample_idx, channel_idx):
        generator = self.generators[channel_idx % len(self.generators)]
        if generator == 'stream-id':
            return self.stream_id
        if generator == 'stream-seq':
            return self.stream_id + channel_idx
        if generator == 'counter':
            return sample_idx
        if generator == 'counter+':
            return (sample_idx * self.channel_count) + channel_idx
        if generator == 'impulse':
            if sample_idx % self.sample_rate == 0:
                return 1
            else:
                return 0
