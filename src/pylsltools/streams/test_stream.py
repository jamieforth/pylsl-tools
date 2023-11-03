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
                 channel_units=None, start_time=None, latency=None,
                 max_time=None, max_samples=None, chunk_size=None,
                 max_buffered=None, barrier=None, controller=None, debug=False,
                 **kwargs):
        print('TestStream', stream_idx, generators, name, content_type,
              channel_count, nominal_srate, channel_format, source_id,
              channel_labels, channel_types, channel_units, start_time,
              latency, max_time, max_samples, chunk_size, max_buffered,
              debug, kwargs)
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
        self.sample_count = 0
        self.stream_idx = stream_idx
        self.channel_count = channel_count
        self.nominal_srate = nominal_srate

        # Initialise local attributes.
        self.generators = generators
        self.start_time = start_time
        self.latency = latency
        self.max_time = max_time
        self.max_samples = max_samples
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.barrier = barrier
        self.controller = controller
        self.debug = debug

    def run(self):
        delta = 1 / self.info.nominal_srate()
        nominal_srate = self.info.nominal_srate()
        content_type = self.info.type()
        self.outlet = StreamOutlet(self.info, self.chunk_size,
                                   self.max_buffered)

        # Initialise start time. If a controller is used time will be
        # initialised later according to a start control message
        # timestamp.
        if self.controller is not None:
            # Initialise current state to keep track of state changes.
            self.state = None
        else:
            if not self.start_time:
                # Non-synchronised timestamps: Use local real-time of
                # this process.
                self.start_time = local_clock()
            # Initialise time values.
            self.initialise_time(self.start_time)

        # FIXME: Need to synchronise wait time over all processes.
        # if self.wait_for_consumers:
        #     print('Waiting for consumers.')
        #     timeout = 1
        #     start_delay = timeout
        #     try:
        #         while self.outlet.wait_for_consumers(timeout):
        #             start_delay = start_delay + timeout
        #     except KeyboardInterrupt:
        #         pass
        #     print(start_delay)
        #     self.start_time = self.start_time + start_delay

        # Synchronise sub-processes before entering main loop.
        if self.barrier is not None:
            self.barrier.wait()

        try:
            while self.check_continue():
                self.elapsed_time = self.logical_time - self.start_time
                sample = self.generate_sample(self.elapsed_time,
                                              self.sample_count)
                self.outlet.push_sample(sample, timestamp=self.logical_time)
                if self.debug and (nominal_srate <= 5
                                   or (self.sample_count % nominal_srate) == 0):
                    self.print(self.name, local_clock(), self.logical_time,
                               self.elapsed_time, content_type, sample)
                self.sample_count = self.sample_count + 1
                self.logical_time = self.logical_time + delta
                # Avoid drift.
                delay = self.logical_time - (local_clock() + self.latency)
                if delay > 0:
                    time.sleep(delay)
                elif (delay + self.latency) < 0:
                    print(f'LATE: {self.name} {delay + self.latency:.6f} try increasing latency!')
        except Exception as exc:
            self.stop()
            raise exc
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}.')
            self.stop()
        print(f'Ended: {self.name}.')

    def initialise_time(self, start_time):
        # Generate data slightly ahead of time to give all
        # sub-processes time to run.
        self.start_time = start_time + self.latency
        self.logical_time = self.start_time
        self.elapsed_time = 0

    def check_continue(self):
        if self.is_stopped():
            return False
        if self.max_time is not None:
            if self.elapsed_time >= self.max_time:
                print(f'{self.name} max time reached.')
                return False
        if self.max_samples is not None:
            if self.sample_count >= self.max_samples:
                print(f'{self.name} max samples reached.')
                return False
        return True and self.check_control_state()

    def check_control_state(self):
        if self.controller is not None and (
                # Control state has changed.
                self.controller.state() != self.state):
            if self.controller.state() == self.controller.states.STOP:
                self.state = self.controller.state()
                with self.controller.condition:
                    # Wait for state change.
                    self.controller.condition.wait()
            if self.controller.state() == self.controller.states.START:
                self.state = self.controller.state()
                # Get synchronised start time in local timebase.
                start_time = self.controller.timestamp()
                #print(f'Controller time: {start_time}, local time: {local_clock()}')
                self.initialise_time(start_time)
                return True
            if self.controller.state() == self.controller.states.QUIT:
                return False
        return True

    def generate_sample(self, time, sample_idx):
        sample = [self.generate_channel_data(time, sample_idx, channel_idx)
                  for channel_idx in range(self.channel_count)]
        return sample

    def generate_channel_data(self, time, sample_idx, channel_idx):
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
