"""Test stream class."""

import math
import os
import textwrap
import time
import numpy as np

from pylsl import StreamOutlet, local_clock
from pylsltools import ControlStates
from pylsltools.streams import DataStream, MarkerStreamProcess


class BaseTestStream:
    """Test stream to generate deterministic streams of data.

    Each stream runs in it's own sub-process. Data is generated
    sample-by-sample so it is not the most efficient implementation but if
    performance becomes problematic latency can be increased to give each
    process time to generate data. However, timestamps are set according to
    logical time, so even if data is sent late is should still be timestamped
    correctly.
    """

    control_states = ControlStates

    def __init__(
        self,
        stream_idx,
        functions,
        name,
        *,
        source_id=None,
        max_time=None,
        max_samples=None,
        chunk_size=None,
        max_buffered=None,
        barrier=None,
        debug=False,
        **kwargs,
    ):
        if name:
            name = f"{name} test stream {stream_idx} {' '.join(g for g in functions)}"
        else:
            name = f"Test stream {stream_idx} {' '.join(g for g in functions)}"
        # If no source_id is provided default to script name and PID to
        # identify the source. In the default case if a stream is interrupted
        # due to network outage consumers should be able to automatically
        # recover data up to max_buffered length (default 6 minutes). However,
        # if the script is restarted the PID will be different and appear as a
        # new LSL stream so automatic recovery will not work. To test LSL
        # automatic recovery provide an explicit source_id.
        if not source_id:
            source_id = f"{os.path.basename(__file__)}:{os.getpid()}:{stream_idx}"

        super().__init__(
            name,
            source_id=source_id,
            **kwargs,
        )

        # Initialise values required by data generating functions.
        self.sample_count = 0
        self.elapsed_time = 0
        self.stream_idx = stream_idx

        # Initialise local attributes.
        self.functions = functions
        self.start_time = None
        self.stop_time = None
        self.max_time = max_time
        self.max_samples = max_samples
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.barrier = barrier
        self.debug = debug

    def run(self):
        info = self.make_stream_info()
        if self.debug:
            print(info.as_xml())

        outlet = StreamOutlet(info, self.chunk_size, self.max_buffered)

        # Synchronise sub-processes before entering main loop.
        if self.barrier is not None:
            self.barrier.wait()

        try:
            while self.check_continue():
                if self.start_time:
                    self.elapsed_time = self.logical_time - self.start_time
                    sample = self.generate_sample(self.elapsed_time, self.sample_count)
                    outlet.push_sample(sample, timestamp=self.logical_time)
                    if self.debug and (
                        self.nominal_srate <= 5
                        or (self.sample_count % self.nominal_srate) == 0
                    ):
                        self.print(
                            self.name,
                            local_clock(),
                            self.logical_time,
                            self.elapsed_time,
                            self.content_type,
                            sample,
                        )
                    self.sample_count = self.sample_count + 1
                self.logical_time = self.logical_time + self.delta
                # Avoid drift.
                delay = self.logical_time - (local_clock() + self.latency)
                if delay > 0:
                    time.sleep(delay)
                elif (delay + self.latency) < 0:
                    print(
                        f"LATE: {self.name} {delay + self.latency:.6f} try increasing latency!"
                    )
        except KeyboardInterrupt:
            print(f"Stopping: {self.name}.")
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            self.cleanup()
            print(f"Ended: {self.name}.")

    def initialise_time(self, start_time, latency):
        # Generate data slightly ahead of time to give all sub-processes time
        # to run.
        self.latency = latency
        self.start_time = start_time
        self.logical_time = start_time
        self.elapsed_time = 0

    def check_continue(self):
        if self.is_stopped():
            return False
        if not self.check_control_state():
            return False
        if self.stop_time is not None:
            if self.logical_time >= self.stop_time:
                if self.debug:
                    print("Synchronised stop time.")
                self.start_time = None
                self.stop_time = None
        if self.max_time is not None:
            if self.elapsed_time >= self.max_time:
                if self.debug:
                    print(f"{self.name} max time reached.")
                return False
        if self.max_samples is not None:
            if self.sample_count >= self.max_samples:
                if self.debug:
                    print(f"{self.name} max samples reached.")
                return False
        return True

    def check_control_state(self):
        if self.start_time and self.recv_message_queue.empty():
            pass
        else:
            if self.debug:
                print(f"{self.name}: waiting for or handling a message")
            # This is blocking.
            message = self.recv_message_queue.get()
            if self.debug:
                print(
                    f"{self.name} received message: {message}, local_clock: {local_clock()}"
                )
            # All time-stamps are in the local timebase.
            if message["state"] == self.control_states.PAUSE:
                self.stop_time = message["time_stamp"]
            if message["state"] == self.control_states.START:
                start_time = message["time_stamp"]
                latency = message["latency"]
                if not start_time:
                    # Non-synchronised timestamps: Use local real-time of
                    # this process.
                    start_time = local_clock()
                # Initialise time values.
                self.initialise_time(start_time, latency)
            if message["state"] == self.control_states.STOP:
                self.stop_time = message["time_stamp"]
        return True

    def generate_sample(self, time, sample_idx):
        sample = [
            self.generate_channel_data(time, sample_idx, channel_idx)
            for channel_idx in range(self.channel_count)
        ]
        sample = np.array(sample, dtype=self.dtype)
        return sample

    def generate_channel_data(self, time, sample_idx, channel_idx):
        fn = self.functions[channel_idx % len(self.functions)]
        if fn == "stream-id":
            return self.stream_idx
        if fn == "stream-seq":
            return self.stream_idx + channel_idx
        if fn == "counter":
            return sample_idx
        if fn == "counter+":
            return (sample_idx * self.channel_count) + channel_idx
        if fn == "counter-mod-fs":
            return sample_idx % self.nominal_srate
        if fn == "impulse":
            if sample_idx % self.nominal_srate == 0:
                return 1
            else:
                return 0
        if fn == "sine":
            return math.sin((2 * math.pi) * time)  # 1 Hz
        if fn == "sine+":
            return math.sin((2 * math.pi) * 2**channel_idx * time)

    def print(self, name, now, timestamp, elapsed_time, content_type, data):
        print(
            textwrap.fill(
                textwrap.dedent(
                    f"""\
                    {name}:
                    now: {now:.6f},
                    timestamp: {timestamp:.6f},
                    elapsed: {elapsed_time:.2f},
                    {content_type}: {data}
                    """
                ),
                200,
            )
        )


class TestDataStream(BaseTestStream, DataStream):
    def __init__(
        self,
        stream_idx,
        functions,
        name,
        content_type,
        channel_count,
        nominal_srate,
        *,
        channel_format,
        source_id=None,
        channel_labels=None,
        channel_types=None,
        channel_units=None,
        max_time=None,
        max_samples=None,
        chunk_size=None,
        max_buffered=None,
        recv_message_queue=None,
        send_message_queue=None,
        barrier=None,
        debug=False,
        **kwargs,
    ):
        # Set class attributes.
        self.delta = 1 / nominal_srate
        self.dtype = channel_format

        super().__init__(
            stream_idx,
            functions,
            name,
            content_type=content_type,
            channel_count=channel_count,
            nominal_srate=nominal_srate,
            channel_format=channel_format,
            source_id=source_id,
            channel_labels=channel_labels,
            channel_types=channel_types,
            channel_units=channel_units,
            max_time=max_time,
            max_samples=max_samples,
            chunk_size=chunk_size,
            max_buffered=max_buffered,
            recv_message_queue=recv_message_queue,
            send_message_queue=send_message_queue,
            barrier=barrier,
            debug=debug,
            **kwargs,
        )


class TestMarkerStream(BaseTestStream, MarkerStreamProcess):
    def __init__(
        self,
        stream_idx,
        functions,
        name,
        content_type,
        channel_count,
        nominal_srate,
        *,
        source_id=None,
        channel_labels=None,
        max_time=None,
        max_samples=None,
        chunk_size=None,
        max_buffered=None,
        recv_message_queue=None,
        send_message_queue=None,
        barrier=None,
        debug=False,
        **kwargs,
    ):
        # Set class attributes.
        self.dtype = str
        self.delta = 1 / nominal_srate

        super().__init__(
            stream_idx,
            functions,
            name,
            content_type=content_type,
            channel_count=channel_count,
            source_id=source_id,
            channel_labels=channel_labels,
            max_time=max_time,
            max_samples=max_samples,
            chunk_size=chunk_size,
            max_buffered=max_buffered,
            recv_message_queue=recv_message_queue,
            send_message_queue=send_message_queue,
            barrier=barrier,
            debug=debug,
            **kwargs,
        )
