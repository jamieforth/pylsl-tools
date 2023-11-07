"""Monitor stream class.

For receiving monitoring information from relay streams.
"""

import os
import json

from pylsl import LostError, StreamInlet, StreamOutlet, resolve_bypred
from pylsltools.streams import BaseMarkerStream, MarkerStreamThread


class MonitorSender(BaseMarkerStream):
    """Stream to send monitoring messages.

    This should run in the same thread as the stream being monitored.
    """

    def __init__(self, name, content_type='monitor', source_id=None,
                 manufacturer='pylsltools', debug=False, **kwargs):

        if not source_id:
            source_id = f'{os.path.basename(__file__)}:{os.getpid()}'

        super().__init__(name, content_type, source_id=source_id,
                         manufacturer=manufacturer, **kwargs)

        # Set class attributes.
        self.debug = debug
        info = self.make_stream_info(name, content_type, source_id,
                                     manufacturer)

        self.outlet = StreamOutlet(info, chunk_size=1, max_buffered=1)

    def send(self, **kwargs):
        """Send key=value pairs as a JSON encoded string."""
        if self.debug:
            print(f'{self.name}: {kwargs}')
        self.outlet.push_sample([json.dumps(kwargs)])


class MonitorReceiver(MarkerStreamThread):

    def __init__(self, name, content_type, hostname, debug=False, **kwargs):
        super().__init__(name, content_type, **kwargs)

        # Initialise local attributes.
        self.sender_name = name
        self.sender_hostname = hostname
        self.debug = debug

    def run(self):
        """Monitor Receiver main loop."""
        # We need to resolve the StreamInfo again because they don't
        # appear to be thread-safe.
        sender_info = None
        pred = ' and '.join([
                f"name='{self.sender_name}'",
                f"type='{self.content_type}'",
                f"hostname='{self.sender_hostname}'"
            ])

        while not sender_info and not self.is_stopped():
            sender_info = resolve_bypred(pred, timeout=0.5)
        if not sender_info:
            return
        sender_info = sender_info[0]

        self.inlet = StreamInlet(sender_info, max_buflen=1, max_chunklen=1,
                                 recover=False)
        if self.debug:
            print(self.inlet.info().as_xml())

        try:
            while not self.is_stopped():
                message, timestamp = self.inlet.pull_sample(0.5)
                if message:
                    if self.debug:
                        print(f'{self.name}, timestamp: {timestamp}, message: {message}')
                        # Handle message.
                        message = self.parse_message(message)
                    print(message)
        except LostError as exc:
            print(f'{self.name}: {exc}')
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            self.cleanup()
            print(f'Ended: {self.name}.')

    def cleanup(self):
        if isinstance(self.inlet, StreamInlet):
            self.inlet.close_stream()
