"""Script to receive timestamped control messages over LSL."""

import os
import argparse
import subprocess

from pylsltools.streams.control_stream import ControlReceiver
from pylsltools import ControlStates


class AntController:
    """Remote control of Ant lslserver."""

    control_states = ControlStates
    state = ControlStates.STOP
    running = True

    def __init__(self, control_name, debug):
        self.controller = ControlReceiver(
            control_name,
            debug=debug)
        self.controller.start()

    def start(self):
        while self.running:
            message = self.controller.get_message()
            if message['state'] != self.state:
                # Update current state.
                self.state = message['state']
                # When START, run ant lslserver.
                if self.state == self.control_states.START:
                    self.launch_ant()
                # When STOP stop this thread.
                if message['state'] == self.control_states.STOP:
                    self.stop()
            print(message)

    def stop(self):
        print('stop')
        self.running = False
        print('kill ant')
        self.task.terminate()
        print('ant terminated')

    def launch_ant(self):
        print('start ant')
        lslexe = "C:\\Users\\neuro\\Desktop\\standalone-eego-edi1-lsl-outlet-v0.0.3\\standalone_eego_edi1_lsl_outlet.exe"
        self.task = subprocess.Popen(
            lslexe,
            cwd="C:\\Users\\neuro\\Desktop\\standalone-eego-edi1-lsl-outlet-v0.0.3",
            creationflags=subprocess.DETACHED_PROCESS)
        print(f'after start ant {self.task.pid}')


def main():
    """Control stream."""
    parser = argparse.ArgumentParser(description="""Create a controller
    stream for sending timestamped messages to other pylsltools
    streams.""")
    parser.add_argument(
        '--control-name',
        default='ant',
        help='Control stream name.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print extra debugging information.')

    args = parser.parse_args()
    controller = AntController(
        args.control_name,
        debug=args.debug)
    try:
        controller.start()
    except Exception as exc:
        # Stop controller thread.
        controller.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        controller.stop()
    print('Main exit.')
