"""Base stream class."""

import sys
import json
import multiprocessing
import threading
if 'linux' in sys.platform:
    from multiprocessing import Process
from threading import Thread

from pylsl import IRREGULAR_RATE, StreamInfo


class BaseStream():
    """Base stream initialised from an LSL info object."""

    info = None

    def __init__(self, info, **kwargs):
        super().__init__(**kwargs)
        if info:
            self.set_info(info)

    def set_info(self, info):
        self.info = info
        #print(info.as_xml())

if 'linux' in sys.platform:
    dataStreamSuperClass = Process
elif 'win32' in sys.platform:
    dataStreamSuperClass = Thread

class DataStream(BaseStream, dataStreamSuperClass):
    """Data stream that runs in a separate process."""

    def __init__(self, name, content_type, channel_count, nominal_srate,
                 channel_format, *, source_id=None, manufacturer='pylsltools',
                 channel_labels=None, channel_types=None, channel_units=None,
                 **kwargs):
        print('DataStream', name, content_type, channel_count, nominal_srate,
              channel_format, source_id, manufacturer, channel_labels,
              channel_types, channel_units, kwargs)
        info = self.make_stream_info(name, content_type, channel_count,
                                     nominal_srate, channel_format, source_id,
                                     manufacturer, channel_labels,
                                     channel_types, channel_units)
        super().__init__(info, name=name, **kwargs)

        # Event to terminate the process.
        self.stop_event = multiprocessing.Event()

    def run(self):
        pass

    def stop(self):
        self.stop_event.set()

    def is_stopped(self):
        return self.stop_event.is_set()

    def make_stream_info(self, name, content_type, channel_count,
                         nominal_srate, channel_format, source_id,
                         manufacturer, channel_labels=None, channel_types=None,
                         channel_units=None):
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

    def __init__(self, info, **kwargs):

        super().__init__(info, **kwargs)

    def make_stream_info(self, name, content_type, source_id, manufacturer):
        channel_count = 1
        nominal_srate = IRREGULAR_RATE
        channel_format = 'string'

        info = StreamInfo(name,
                          content_type,
                          channel_count,
                          nominal_srate,
                          channel_format,
                          source_id)
        return info

    def parse_message(self, message):
        message = message[0]
        if message:
            return json.loads(message)
        else:
            return None


class MarkerStreamThread(BaseMarkerStream, Thread):
    """Marker stream that runs in a separate thread."""

    def __init__(self, info, **kwargs):

        super().__init__(info, **kwargs)

        # Event to terminate the process.
        self.stop_event = threading.Event()

    def run(self):
        pass

    def stop(self):
        self.stop_event.set()

    def is_stopped(self):
        return self.stop_event.is_set()
