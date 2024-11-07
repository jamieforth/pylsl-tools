import queue

from pylsl import (LostError, StreamInlet, StreamOutlet, local_clock, proc_ALL,
                   resolve_bypred)
from pylsltools import ControlStates
from pylsltools.streams import MarkerStreamThread


class ControlReceiver(MarkerStreamThread):
    """Control stream receiver thread."""

    control_states = ControlStates
    inlet = None
    messaging_task = None

    def __init__(self, name, *, content_type='control',
                 debug=False, **kwargs):
        super().__init__(name, content_type, **kwargs)

        # Set class attributes.
        self.time_stamp = 0.0
        self.state = self.control_states.STOP
        self.send_message_queue = queue.SimpleQueue()
        self.debug = debug
        self.inlet = None
        self.clock_offset = None

    def run(self):
        print('Waiting for control stream.')

        sender_info = None
        while not sender_info and not self.is_stopped():
            # Resolve must run in the same thread as the inlet.
            sender_info = resolve_bypred(f"name='{self.name}'", timeout=0.5)
        if not sender_info:
            return
        sender_info = sender_info[0]

        print(f'Found control stream: {sender_info.name()}.')

        self.inlet = StreamInlet(sender_info, max_buflen=1, max_chunklen=1,
                                 recover=False, processing_flags=proc_ALL)
        try:
            while not self.is_stopped():
                # Blocking.
                message, time_stamp = self.inlet.pull_sample(1)
                if message:
                    print(f'Control {self.name}, time_stamp: {time_stamp}, message: {message}')
                    # Handle message.
                    message = self.parse_message(message, time_stamp)
                    # Only notify on state changes.
                    if message and message['state'] != self.state:
                        # Update current state.
                        self.state = message['state']
                        self.time_stamp = time_stamp
                        self.send_message_queue.put(message)
                        # When STOP stop this thread.
                        if message['state'] == self.control_states.STOP:
                            self.stop()
        except LostError as exc:
            print(f'{self.name}: {exc}')
        finally:
            self.stop()
            self.cleanup()
            print(f'Ended: {self.name}.')

    def cleanup(self):
        if self.inlet:
            self.inlet.close_stream()

    def get_message(self, timeout=0.2):
        try:
            message = self.send_message_queue.get(timeout=timeout)
            return message
        except queue.Empty:
            pass
