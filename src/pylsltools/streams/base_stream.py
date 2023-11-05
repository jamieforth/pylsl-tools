"""Base stream class."""

import json
import multiprocessing
import threading
from multiprocessing import Process
from threading import Thread

from pylsl import IRREGULAR_RATE, StreamInfo


class BaseStream():
    """Base stream initialised from an LSL info object."""

    def __init__(self, name, content_type, channel_count, nominal_srate,
                 channel_format, *, source_id, manufacturer, **kwargs):
        super().__init__(name=name, **kwargs)

        # Set class attributes.
        self.content_type = content_type
        self.channel_count = channel_count
        self.nominal_srate = nominal_srate
        self.channel_format = channel_format
        self.source_id = source_id
        self.manufacturer = manufacturer

    def cleanup(self):
        pass

class DataStream(BaseStream, Process):
    """Data stream that runs in a separate process."""

    def __init__(self, name, content_type, channel_count, nominal_srate,
                 channel_format, recv_message_queue, send_message_queue, *,
                 source_id=None, manufacturer='pylsltools',
                 channel_labels=None, channel_types=None, channel_units=None,
                 **kwargs):
        super().__init__(name, content_type, channel_count, nominal_srate,
                         channel_format, source_id=source_id,
                         manufacturer=manufacturer, **kwargs)

        # Set class attributes.
        self.recv_message_queue = recv_message_queue
        self.send_message_queue = send_message_queue
        self.channel_labels = channel_labels
        self.channel_types = channel_types
        self.channel_units = channel_units

        # Event to terminate the process.
        self.stop_event = multiprocessing.Event()

    def run(self):
        pass

    def stop(self):
        if not self.is_stopped():
            self.stop_event.set()
            if self.send_message_queue:
                # Unblock any waiting threads.
                self.send_message_queue.put(f'Stream {self.name} stopped.')
            self.cleanup()

    def is_stopped(self):
        return self.stop_event.is_set()

    def make_stream_info(self, name, content_type, channel_count,
                         nominal_srate, channel_format, source_id,
                         manufacturer, channel_labels=None, channel_types=None,
                         channel_units=None):
        """Return a pylsl StreamInfo object.

        StreamInfo objects are not thread safe, so must be created
        in the same thread as each stream.
        """
        info = StreamInfo(name,
                          content_type,
                          channel_count,
                          nominal_srate,
                          channel_format,
                          source_id)
        # Append custom metadata.
        if manufacturer:
            info.desc().append_child_value('manufacturer', manufacturer)
        channel_labels = self.check_channel_labels(channel_labels,
                                                   channel_count)
        channel_types = self.check_channel_types(channel_types,
                                                 channel_count)
        channel_units = self.check_channel_units(channel_units,
                                                 channel_count)
        channels = info.desc().append_child('channels')
        for i in range(channel_count):
            ch = channels.append_child('channel')
            ch.append_child_value('label', channel_labels[i])
            if channel_types:
                ch.append_child_value('type', channel_types[i])
            if channel_units:
                ch.append_child_value('unit', channel_units[i])
        return info

    def check_channel_labels(self, channel_labels, channel_count):
        if isinstance(channel_labels, list):
            if len(channel_labels) == channel_count:
                pass
            else:
                print('{channel_count} channel labels required, {len(channel_labels)} provided.')
                channel_labels = self.make_channel_labels(channel_count)
        else:
            channel_labels = self.make_channel_labels(channel_count)
        return channel_labels

    def check_channel_types(self, channel_types, channel_count):
        if isinstance(channel_types, list):
            if len(channel_types) == channel_count:
                pass
            else:
                print('{channel_count} channel types required, {len(channel_types)} provided.')
                channel_types = 'misc'
        if isinstance(channel_types, str):
            channel_types = [channel_types] * channel_count
        return channel_types

    def check_channel_units(self, channel_units, channel_count):
        if isinstance(channel_units, list):
            if len(channel_units) == channel_count:
                pass
            else:
                print('{channel_count} channel units required, {len(channel_units)} provided.')
                channel_units = None
        if isinstance(channel_units, str):
            channel_units = [channel_units] * channel_count
        return channel_units

    def make_channel_labels(self, channel_count):
        return [f'ch:{channel_idx:0=2d}' for channel_idx in
                range(channel_count)]


class BaseMarkerStream(BaseStream):
    """Simple marker stream."""

    def __init__(self, name, content_type, *, source_id, manufacturer,
                 **kwargs):
        channel_count = 1
        nominal_srate = IRREGULAR_RATE
        channel_format = 'string'

        super().__init__(name, content_type, channel_count, nominal_srate,
                         channel_format, source_id=source_id,
                         manufacturer=manufacturer, **kwargs)

    def make_stream_info(self, name, content_type, source_id, manufacturer):
        """Return a pylsl StreamInfo object.

        StreamInfo objects are not thread safe, so must be created
        in the same thread as each stream.
        """
        info = StreamInfo(name,
                          content_type,
                          self.channel_count,
                          self.nominal_srate,
                          self.channel_format,
                          source_id)
        # Append custom metadata.
        if manufacturer:
            info.desc().append_child_value('manufacturer', manufacturer)

        return info

    def parse_message(self, message, time_stamp=None):
        message = message[0]
        if message:
            message = json.loads(message)
            if time_stamp:
                message['time_stamp'] = time_stamp
            return message
        else:
            return None


class MarkerStreamThread(BaseMarkerStream, Thread):
    """Marker stream that runs in a separate thread."""

    send_message_queue = None

    def __init__(self, name, content_type, *, source_id=None,
                 manufacturer='pylsltools', **kwargs):
        super().__init__(name, content_type, source_id=source_id,
                         manufacturer=manufacturer, **kwargs)

        # Event to terminate the process.
        self.stop_event = threading.Event()

    def run(self):
        pass

    def stop(self):
        if not self.is_stopped():
            self.stop_event.set()
            if self.send_message_queue:
                # Unblock any waiting threads.
                self.send_message_queue.put('')
            self.cleanup()

    def is_stopped(self):
        return self.stop_event.is_set()
