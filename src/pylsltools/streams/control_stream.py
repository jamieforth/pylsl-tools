
import json
import multiprocessing
import platform
import threading
import time
from enum import IntEnum, auto
from multiprocessing import Condition, Value

from pylsl import (IRREGULAR_RATE, LostError, StreamInfo, StreamInlet,
                   StreamOutlet, local_clock, proc_ALL, resolve_bypred)
from pylsltools.streams import MarkerStream


class States(IntEnum):
    STOP = auto()
    START = auto()
    QUIT = auto()


class ControlSender(MarkerStream):
    """Control stream sending thread."""

    states = States

    def __init__(self, name, *, content_type='control', source_id=None,
                 latency=0.5, manufacturer='pylsltools', debug=False, **kwargs):

        channel_count = 1
        nominal_srate = IRREGULAR_RATE
        channel_format = 'string'
        # Use host name to identify source. If stream is interrupted due
        # to network outage or the controller is restarted receivers
        # should be able to recover.
        if not source_id:
            source_id = platform.node()

        info = self.make_stream_info(name, content_type, channel_count,
                                     nominal_srate, channel_format, source_id,
                                     manufacturer)

        super().__init__(info, **kwargs)

        # Set class attributes.
        self.name = name
        self.latency = latency
        self.debug = debug

    def make_stream_info(self, name, content_type, channel_count,
                         nominal_srate, channel_format, source_id,
                         manufacturer):
        info = StreamInfo(name,
                          content_type,
                          channel_count,
                          nominal_srate,
                          channel_format,
                          source_id)
        return info

    def run(self):
        self.outlet = StreamOutlet(self.info, chunk_size=1)
        try:
            while not self.is_stopped():
                cmd = input('Enter a command: start, stop, quit.\n')
                if cmd == 'stop':
                    self.outlet.push_sample([json.dumps(
                        {'cmd': self.states.STOP}
                    )], local_clock() + self.latency)
                elif cmd == 'start':
                    self.outlet.push_sample([json.dumps(
                        {'cmd': self.states.START}
                    )], local_clock() + self.latency)
                elif cmd == 'quit':
                    self.stop()
                else:
                    print(f'Undefined command: {cmd}')
        except Exception as exc:
            self.stop()
            raise exc
        print(f'Ended: {self.name}.')

    def stop(self):
        super().stop()
        # Send quit command here in case main thread called stop or
        # exception raised.
        self.outlet.push_sample([json.dumps(
            {'cmd': self.states.QUIT}
        )], local_clock() + self.latency)
        # Pause thread before destroying outlet to try and avoid any
        # receivers throwing a LostError before receiving the quit
        # message. Not that it really matters as receivers will
        # gracefully quit when a stream disconnects - but is there a
        # better way to handle this by waiting for any pending messages
        # to be sent?
        time.sleep(1)


class ControlReceiver(MarkerStream):
    """Control stream receiver thread."""

    states = States

    def __init__(self, name, **kwargs):
        super().__init__(None, **kwargs)

        # Set class attributes.
        self.name = name
        self.__timestamp = Value('f', 0.0)
        self.__state = Value('i', self.states.STOP)
        self.condition = Condition()

    def run(self):
        print('Waiting for control stream.')
        print(multiprocessing.current_process(), threading.current_thread())
        sender_info = resolve_bypred(f"name='{self.name}'")[0]
        self.set_info(sender_info)

        inlet = StreamInlet(self.info, max_buflen=1, max_chunklen=1,
                            recover=False, processing_flags=proc_ALL)
        try:
            while not self.is_stopped():
                try:
                    message, timestamp = inlet.pull_sample()
                    print(f'Control {self.name}, timestamp: {timestamp}, message: {message}')
                except LostError as exc:
                    self.stop()
                    print(f'{self.name}: {exc}')
                    return
                # Handle message.
                message = self.parse_message(message)
                if message:
                    # Only notify on state changes.
                    if message['cmd'] != self.state():
                        # Update shared memory and notify all waiting
                        # processes.
                        self.__timestamp.value = timestamp
                        self.__state.value = message['cmd']
                        with self.condition:
                            self.condition.notify_all()
                        if self.state() == self.states.QUIT:
                            self.stop()
        except Exception as exc:
            self.stop()
            raise exc

    def stop(self):
        super().stop()
        # Ensure all processes are notified even if this thread exists
        # not in response to receiving a quit command.
        self.__state.value = self.states.QUIT
        with self.condition:
            self.condition.notify_all()

    def timestamp(self):
        return self.__timestamp.value

    def state(self):
        return self.__state.value

    def parse_message(self, message):
        message = message[0]
        if message:
            return json.loads(message)
        else:
            return None
