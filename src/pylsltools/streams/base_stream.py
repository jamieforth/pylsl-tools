"""Base stream class."""

from pylsl import StreamInfo, StreamOutlet, local_clock


class BaseStream:

    stream_id = None
    name = None
    channel_count = None
    content_type = None
    sample_rate = None
    source_id = None

    def __init__(self, stream_id, name, channel_count, content_type,
                 channel_format, sample_rate, source_id):
        self.stream_id = stream_id
        self.name = name
        self.channel_count = channel_count
        self.content_type = content_type
        self.channel_format = channel_format
        self.sample_rate = sample_rate
        self.source_id = source_id

    def start(self):
        pass

    def stop(self):
        pass


class BaseDataStream(BaseStream):

    # Channel metadata
    channel_labels = None
    channel_types = None
    channel_units = None

    def __init__(self, stream_id, name, channel_count, content_type,
                 channel_format, sample_rate, source_id, channel_labels=None,
                 channel_types='misc', channel_units=None):

        super().__init__(stream_id, name, channel_count, content_type,
                         channel_format, sample_rate, source_id,)

        # Channel labels
        if isinstance(channel_labels, list):
            if len(channel_labels) == channel_count:
                self.channel_labels = channel_labels
            else:
                print('{channel_count} channel labels required, {len(channel_labels)} provided.')
                self.channel_labels = self.make_channel_labels()
        else:
            self.channel_labels = self.make_channel_labels()

        # Channel types
        if isinstance(channel_types, list):
            if len(channel_types) == channel_count:
                self.channel_types = channel_types
            else:
                print('{channel_count} channel types required, {len(channel_types)} provided.')
                self.channel_types = 'misc'
        if isinstance(channel_types, str):
            self.channel_types = [channel_types] * channel_count

        # Channel units
        if isinstance(channel_units, list):
            if len(channel_units) == channel_count:
                self.channel_units = channel_units
            else:
                print('{channel_count} channel units required, {len(channel_units)} provided.')
                self.channel_units = None
        if isinstance(channel_units, str):
            self.channel_units = [channel_units] * channel_count

    def make_stream_info(self):
        info = StreamInfo(name=self.name, type=self.content_type,
                          channel_count=self.channel_count,
                          nominal_srate=self.sample_rate,
                          channel_format=self.channel_format,
                          source_id=self.source_id)
        # Append custom metadata.
        info.desc().append_child_value('manufacturer', 'pylsltools')
        channels = info.desc().append_child('channels')
        for i in range(self.channel_count):
            ch = channels.append_child('channel')
            ch.append_child_value('label', self.channel_labels[i])
            ch.append_child_value('type', self.channel_types[i])
            if self.channel_units:
                ch.append_child_value('unit', self.channel_units[i])
        return info

    def make_channel_labels(self):
        return [f'ch:{channel_idx:0=2d}' for channel_idx in
                range(self.channel_count)]
