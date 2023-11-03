"""Monitor stream class.

For receiving monitoring information from relay streams.
"""

import json
import platform

from pylsl import LostError, StreamInlet, StreamOutlet
from pylsltools.streams import BaseMarkerStream, MarkerStreamThread


class MonitorSender(BaseMarkerStream):

    def __init__(self, name, content_type='monitor', source_id=None,
                 manufacturer='pylsltools', debug=False, **kwargs):

        if not source_id:
            source_id = platform.node()

        info = self.make_stream_info(name, content_type, source_id,
                                     manufacturer)
        super().__init__(info, **kwargs)

        # Set class attributes.
        self.name = name
        self.debug = debug
        self.outlet = StreamOutlet(self.info, chunk_size=1, max_buffered=1)

    def send(self, **kwargs):
        if self.debug:
            print(f'{self.name}: {kwargs}')
        self.outlet.push_sample([json.dumps(kwargs)])


class MonitorReceiver(MarkerStreamThread):

    def __init__(self, sender_info, debug=False, **kwargs):
        super().__init__(sender_info, **kwargs)

        self.name = sender_info.name()
        self.debug = debug

    def run(self):
        inlet = StreamInlet(self.info, max_buflen=1, max_chunklen=1,
                            recover=False)
        try:
            while not self.is_stopped():
                try:
                    message, timestamp = inlet.pull_sample()
                except LostError as exc:
                    self.stop()
                    print(f'{self.name}: {exc}')
                    return
                if self.debug:
                    print(f'{self.name}, timestamp: {timestamp}, message: {message}')
                # Handle message.
                message = self.parse_message(message)
                if message:
                    print(message)
        except Exception as exc:
            self.stop()
            raise exc
