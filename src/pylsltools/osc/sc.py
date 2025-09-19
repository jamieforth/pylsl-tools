from typing import NamedTuple

class ScArgs(NamedTuple):
    """SuperCollider argument."""

    ip_addr: str
    sclang_port: int
    scsynth_port: int
    latency: int


class SuperCollider():
    def __init__(
        self,
        sclang_ip="127.0.0.1",
        sclang_port=57120,
        scsynth_ip="127.0.0.1",
        scsynth_port=57110,
        latency=0,
    ):
        self.sclang_ip = sclang_ip
        self.sclang_port = sclang_port
        self.scsynth_ip = scsynth_ip
        self.scsynth_port = scsynth_port
        self.latency = latency


def add_cli_args(parser):
    osc_group = parser.add_argument_group("supercollider options")
    osc_group.add_argument(
        "--sclang-ip", default="127.0.0.1", help="The IP address of sclang."
    )
    osc_group.add_argument(
        "--sclang-port",
        type=int,
        default=57120,
        help="The port the sclang is listening on",
    )
    osc_group.add_argument(
        "--scsynth-ip", default="127.0.0.1", help="The IP address of scsynth."
    )
    osc_group.add_argument(
        "--scsynth-port",
        type=int,
        default=57110,
        help="The port the scsynth is listening on",
    )
    osc_group.add_argument(
        "--osc-latency", type=float, default=0.0, help="Scheduling latency in seconds."
    )
