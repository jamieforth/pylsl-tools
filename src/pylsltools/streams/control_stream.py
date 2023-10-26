from pylsl import StreamOutlet, local_clock
from pylsltools.streams import BaseStream
import asyncio


class ControlServer(BaseStream):

    def __init__(self, control_name):

        # super().__init__(None, name, channel_count, content_type,
        #                  channel_format, sample_rate, source_id)

        self.control_name = control_name

    def start(self):
        asyncio.run(self.run())

    async def run(self):
        await asyncio.gather(self.count(), self.count(), self.count())

    async def count(self):
        print(1)
        await asyncio.sleep(1)
        print(2)

class ControlClient(BaseStream):

    def __init__(self, control_name, device):

        # super().__init__(None, name, channel_count, content_type,
        #                  channel_format, sample_rate, source_id)

        self.control_name = control_name
        self.device = device

    def start(self):
        asyncio.run(self.run())

    async def run(self):
        await asyncio.gather(self.count(), self.count(), self.count())

    async def count(self):
        print(1)
        await asyncio.sleep(1)
        print(2)
