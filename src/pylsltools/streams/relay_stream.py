"""Relay stream.

Can re-encoding and/or pre-processing a stream with optional remote
control. Useful for re-encoding a local stream to fix broken client timestamps
before relaying across the network.
"""

import dataclasses
import logging
import os
import textwrap

from pylsl import StreamInlet, StreamOutlet, local_clock, resolve_bypred
from pylsl.util import LostError

from pylsltools import ControlStates
from pylsltools.logging import init_sub_process_logging
from pylsltools.streams import DataStream, MonitorSender, StreamInfoBoundData

logger = logging.getLogger(__name__)


class RelayStream(DataStream):
    """Relay, monitor and pre-process streams."""

    control_states = ControlStates

    def __init__(
        self,
        info: StreamInfoBoundData,
        inlet_options,
        outlet_options,
        *,
        re_encode_timestamps=False,
        output=True,
        monitor=True,
        monitor_interval=5,
        recv_message_queue=None,
        send_message_queue=None,
        log_queue=None,
        log_level=None,
        **kwargs,
    ):
        # Store incoming stream info.
        self.sender_info = info

        # Update info for what will become the relay stream.
        info = dataclasses.copy.copy(info)
        info.name = "_relay_" + info.name
        info.source_id = f"_relay_{info.source_id}:{os.getpid()}"
        logger.debug(info)
        super().__init__(
            info,
            recv_message_queue=recv_message_queue,
            send_message_queue=send_message_queue,
            log_queue=log_queue,
            log_level=log_level,
        )
        # Initialise local attributes.
        self.inlet_options = inlet_options
        self.outlet_options = outlet_options
        self.re_encode_timestamps = re_encode_timestamps
        self.output = output
        self.monitor = monitor
        self.monitor_interval = monitor_interval
        self.inlet = None

    def run(self):
        """Relay process main loop."""
        # FIXME: Integrate chunking option.
        # Chunk size should be 1 when re-encoding timestamps to ensure we get
        # samples as fast as possible.

        init_sub_process_logging(self.log_queue, self.log_level)

        # We need to resolve the StreamInfo again because they don't appear to
        # be thread-safe.
        sender_info = None
        pred = " and ".join(
            [
                f"name='{self.sender_info.name}'",
                f"type='{self.sender_info.content_type}'",
                f"channel_count={self.sender_info.channel_count}",
                f"hostname='{self.sender_info.hostname}'",
            ]
        )
        while not sender_info and not self.is_stopped():
            sender_info = resolve_bypred(pred, timeout=0.5)
        if not sender_info:
            return
        sender_info = sender_info[0]

        # Recover=True will keep this process alive forever and never throw a
        # LostError. Recover=False will end this process and delegate
        # restarting to the continuous resolver if the stream comes back
        # online. Which is best? Handing control back to the continuous
        # resolver at least allows for a graceful exit. Alternatively, set a
        # timeout on pull_sample and return after a period of waiting to see if
        # the stream reconnects.
        self.inlet = StreamInlet(
            sender_info,
            self.inlet_options.max_buffer_size,
            self.inlet_options.max_chunk_size,
            self.inlet_options.recover,
            self.inlet_options.processing_flags,
        )

        if self.output:
            # FIXME: Append desc custom metadata.
            info = self.make_stream_info()
            outlet = StreamOutlet(
                info,
                max_buffered=self.outlet_options.max_buffer_size,
                chunk_size=self.outlet_options.max_chunk_size,
            )

        if self.monitor:
            self.monitor = MonitorSender(
                "_monitor_" + self.sender_info.name,
                content_type="monitor",
            )

        sample_count = 0
        timeout = max(1 / self.sender_info.nominal_srate * 1.5, 0.1)

        try:
            # TODO: Integrate control states!
            # Could use this to pre-process/reduce data being relayed.
            while not self.is_stopped():
                sample, timestamp = self.inlet.pull_sample(timeout)
                now = local_clock()
                # chunk, timestamps = self.inlet.pull_chunk(timeout)
                if sample:
                    if self.re_encode_timestamps:
                        # Re-encode timestamp.
                        timestamp = now
                    if self.output:
                        outlet.push_sample(sample, timestamp)
                    if (
                        self.info.nominal_srate <= 5
                        or (sample_count % self.info.nominal_srate) == 0
                    ):
                        logger.debug(
                            self.fmt_log(
                                self.info.name,
                                now,
                                timestamp,
                                self.info.content_type,
                                sample,
                            )
                        )
                    if self.monitor and (
                        self.info.nominal_srate == 0
                        or (
                            sample_count
                            % (self.info.nominal_srate * self.monitor_interval)
                        )
                        == 0
                    ):
                        self.monitor.send_JSON(
                            hostname=self.sender_info.hostname,
                            name=self.sender_info.name,
                            sample_count=sample_count,
                        )
                    sample_count += 1
        except LostError as exc:
            print(f"{self.info.name}: {exc}")
        except KeyboardInterrupt:
            print(f"Stopping: {self.info.name}")
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            print(f"Ended: {self.info.name}.")

    def fmt_log(self, name, now, timestamp, content_type, data):
        return textwrap.fill(
            textwrap.dedent(f"""\
        {name}:
        now: {now:.6f},
        timestamp: {timestamp:.6f},
        {content_type}: {data}
        """),
            200,
        )

    def cleanup(self):
        print("Relay cleanup")
        if self.inlet:
            self.inlet.close_stream()
