"""Relay stream class.

For re-encoding and/or pre-processing a stream with optional remote
control. Useful for re-encoding a local stream to fix broken client
timestamps before relaying across the network.
"""

import textwrap

from pylsl import (LostError, StreamInlet, StreamOutlet, local_clock,
                   resolve_bypred)
from pylsltools import ControlStates
from pylsltools.streams import DataStream, MonitorSender


class RelayStream(DataStream):
    """Relay, monitor and pre-process streams."""

    control_states = ControlStates

    def __init__(self, name, content_type, channel_count, nominal_srate,
                 channel_format, hostname, *, re_encode_timestamps=False,
                 output=True, monitor=True, monitor_interval=5, chunk_size=1,
                 max_buffered=360, recv_message_queue=None,
                 send_message_queue=None, debug=False, **kwargs):

        relay_name = '_relay_' + name

        super().__init__(relay_name, content_type, channel_count,
                         nominal_srate, channel_format,
                         recv_message_queue=recv_message_queue,
                         send_message_queue=send_message_queue)

        # Initialise local attributes.
        self.sender_name = name
        self.sender_hostname = hostname
        self.re_encode_timestamps = re_encode_timestamps
        self.output = output
        self.monitor = monitor
        self.monitor_interval = monitor_interval
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.debug = debug

    def run(self):
        """Relay process main loop."""
        # FIXME: Integrate chunking option.
        # Chunk size should be 1 when re-encoding timestamps to ensure
        # we get samples as fast as possible.

        # We need to resolve the StreamInfo again because they don't
        # appear to be thread-safe.
        sender_info = None
        pred = ' and '.join([
                f"name='{self.sender_name}'",
                f"type='{self.content_type}'",
                f"channel_count={self.channel_count}",
                f"hostname='{self.sender_hostname}'"
            ])
        while not sender_info and not self.is_stopped():
            sender_info = resolve_bypred(pred, timeout=0.5)
        if not sender_info:
            return
        sender_info = sender_info[0]

        # Recover=True will keep this process alive forever and never
        # throw a LostError. Recover=False will end this process and
        # delegate restarting to the continuous resolver if the stream
        # comes back online. Which is best? Handing control back to the
        # continuous resolver at least allows for a graceful exit.
        inlet = StreamInlet(sender_info,
                            max_buflen=self.max_buffered,
                            max_chunklen=self.chunk_size,
                            recover=False,
                            processing_flags=0)

        source_id = '_relay_' + inlet.info().source_id()

        if self.output:
            # FIXME: Append desc custom metadata.
            info = self.make_stream_info(self.name,
                                         self.content_type,
                                         self.channel_count,
                                         self.nominal_srate,
                                         self.channel_format,
                                         source_id=source_id)
            outlet = StreamOutlet(info, self.chunk_size, self.max_buffered)

        if self.monitor:
            self.monitor = MonitorSender('_monitor_' + self.sender_name,
                                         content_type='monitor',
                                         debug=self.debug)
        sample_count = 0

        try:
            # TODO: Integrate control states!
            while not self.is_stopped():
                sample, timestamp = inlet.pull_sample()
                now = local_clock()
                #chunk, timestamps = inlet.pull_chunk(timeout)
                if sample:
                    if self.re_encode_timestamps:
                        # Re-encode timestamp.
                        timestamp = now
                    if self.output:
                        outlet.push_sample(sample, timestamp)
                    if self.debug and (
                            self.nominal_srate <= 5
                            or (sample_count % self.nominal_srate) == 0):
                        self.print(self.name, now, timestamp,
                                   self.content_type, sample)
                    if self.monitor and (sample_count %
                                         (self.nominal_srate *
                                          self.monitor_interval)) == 0:
                        self.monitor.send(name=self.sender_name,
                                          sample_count=sample_count)
                    sample_count = sample_count + 1
        except LostError as exc:
            print(f'{self.name}: {exc}')
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}')
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            print(f'Ended: {self.name}.')

    def print(self, name, now, timestamp, content_type, data):
        print(textwrap.fill(textwrap.dedent(f'''\
        {name}:
        now: {now:.6f},
        timestamp: {timestamp:.6f},
        {content_type}: {data}
        '''), 200))
