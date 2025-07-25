"""Generator stream class."""
import os
import textwrap
import time

import numpy as np
from pylsl import StreamInfo, StreamOutlet, local_clock

from pylsltools.streams import BaseStreamProcess


class GeneratorStream(BaseStreamProcess):
    """Data stream that runs in a separate process."""

    def __init__(
        self,
        name,
        content_type,
        channel_count,
        nominal_srate,
        channel_format,
        generator_fn,
        generator_args,
        *,
        source_id="",
        desc=None,
        channel_info=None,
        latency=0.1,
        start_delay=0,
        chunk_size=0,
        max_buffered=360,
        debug=False,
        **kwargs,
    ):
        super().__init__(
            name,
            content_type,
            channel_count,
            nominal_srate,
            channel_format,
            source_id=source_id,
            **kwargs,
        )

        # Set class attributes.
        self.generator_fn = generator_fn
        self.generator_args = generator_args
        self.desc = desc
        self.channel_info = channel_info
        self.latency = latency
        self.start_delay = start_delay
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.debug = debug

    def make_stream_info(self):
        """Return a pylsl StreamInfo object.

        StreamInfo objects are not thread safe, so must be created
        in the same thread as each stream.
        """
        info = StreamInfo(
            self.name,
            self.content_type,
            self.channel_count,
            self.nominal_srate,
            self.channel_format,
            self.source_id,
        )
        # Append custom metadata.
        if self.manufacturer:
            info.desc().append_child_value("manufacturer", self.manufacturer)
        info.desc().append_child_value('latency', str(self.latency))
        if isinstance(self.desc, dict):
            for k, v in self.desc.items():
                info.desc().append_child_value(k, v)
        if isinstance(self.channel_info, dict):
            for k, v in self.channel_info.items():
                info._set_channel_info(v, k)
        return info

    def initialise_time(self):
        now = local_clock()
        self.start_time = now
        self.logical_time = now
        self.elapsed_time = 0
        self.sample_count = 0
        self.delta = 1 / self.nominal_srate

    def check_continue(self):
        if self.is_stopped():
            return False
        else:
            return True

    def run(self):
        if not self.source_id:
            self.source_id = f"{os.path.basename(__file__)}:{os.getpid()}"

        info = self.make_stream_info()
        if self.debug:
            print(info.as_xml())

        self.outlet = StreamOutlet(info, self.chunk_size, self.max_buffered)

        generator = self.generator_fn(*self.generator_args, self.debug)
        # Pull first sample here to initialise the generator. There's probably
        # a better way to do this.
        _, sample = next(generator)

        if self.start_delay:
            print(f"Start delay: {self.start_delay}")
            time.sleep(self.start_delay)

        self.initialise_time()

        try:
            while self.check_continue():
                now = local_clock()
                t = self.logical_time + self.latency
                self.outlet.push_sample(sample, timestamp=t)
                if self.debug and (
                    self.nominal_srate <= 5
                    or (self.sample_count % self.nominal_srate) == 0
                ):
                    trace(
                        self.name,
                        now,
                        t,
                        self.logical_time,
                        self.elapsed_time,
                        self.content_type,
                        sample,
                    )
                self.sample_count += 1
                # Increment time for next iteration.
                self.logical_time += self.delta
                self.elapsed_time = self.logical_time - self.start_time
                # Pull next sample before calculating delay.
                _, sample = next(generator)
                # Avoid drift.
                delay = self.logical_time - local_clock()
                if delay > 0:
                    time.sleep(delay)
                elif delay < 0:
                    print(
                        f"LATE: {self.name} {delay:.6f} try increasing latency!"
                    )
        except KeyboardInterrupt:
            print(f"Stopping: {self.name}.")
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            print(f"Ended: {self.name}.")


def trace(name, now, timestamp, logical_time, elapsed_time, content_type, data):
    print(
        textwrap.fill(
            textwrap.dedent(
                f"""\
                {name}:
                now: {now:.4f},
                timestamp: {timestamp:.4f},
                logical: {logical_time:.4f},
                elapsed: {elapsed_time:.4f},
                {content_type}: {data.round(2)}
                """
            ),
            200,
        )
    )
