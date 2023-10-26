"""Relay stream class.

For re-encoding and/or pre-processing a stream with optional remote
control. Useful for re-encoding a local stream to fix broken client
timestamps before relaying across the network.
"""

from threading import Thread
from pylsl import StreamInlet, LostError, IRREGULAR_RATE
from pylsltools.streams.lsl_sender import LSLSender

class RelayStream():

    is_running = False

    def __init__(self, info):

        self.info = info
        print(f'stream: {info.as_xml()}')

    def start(self, chunk_size, max_buffered, keep_orig_timestamps=False,
              monitor=False, debug=False):
        """Start relay thread."""
        # Chunk size should be 1 when re-encoding timestamps to ensure
        # we get samples as fast as possible.

        # FIXME: Recover=True will keep this thread alive forever and
        # never throw a LostError. Recover=False will end this thread
        # and delegate restarting to the continuous resolver if the
        # stream comes back online. Which is best?
        self.inlet = StreamInlet(self.info, max_buflen=max_buffered,
                                 max_chunklen=chunk_size, recover=True,
                                 processing_flags=0)
        if not monitor:
            self.sender = LSLSender('_relay_' + self.info.name(),
                                    self.info.type(),
                                    self.info.channel_count(),
                                    self.info.nominal_srate(),
                                    self.info.channel_format(),
                                    self.info.source_id(),
                                    # FIXME
                                    #desc=self.inlet.info().desc()
                                    )
            self.sender.create_outlet(chunk_size, max_buffered)
            self.monitor = LSLSender('_monitor_' + self.info.name(),
                                    'monitor',
                                     1,
                                     IRREGULAR_RATE,
                                     'string',
                                     self.info.source_id())
            self.monitor.create_outlet(1, max_buffered)


            # FIXME: Integrate chunking option.
            timeout = max(0.005, chunk_size / self.info.nominal_srate())
            self.thread = Thread(target=self.run, args=[timeout, debug])
            self.thread.start()
        else:
            self.thread = Thread(target=self.run_monitor, args=[debug])
            self.thread.start()
        return self

    def stop(self):
        """Stop relay thread."""
        print(f'Stopping relay stream: {self.info.name()}')
        self.is_running = False

    def run(self, timeout, debug):
        """Relay thread main loop."""
        self.is_running = True
        i = 0
        while self.is_running:
            #chunk, timestamps = self.inlet.pull_chunk(timeout)
            try:
                sample, timestamp = self.inlet.pull_sample()
            except LostError as exc:
                self.stop()
                print(exc)
                return
            except Exception as exc:
                self.stop()
                raise exc
            if timestamp:
                self.sender.push_sample(sample)
                #self.sender.push_sample(chunk)
                if debug:
                    if self.info.nominal_srate() < 5:
                        print(timestamp, sample)
                    else:
                        if (i % self.info.nominal_srate()) == 0:
                            print(timestamp, sample)
                if (i % self.info.nominal_srate()) == 0:
                    self.monitor.push_sample([f'{self.info.name()} samples: {i}'])
                i = i + 1
            else:
                print('no data')
        self.is_running = False
        print(f'Relay thread ended: {self.info.name()}')

    def run_monitor(self, debug):
        """Monitor thread main loop."""
        self.is_running = True
        i = 0
        while self.is_running:
            try:
                sample, timestamp = self.inlet.pull_sample()
            except LostError as exc:
                self.stop()
                print(exc)
                return
            except Exception as exc:
                self.stop()
                raise exc
            if timestamp:
                print(sample)
            else:
                print('no data')
        self.is_running = False
        print(f'Monitor thread ended: {self.info.name()}')
