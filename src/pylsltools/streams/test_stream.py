"""Test stream class."""

import os
import time
import textwrap

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

    def run(self):
        if self.start_time is None:
            self.start_time = local_clock()
        sample_count = 0
        logical_time = self.start_time + (self.latency)
        delta = 1 / self.info.nominal_srate()
        self.outlet = StreamOutlet(self.info, self.chunk_size,
                                   self.max_buffered)
        print(self.start_time, local_clock())
        time.sleep(self.latency / 2)
        try:
            while not self.is_stopped():
                now = local_clock()
                elapsed_time = logical_time - self.start_time
                sample = self.generate_sample(sample_count)
                self.outlet.push_sample(sample, timestamp=logical_time)
                if self.debug:
                    if self.info.nominal_srate() <= 5:
                        self.print(self.name, now, logical_time, elapsed_time,
                                   sample)
                    else:
                        if (sample_count % self.info.nominal_srate()) == 0:
                            self.print(self.name, now, logical_time,
                                       elapsed_time, sample)
                sample_count = sample_count + 1
                self.check_continue(elapsed_time, sample_count, self.max_time,
                                    self.max_samples)
                logical_time = logical_time + delta
                # Avoid drift.
                delay = logical_time - local_clock()
                if delay > 0:
                    time.sleep(delay)
                else:
                    print(f'LATE: {self.name} {delay}. Increase latency!')
        except Exception as exc:
            self.stop()
            raise exc
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}')
            self.stop()
        print(f'Ended: {self.name}.')

    def check_continue(self, elapsed_time, sample_count, max_time,
                       max_samples):
        if not self.is_stopped():
            if max_time is not None:
                if elapsed_time >= max_time:
                    print(f'{self.name} max time reached.')
                    self.stop()
            if max_samples is not None:
                if sample_count >= max_samples:
                    print(f'{self.name} max samples reached.')
                    self.stop()

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

    def print(self, name, now, timestamp, elapsed_time, data):
        print(textwrap.fill(textwrap.dedent(f'''
        {name}:
        now: {now:.6f},
        timestamp: {timestamp:.6f},
        elapsed: {elapsed_time:.2f},
        data: {data}
        '''), 200))
