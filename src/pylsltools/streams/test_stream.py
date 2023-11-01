"""Test stream class."""

import os
import textwrap
import time

from pylsl import StreamOutlet, local_clock
from pylsltools.streams import DataStream


class TestStream (DataStream):
    """Test stream to generate deterministic streams of data.

    Each stream runs in it's own sub-process. Data is generated
    sample-by-sample so it is not the most efficient implementation but
    if performance becomes problematic latency can be increased to give
    each process time to generate data. However, timestamps are set
    according to logical time, so even if data is sent late is should
    still be timestamped correctly.
    """
    def __init__(self, stream_idx, generators, name, content_type,
                 channel_count, nominal_srate, channel_format, *,
                 source_id=None, channel_labels=None, channel_types=None,
                 channel_units=None, start_time=None, max_time=None,
                 max_samples=None, chunk_size=None, max_buffered=None,
                 barrier=None, debug=False, **kwargs):
        print('TestStream', stream_idx, generators, name, content_type,
              channel_count, nominal_srate, channel_format, source_id,
              channel_labels, channel_types, channel_units, start_time,
              max_time, max_samples, chunk_size, max_buffered, debug, kwargs)
        if name:
            name = f'{name} test stream {stream_idx} {" ".join(g for g in generators)}'
        else:
            name = f'Test stream {stream_idx} {" ".join(g for g in generators)}'
        # If no source_id is provided default to script name and PID to
        # identify the source. In the default case if a stream is
        # interrupted due to network outage consumers should be able to
        # automatically recover data up to max_buffered length (default
        # 6 minutes). However, if the script is restarted the PID will
        # be different and appear as a new LSL stream so automatic
        # recovery will not work. To test LSL automatic recovery provide
        # an explicit source_id.
        if source_id is None:
            source_id = f'{os.path.basename(__file__)}:{os.getpid()}'

        super().__init__(name, content_type, channel_count,
                         nominal_srate, channel_format,
                         source_id=source_id,
                         channel_labels=channel_labels,
                         channel_types=channel_types,
                         channel_units=channel_units, **kwargs)

        # Store values required by generators as class attributes.
        self.stream_idx = stream_idx
        self.channel_count = channel_count
        self.nominal_srate = nominal_srate

        # Initialise local attributes.
        self.generators = generators
        self.start_time = start_time
        self.max_time = max_time
        self.max_samples = max_samples
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.barrier = barrier
        self.debug = debug

    def run(self):
        if self.start_time is None:
            self.start_time = local_clock()
        sample_count = 0
        logical_time = self.start_time
        delta = 1 / self.info.nominal_srate()
        self.outlet = StreamOutlet(self.info, self.chunk_size,
                                   self.max_buffered)
        nominal_srate = self.info.nominal_srate()
        content_type = self.info.type()

        # Ensure all processes wait here until all other sub-processes
        # are initialised before entering main loop.
        if self.barrier is not None:
            self.barrier.wait()
        try:
            while not self.is_stopped():
                now = local_clock()
                elapsed_time = logical_time - self.start_time
                sample = self.generate_sample(elapsed_time, sample_count)
                self.outlet.push_sample(sample, timestamp=logical_time)
                if self.debug and (nominal_srate <= 5
                                   or (sample_count % nominal_srate) == 0):
                    self.print(self.name, now, logical_time, elapsed_time,
                               content_type, sample)
                sample_count = sample_count + 1
                self.check_continue(elapsed_time, sample_count, self.max_time,
                                    self.max_samples)
                logical_time = logical_time + delta
                # Avoid drift.
                delay = logical_time - local_clock()
                if delay > 0:
                    time.sleep(delay)
                else:
                    print(f'LATE: {self.name} {delay:.6f} try increasing latency!')
        except Exception as exc:
            self.stop()
            raise exc
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}.')
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
            if sample_idx % self.nominal_srate == 0:
                return 1
            else:
                return 0

    def print(self, name, now, timestamp, elapsed_time, content_type, data):
        print(textwrap.fill(textwrap.dedent(f'''
        {name}:
        now: {now:.6f},
        timestamp: {timestamp:.6f},
        elapsed: {elapsed_time:.2f},
        {content_type}: {data}
        '''), 200))
