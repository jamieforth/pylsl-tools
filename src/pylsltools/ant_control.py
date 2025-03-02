"""Script to receive timestamped control messages over LSL."""

import io
import argparse
import asyncio
import subprocess
import sys
import platform

from pylsltools import ControlStates
from pylsltools.streams import ControlReceiver, MonitorSender

from .nl_mappings import hostname_device_mapper


class AntController:
    """Remote control of Ant lslserver."""

    control_states = ControlStates
    controlReceiver = None
    state = ControlStates.STOP
    # running = True
    lsl_server_task = None

    def __init__(self, control_name, debug):
        self.debug = debug
        self.controlReceiver = ControlReceiver(control_name, debug=debug)
        self.monitorSender = MonitorSender(
            self.make_monitor_name(), content_type="monitor", debug=self.debug
        )

    def make_monitor_name(self):
        hostname = platform.node()
        if hostname in hostname_device_mapper:
            hostname = hostname_device_mapper[hostname]

        return "_monitor_" + hostname

    def start(self):
        # Start receiver.
        self.controlReceiver.start()
        # Use asyncio to handle asynchronous messages in the main thread.
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(self.run_tasks())
        print("End start")

    async def run_tasks(self):
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.handle_control_messages())
            tg.create_task(self.handle_monitor_messages())

    async def handle_monitor_messages(self):
        while self.running:
            if self.debug:
                print("monitor task")
            line = ""
            if self.lsl_server_task:
                line = self.lsl_server_task.stdout.readline()
            if self.debug:
                print(line)
            await asyncio.sleep(0.1)
            self.monitorSender.send([line.rstrip()])

    async def handle_control_messages(self):
        self.running = True
        try:
            while self.running:
                # Loop here waiting for messages.
                # Block on message queue.
                if self.debug:
                    print("blocking receive")
                message = self.controlReceiver.get_message(0.1)
                if self.debug:
                    print(self.__class__, message)

                if message and message["state"] != self.state:
                    # Update current state.
                    self.state = message["state"]
                    # When START, run ant lslserver.
                    if self.state == self.control_states.START:
                        self.start_ant()
                    if self.state == self.control_states.PAUSE:
                        self.stop_ant()
                    # When STOP stop this thread.
                    if message["state"] == self.control_states.STOP:
                        self.stop()
                await asyncio.sleep(0.1)
        finally:
            if self.debug:
                print("End controller messaging.")
            self.stop()

    def stop(self):
        print(f"Stop: {self.__class__}")
        self.running = False
        # self.messaging_task.cancel()
        self.controlReceiver.stop()
        self.stop_ant()
        # super().stop()

    def start_ant(self):
        print("start ant")
        if "win32" in sys.platform:
            lslexe = "C:\\Users\\neuro\\Desktop\\standalone-eego-edi1-lsl-outlet-v0.0.3\\standalone_eego_edi1_lsl_outlet.exe"
            self.lsl_server_task = subprocess.Popen(
                lslexe,
                cwd="C:\\Users\\neuro\\Desktop\\standalone-eego-edi1-lsl-outlet-v0.0.3",
                stdout=subprocess.PIPE,
                text=True,
            )
            # creationflags=subprocess.DETACHED_PROCESS)
            print(f"Ant PID: {self.lsl_server_task.pid}")
        else:
            self.lsl_server_task = subprocess.Popen(
                "/home/jamie/.local/bin/counter-test.sh",
                stdout=subprocess.PIPE,
                bufsize=1,
                text=True,
            )
            print(f"Ant PID: {self.lsl_server_task.pid}")

    def stop_ant(self):
        if self.lsl_server_task:
            print("Killing ant.")
            self.lsl_server_task.terminate()
            print("Ant terminated.")
        else:
            print("Ant not running.")


def main():
    """Control stream."""
    parser = argparse.ArgumentParser(
        description="""Create a controller
    stream for sending timestamped messages to other pylsltools
    streams."""
    )
    parser.add_argument("--control-name", default="ant", help="Control stream name.")
    parser.add_argument(
        "--debug", action="store_true", help="Print extra debugging information."
    )

    args = parser.parse_args()
    controller = AntController(args.control_name, debug=args.debug)
    try:
        controller.start()
        # controller.join()
    except Exception as exc:
        # Stop controller thread.
        controller.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main.")
        controller.stop()
    print("Main exit.")
