"""Base stream class."""

from multiprocessing import Event, Process

from pylsl import StreamInfo, StreamOutlet, local_clock


class BaseStream(Process):

    def __init__(self, info, **kwargs):
        # macOX and Windows default
        # multiprocessing.set_start_method('spawn')
        print('BaseStream', info, kwargs)
        super().__init__(**kwargs)
        self.info = info
        print(info.as_xml())
        print(kwargs)
        # Event to terminate the process.
        self.stop = Event()

    def run(self):
        pass


class DataStream(BaseStream):

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
