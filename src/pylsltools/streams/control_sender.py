import asyncio
import json
import platform
import queue

from aioconsole import ainput
from pylsl import (StreamInlet, StreamOutlet, local_clock, proc_ALL,
                   resolve_bypred)
from pylsl.util import LostError
from pylsltools import ControlStates
from pylsltools.streams import MarkerStreamThread


class ControlSender(MarkerStreamThread):
    """Control stream sending thread."""

    control_states = ControlStates

    def __init__(self, name, latency=0.5, *, content_type='control',
                 source_id='', manufacturer='pylsltools', debug=False,
                 **kwargs):
        # Use host name to identify source if unspecified. If stream is
        # interrupted due to network outage or the controller is
        # restarted receivers should be able to recover.
        if not source_id:
            source_id = platform.node()

        super().__init__(name, content_type, source_id=source_id,
                         manufacturer=manufacturer, **kwargs)

        # Set class attributes.
        self.latency = latency
        self.debug = debug

    def run(self):
        info = self.make_stream_info()

        self.outlet = StreamOutlet(info, chunk_size=1)

        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.cli())

    async def cli(self):
        """REPL interface for sending control messages."""
        while not self.is_stopped():
            state = await ainput('Enter a command: start, pause, stop.\n')
            if state == 'start':
                self.outlet.push_sample([json.dumps(
                    {'state': self.control_states.START}
                )], local_clock() + self.latency)
            elif state == 'pause':
                self.outlet.push_sample([json.dumps(
                    {'state': self.control_states.PAUSE}
                )], local_clock() + self.latency)
            elif state == 'stop':
                self.outlet.push_sample([json.dumps(
                    {'state': self.control_states.STOP}
                )], local_clock() + self.latency)
                self.stop()
            else:
                print(f'Undefined command: {state}')


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
