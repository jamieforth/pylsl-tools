"""Control states used for inter-thread/process communication."""

from enum import IntEnum, auto

class ControlStates(IntEnum):
    STOP = auto()
    START = auto()
    PAUSE = auto()
