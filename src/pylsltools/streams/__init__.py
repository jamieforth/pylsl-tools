import importlib.util

from .base_stream import (
    BaseMarkerStream,
    BaseStream,
    BaseStreamProcess,
    BaseStreamThread,
    ChannelInfoMixin,
    DataStream,
    DescInfoMixin,
    LslInletOptions,
    LslOutletOptions,
    MarkerStreamProcess,
    MarkerStreamThread,
    StreamInfoBoundData,
    StreamInfoData,
)
from .control_receiver import ControlReceiver

if importlib.util.find_spec("aioconsole") is not None:
    from .control_sender import ControlSender
else:
    # Handle the case where the module is not available
    print("ControlSender not available: aioconsole not installed.")

from .generator_stream import GeneratorStream
from .monitor_stream import MonitorReceiver, MonitorSender
from .osc_relay_stream import OscRelayStream
from .relay_stream import RelayStream
from .test_stream import TestDataStream, TestMarkerStream
