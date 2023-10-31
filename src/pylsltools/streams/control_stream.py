from threading import Thread, Event

from pylsl import StreamInlet, StreamOutlet, local_clock, resolve_bypred, LostError
from pylsltools.streams import MarkerStream


class ControlSender(MarkerStream):

    def __init__(self, name, *, content_type='control', source_id=None,
                 latency=None, debug=False, **kwargs):

        super().__init__(name, content_type=content_type, source_id=source_id,
                         **kwargs)

        self.latency = latency
        self.debug = debug

    def run(self):
        self.outlet = StreamOutlet(self.info, chunk_size=1)
        try:
            while not self.is_stopped():
                cmd = input('Enter a command: start, stop, quit.\n')
                if cmd in ['start', 'stop']:
                    now = local_clock()
                    self.outlet.push_sample(
                        [f'cmd:{cmd}, timestamp:{now}, latency: {self.latency}'])
                elif cmd == 'quit':
                    self.stop()
                else:
                    print(f'Undefined command: {cmd}')

        except KeyboardInterrupt:
            print(f'Stopping: {self.name}')
            self.stop()
        print(f'Ended: {self.name}.')


class ControlReceiver():

    def __init__(self, name):

        self.name = name
        self.stop_event = Event()

    def start(self):
        print('Waiting for control stream.')
        self.sender_info = resolve_bypred(f"name='{self.name}'")[0]

        self.thread = Thread(target=self.run)
        self.thread.start()
        # Block main thread until resolver thread returns.
        self.thread.join()

    def stop(self):
        self.stop_event.set()

    def is_stopped(self):
        return self.stop_event.is_set()

    def run(self):
        inlet = StreamInlet(self.sender_info, max_chunklen=1)
        try:
            while not self.is_stopped():
                message = inlet.pull_sample()
                print(message)
        except LostError as exc:
            self.stop()
            # FIXME: Send message back to main thread.
            print(f'{self.name}: {exc}')
            return
        except Exception as exc:
            self.stop()
            raise exc
