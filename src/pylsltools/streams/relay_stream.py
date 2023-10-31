"""Relay stream class.

For re-encoding and/or pre-processing a stream with optional remote
control. Useful for re-encoding a local stream to fix broken client
timestamps before relaying across the network.
"""

import textwrap

from pylsl import (LostError, StreamInlet, StreamOutlet, local_clock)
from pylsltools.streams import DataStream, MarkerStream


class RelayStream(DataStream):

    def __init__(self, sender_info, keep_orig_timestamps=False, monitor=False,
                 chunk_size=1, max_buffered=360, debug=False, **kwargs):

        print(f'sender info: {sender_info.as_xml()}')
        self.name = '_relay_' + sender_info.name()
        super().__init__(self.name,
                         sender_info.type(),
                         sender_info.channel_count(),
                         sender_info.nominal_srate(),
                         sender_info.channel_format(),
                         source_id=sender_info.source_id(),
                         # FIXME
                         #desc=self.inlet.info().desc()
                         )

        self.sender_info = sender_info
        self.keep_orig_timestamps = keep_orig_timestamps
        if monitor:
            self.monitor = MarkerStream('_monitor_' + self.sender_info.name(),
                                        content_type='monitor')
        else:
            self.monitor = None
        self.chunk_size = chunk_size
        self.max_buffered = max_buffered
        self.debug = debug

    def run(self):
        """Relay process main loop."""
        # FIXME: Integrate chunking option.
        # Chunk size should be 1 when re-encoding timestamps to ensure
        # we get samples as fast as possible.

        # FIXME: Recover=True will keep this process alive forever and
        # never throw a LostError. Recover=False will end this process
        # and delegate restarting to the continuous resolver if the
        # stream comes back online. Which is best? Handing control back
        # to the continuous resolver allows for a graceful exit.
        inlet = StreamInlet(self.sender_info,
                            max_buflen=self.max_buffered,
                            max_chunklen=self.chunk_size,
                            recover=False,
                            processing_flags=0)
        outlet = StreamOutlet(self.info, self.chunk_size,
                              self.max_buffered)
        if self.monitor:
            monitor_outlet = StreamOutlet(self.monitor.info, chunk_size=1)

        nominal_srate = self.sender_info.nominal_srate()
        sample_count = 0
        try:
            while not self.is_stopped():
                try:
                    sample, timestamp = inlet.pull_sample()
                    now = local_clock()
                    #chunk, timestamps = inlet.pull_chunk(timeout)
                except LostError as exc:
                    self.stop()
                    print(f'{self.name}: {exc}')
                    return
                except Exception as exc:
                    self.stop()
                    raise exc
                if timestamp:
                    if not self.keep_orig_timestamps:
                        timestamp = now
                    # Re-encode timestamp.
                    outlet.push_sample(sample, timestamp)
                    if self.debug:
                        if nominal_srate <= 5:
                            self.print(self.name, now, timestamp, sample)
                        else:
                            if (sample_count % nominal_srate) == 0:
                                self.print(self.name, now, timestamp, sample)
                    if self.monitor:
                        if (sample_count % nominal_srate) == 0:
                            monitor_outlet.push_sample([
                                f'{self.sender_info.name()} samples: {sample_count}'
                            ])
                    sample_count = sample_count + 1
                else:
                    print('no data')
        except Exception as exc:
            self.stop()
            raise exc
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}')
            self.stop()
        print(f'Ended: {self.info.name()}')

    def print(self, name, now, timestamp, data):
        print(textwrap.fill(textwrap.dedent(f'''
        {name}:
        now: {now:.6f},
        timestamp: {timestamp:.6f},
        data: {data}
        '''), 200))
