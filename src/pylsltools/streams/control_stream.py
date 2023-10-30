from pylsl import StreamOutlet, local_clock
from pylsltools.streams import BaseStream


class ControlSender(BaseStream):

    def __init__(self, control_name):

        self.control_name = control_name

    def start(self):
        pass

    def run(self):
        pass


class ControlReceiver(BaseStream):

    def __init__(self, control_name, device):

        self.control_name = control_name
        self.device = device

    def start(self):
        pass

    def run(self):
        pass
