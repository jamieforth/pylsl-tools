"""Base stream class."""

import json
import multiprocessing
import threading
from multiprocessing import Process
from threading import Thread

import numpy as np
from pylsl import IRREGULAR_RATE, StreamInfo
from pylsl.lib import fmt2string


class BaseStream:
    """Base stream initialised with LSL properties."""

    def __init__(
        self,
        name,
        content_type,
        channel_count,
        nominal_srate,
        channel_format,
        *,
        source_id="",
        manufacturer="pylsltools",
        channel_labels=None,
        **kwargs,
    ):
        # Complete initialisation of any Threads or Processes.
        super().__init__(**kwargs)

        # Set class attributes.
        self.name = name
        self.content_type = content_type
        self.channel_count = channel_count
        self.nominal_srate = nominal_srate
        self.channel_format = channel_format
        self.dtype = lslfmt2np(channel_format)
        self.source_id = source_id
        self.manufacturer = manufacturer
        self.channel_labels = check_channel_labels(channel_labels, channel_count)

    def make_stream_info(self):
        """Return a pylsl StreamInfo object.

        StreamInfo objects are not thread safe, so must be created
        in the same thread as each stream.
        """
        info = StreamInfo(
            self.name,
            self.content_type,
            self.channel_count,
            self.nominal_srate,
            self.channel_format,
            self.source_id,
        )
        # Append custom metadata.
        if self.manufacturer:
            info.desc().append_child_value("manufacturer", self.manufacturer)
        if self.channel_labels:
            channels = info.desc().append_child("channels")
            for i in range(self.channel_count):
                ch = channels.append_child("channel")
                ch.append_child_value("label", self.channel_labels[i])
        return info


class BaseStreamThread(BaseStream, Thread):
    # Event to terminate the thread.
    stop_event = None

    # Queue to send messages to parent thread.
    send_message_queue = None

    def __init__(self, *args, send_message_queue=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Event to terminate the thread.
        self.stop_event = threading.Event()

        # Set class attributes.
        self.send_message_queue = send_message_queue

    def is_stopped(self):
        return self.stop_event.is_set()

    def run(self):
        pass

    def stop(self):
        if not self.is_stopped():
            print(f"Terminating thread: {self.name}.")
            self.stop_event.set()

    def cleanup(self):
        pass


class BaseStreamProcess(BaseStream, Process):
    # Event to terminate the process.
    stop_event = None

    # Queue to receive messages from parent thread.
    recv_message_queue = None

    # Queue to send messages to parent thread.
    send_message_queue = None

    def __init__(
        self,
        *args,
        recv_message_queue=None,
        send_message_queue=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # Event to terminate the thread.
        self.stop_event = multiprocessing.Event()

        # Set class attributes.
        self.recv_message_queue = recv_message_queue
        self.send_message_queue = send_message_queue

    def is_stopped(self):
        return self.stop_event.is_set()

    def run(self):
        pass

    def stop(self):
        if not self.is_stopped():
            print(f"Terminating process: {self.name}.")
            self.stop_event.set()
            if self.send_message_queue:
                # Unblock any waiting threads.
                self.send_message_queue.put("")

    def cleanup(self):
        pass


class DataStream(BaseStreamProcess):
    """Data stream that runs in a separate process."""

    def __init__(
        self,
        name,
        content_type,
        channel_count,
        nominal_srate,
        channel_format,
        *,
        source_id="",
        manufacturer="pylsltools",
        channel_labels=None,
        channel_types=None,
        channel_units=None,
        recv_message_queue=None,
        send_message_queue=None,
        **kwargs,
    ):
        # Create default labels.
        if channel_labels is None:
            channel_labels = make_channel_labels(channel_count)

        super().__init__(
            name,
            content_type,
            channel_count,
            nominal_srate,
            channel_format,
            source_id=source_id,
            manufacturer=manufacturer,
            channel_labels=channel_labels,
            recv_message_queue=recv_message_queue,
            send_message_queue=send_message_queue,
            **kwargs,
        )

        # Set class attributes.
        self.channel_types = check_channel_types(channel_types, channel_count)
        self.channel_units = check_channel_units(channel_units, channel_count)

    def make_stream_info(self):
        info = BaseStream.make_stream_info(self)
        if self.channel_labels:
            channels = info.desc().child("channels")
            ch = channels.first_child()
            for i in range(self.channel_count):
                if self.channel_types:
                    ch.append_child_value("type", self.channel_types[i])
                if self.channel_units:
                    ch.append_child_value("unit", self.channel_units[i])
                ch = ch.next_sibling("channel")
        return info


class BaseMarkerStream(BaseStream):
    """Simple marker stream."""

    def __init__(
        self,
        name,
        content_type,
        *,
        channel_count=1,
        source_id="",
        manufacturer="pylsltools",
        channel_labels=None,
        channel_types=None,
        **kwargs,
    ):
        # Create default labels.
        if channel_labels is None:
            channel_labels = make_channel_labels(channel_count)

        # Set marker stream specific properties.
        nominal_srate = IRREGULAR_RATE
        channel_format = "string"

        super().__init__(
            name,
            content_type,
            channel_count=channel_count,
            nominal_srate=nominal_srate,
            channel_format=channel_format,
            source_id=source_id,
            manufacturer=manufacturer,
            channel_labels=channel_labels,
            **kwargs,
        )

        # Set class attributes.
        self.channel_types = check_channel_types(channel_types, channel_count)

    def make_stream_info(self):
        info = BaseStream.make_stream_info(self)
        if self.channel_labels:
            channels = info.desc().child("channels")
            ch = channels.first_child()
            for i in range(self.channel_count):
                if self.channel_types:
                    ch.append_child_value("type", self.channel_types[i])
                ch = ch.next_sibling("channel")
        return info

    def parse_message(self, message, time_stamp=None, channel=0):
        message = message[channel]
        if message:
            message = json.loads(message)
            if time_stamp:
                message["time_stamp"] = time_stamp
            return message
        else:
            return None


class MarkerStreamThread(BaseMarkerStream, BaseStreamThread):
    """Marker stream that runs in a separate thread."""

    def __init__(
        self,
        name,
        content_type,
        **kwargs,
    ):
        super().__init__(
            name,
            content_type,
            **kwargs,
        )


class MarkerStreamProcess(BaseMarkerStream, BaseStreamProcess):
    """Marker stream that runs in a separate process."""

    def __init__(
        self,
        name,
        content_type,
        **kwargs,
    ):
        super().__init__(
            name,
            content_type,
            **kwargs,
        )


# Helper functions


def make_channel_labels(channel_count):
    return [f"ch:{channel_idx:0=2d}" for channel_idx in range(channel_count)]


def check_channel_labels(channel_labels, channel_count):
    if isinstance(channel_labels, list):
        if len(channel_labels) != channel_count:
            print(
                f"{channel_count} channel labels required, {len(channel_labels)} provided."
            )
            channel_labels = None
    return channel_labels


def check_channel_types(channel_types, channel_count):
    if isinstance(channel_types, list):
        if len(channel_types) != channel_count:
            print(
                f"{channel_count} channel types required, {len(channel_types)} provided."
            )
    if isinstance(channel_types, str):
        channel_types = [channel_types] * channel_count
    return channel_types


def check_channel_units(channel_units, channel_count):
    if isinstance(channel_units, list):
        if len(channel_units) != channel_count:
            print(
                f"{channel_count} channel units required, {len(channel_units)} provided."
            )
            channel_units = None
    if isinstance(channel_units, str):
        channel_units = [channel_units] * channel_count
    return channel_units


def lslfmt2np(channel_format):
    if isinstance(channel_format, int):
        channel_format = fmt2string[channel_format]
    lslfmt_map = {
        "int8": np.int8,
        "int16": np.int16,
        "int32": np.int32,
        "int64": np.int64,
        "float32": np.float32,
        "double64": np.float64,
        "string": str,
    }
    return lslfmt_map[channel_format]
