import argparse
import asyncio
import json
import sys
import time
from threading import Thread, Event

from pylsl import LostError, StreamOutlet, local_clock, proc_ALL
from pythonosc import osc_bundle_builder, osc_message_builder, udp_client

from pylsltools import ControlStates
from pylsltools.streams import ControlSender


class OscController(ControlSender):

    def __init__(self, name, latency=0.5, *, content_type, source_id, sc_ip,
                 sclang_port, manufacturer='pylsltools', debug=False, **kwargs):
        super().__init__(name,
                         latency,
                         content_type=content_type,
                         source_id=source_id,
                         manufacturer=manufacturer,
                         debug=debug)
        self.sc_ip = sc_ip
        self.sclang_port = sclang_port
        self.stop_event = Event()

    def counter(self, start_time, sf, stop_event, latency):
        logical_time = start_time
        elapsed_time = 0 - latency
        delta = 1 / sf
        while not stop_event.is_set():
            elapsed_time = logical_time - start_time
            print(elapsed_time)
            self.outlet.push_sample([json.dumps(
                {'seconds': logical_time}
            )])
            logical_time = logical_time + delta
            delay = logical_time - (local_clock() + latency)
            if delay > 0:
                time.sleep(delay)

    def run(self):
        info = self.make_stream_info(self.name, self.content_type,
                                     self.source_id, self.manufacturer)

        self.outlet = StreamOutlet(info, chunk_size=1)
        sclang = udp_client.SimpleUDPClient(self.sc_ip, self.sclang_port)
        try:
            while not self.is_stopped():
                state = input('Enter a command: start, pause, stop.\n')
                if state == 'start':
                    unixtime = time.time()
                    lsl_time = local_clock()
                    self.outlet.push_sample([json.dumps(
                        {'state': self.control_states.START}
                    )], lsl_time + self.latency)
                    bundle = osc_bundle_builder.OscBundleBuilder(
                        unixtime + self.latency)
                    msg = osc_message_builder.OscMessageBuilder(address=f'/lsl/record/start')
                    bundle.add_content(msg.build())
                    sclang.send(bundle.build())
                    self.counter_thread = Thread(target=self.counter, args=(
                        lsl_time, 1/5, self.stop_event, self.latency))
                    self.counter_thread.start()
                elif state == 'pause':
                    unixtime = time.time()
                    self.outlet.push_sample([json.dumps(
                        {'state': self.control_states.PAUSE}
                    )])
                    bundle = osc_bundle_builder.OscBundleBuilder(
                        unixtime + self.latency)
                    msg = osc_message_builder.OscMessageBuilder(address=f'/lsl/record/pause')
                    bundle.add_content(msg.build())
                    sclang.send(bundle.build())

                elif state == 'stop':
                    unixtime = time.time()
                    bundle = osc_bundle_builder.OscBundleBuilder(
                        unixtime + self.latency)
                    msg = osc_message_builder.OscMessageBuilder(address=f'/lsl/record/stop')
                    bundle.add_content(msg.build())
                    sclang.send(bundle.build())
                    self.stop_event.set()
                    self.stop()
                else:
                    print(f'Undefined command: {state}')
        except Exception as exc:
            self.stop()
            raise exc
        print(f'Ended: {self.name}.')


def main():
    """OSC control stream."""
    parser = argparse.ArgumentParser(description="""Create a controller
    stream for sending timestamped messages to other pylsltools
    streams.""")
    parser.add_argument(
        '--name',
        default='audio',
        help='Name of the control stream.')
    parser.add_argument(
        '--content-type',
        default='marker',
        help='Content type for marker stream.')
    parser.add_argument(
        '--source-id',
        default='',
        help='Unique identifier for stream source.')
    parser.add_argument(
        "--sc-ip",
        default="127.0.0.1",
        help="The ip of the OSC server")
    parser.add_argument(
        "--sclang-port",
        type=int,
        default=57120,
        help="The port the sclang is listening on")
    parser.add_argument(
        '--latency',
        type=float,
        default=0.5,
        help='Scheduling latency in seconds.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print extra debugging information.')

    args = parser.parse_args()
    controller = OscController(args.name,
                               content_type=args.content_type,
                               source_id=args.source_id,
                               latency=args.latency,
                               sc_ip=args.sc_ip,
                               sclang_port=args.sclang_port,
                               debug=args.debug)
    try:
        controller.start()
        # Block here until controller thread returns.
        controller.join()
    except Exception as exc:
        # Stop controller thread.
        controller.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        controller.stop()
    print('Main exit.')
