"""Monitor stream class.

For receiving monitoring information from relay streams.
"""

import json
import os
import time

from pylsl import LostError, StreamInlet, StreamOutlet, resolve_bypred
from pylsltools.streams import BaseMarkerStream, MarkerStreamThread


class MonitorSender(BaseMarkerStream):
    """Stream to send monitoring messages.

    This should run in the same thread as the stream being monitored.
    """

    def __init__(self, name, content_type='monitor', source_id='',
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

    def send(self, text):
        """Send string."""
        if self.debug:
            print(f'{self.name}: {text}')
        self.outlet.push_sample(text)

    def send_JSON(self, **kwargs):
        """Send key=value pairs as a JSON encoded string."""
        if self.debug:
            print(f'{self.name}: {kwargs}')
        self.outlet.push_sample([json.dumps(kwargs)])


class MonitorReceiver(MarkerStreamThread):

    def __init__(self, name, content_type, hostname, source_id, *,
                 send_message_queue=None, json=False, debug=False, **kwargs):

        super().__init__(name, content_type, source_id=source_id, **kwargs)

        # Initialise local attributes.
        self.sender_name = name
        self.sender_hostname = hostname
        self.send_message_queue = send_message_queue
        self.json = json
        self.debug = debug
        self.inlet = None
        self.sample_count = 0

    def run(self):
        """Monitor Receiver main loop."""
        # We need to resolve the StreamInfo again because they don't
        # appear to be thread-safe.
        timeout = 0.5
        sender_info = None
        pred = ' and '.join([
                f"name='{self.sender_name}'",
                f"type='{self.content_type}'",
                f"hostname='{self.sender_hostname}'"
            ])

        while not sender_info and not self.is_stopped():
            sender_info = resolve_bypred(pred, timeout=timeout)
        if not sender_info:
            return
        sender_info = sender_info[0]

        self.inlet = StreamInlet(sender_info, max_buflen=1, max_chunklen=1,
                                 recover=False)
        if self.debug:
            print(self.inlet.info().as_xml())

        try:
            while not self.is_stopped():
                message, timestamp = self.inlet.pull_sample(timeout)
                if message:
                    if self.debug:
                        print(f'{self.name}, timestamp: {timestamp}, message: {message}')
                    # Handle message.
                    if self.json:
                        message = self.parse_message(message)
                    else:
                        message = {'message': message}
                        # message['sample_diff'] = (message['sample_count']
                        #                           - self.sample_count)
                        # message['stream_lost'] = False
                        # self.origin_name = message['name']
                        # self.sample_count = message['sample_count']
                    message['name'] = self.sender_name
                    message['hostname'] = self.sender_hostname
                    message['source_id'] = self.source_id
                    self.send_message_queue.put(message)
        except LostError as exc:
            print(f'{self.name}: {exc}')
            # self.send_message_queue.put({'name': self.origin_name,
            #                              'source_id': self.source_id,
            #                              'sample_count': self.sample_count,
            #                              'sample_diff': 0,
            #                              'stream_lost': True})
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            self.cleanup()
            print(f'Ended: {self.name}.')

    def cleanup(self):
        if self.inlet:
            self.inlet.close_stream()
        time.sleep(0.2)
