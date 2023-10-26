"""Base stream sender class."""

from pylsl import StreamInfo, StreamOutlet, local_clock


class LSLSender:

    info = None

    def __init__(self, name, content_type, channel_count, nominal_srate,
                 channel_format, source_id, desc=None,
                 manufacturer='pylsltools', channel_labels=None,
                 channel_types='misc', channel_units=None):
        if desc:
            self.info = self.make_stream_info_with_desc(name, content_type,
                                                        channel_count,
                                                        nominal_srate,
                                                        channel_format,
                                                        source_id, desc)
        else:
            # Channel labels
            if isinstance(channel_labels, list):
                if len(channel_labels) == channel_count:
                    pass
                else:
                    print('{channel_count} channel labels required, {len(channel_labels)} provided.')
                    channel_labels = self.make_channel_labels(channel_count)
            else:
                channel_labels = self.make_channel_labels(channel_count)

            # Channel types
            if isinstance(channel_types, list):
                if len(channel_types) == channel_count:
                    pass
                else:
                    print('{channel_count} channel types required, {len(channel_types)} provided.')
                    channel_types = 'misc'
            if isinstance(channel_types, str):
                channel_types = [channel_types] * channel_count

            # Channel units
            if isinstance(channel_units, list):
                if len(channel_units) == channel_count:
                    pass
                else:
                    print('{channel_count} channel units required, {len(channel_units)} provided.')
                    channel_units = None
            if isinstance(channel_units, str):
                channel_units = [channel_units] * channel_count

            self.info = self.make_stream_info(name, content_type, channel_count,
                                              nominal_srate, channel_format,
                                              source_id, manufacturer,
                                              channel_labels, channel_types,
                                              channel_units)

    def make_channel_labels(self, channel_count):
        return [f'ch:{channel_idx:0=2d}' for channel_idx in
                range(channel_count)]


    # def make_stream_info_with_desc(self, name, content_type, channel_count,
    #                                nominal_srate, channel_format, source_id,
    #                                desc):
    #     info = StreamInfo(name,
    #                       content_type,
    #                       channel_count,
    #                       nominal_srate,
    #                       channel_format,
    #                       source_id)
    #     #print(info.desc().append_copy(desc))
    #     #info.desc().parent().next_sibling().append_copy(desc)
    #     # FIXME: How to add desc metadata?
    #     print('desc', info.as_xml())
    #     return info

    def make_stream_info(self, name, content_type, channel_count,
                         nominal_srate, channel_format, source_id,
                         manufacturer, channel_labels, channel_types,
                         channel_units):
        info = StreamInfo(name,
                          content_type,
                          channel_count,
                          nominal_srate,
                          channel_format,
                          source_id)
        # Append custom metadata.
        if manufacturer:
            info.desc().append_child_value('manufacturer', manufacturer)
        channels = info.desc().append_child('channels')
        for i in range(channel_count):
            ch = channels.append_child('channel')
            ch.append_child_value('label', channel_labels[i])
            ch.append_child_value('type', channel_types[i])
            if channel_units:
                ch.append_child_value('unit', channel_units[i])
        return info

    def create_outlet(self, chunk_size, max_buffered):
        self.outlet = StreamOutlet(self.info, chunk_size=chunk_size,
                                   max_buffered=max_buffered)

    def push_sample(self, x, timestamp=0.0, pushthrough=True):
        self.outlet.push_sample(x, timestamp, pushthrough)

    def push_chunk(self, x, timestamp=0.0, pushthrough=True):
        self.outlet.push_chunk(x, timestamp, pushthrough)
