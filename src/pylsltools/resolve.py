import argparse
import logging
from queue import Queue
from threading import Event, Thread
from typing import NamedTuple

from pylsl import ContinuousResolver

logger = logging.getLogger(__name__)


class StreamInfoTuple(NamedTuple):
    """Stream information as a serialisable tuple."""

    name: str
    content_type: str
    channel_count: int
    nominal_srate: float
    channel_format: int
    source_id: str


def stream_notifier(
    queue,
    stop_event,
    prop=None,
    value=None,
    pred=None,
    forget_after=5,
    refresh_rate=2,
    notify_lost=True,
):
    resolver = ContinuousResolver(prop, value, pred, forget_after)

    known_streams = {}

    while not stop_event.is_set():
        # Continuous resolver always returns new StreamInfo objects so we need
        # to check if we've seen each stream before.
        active_streams = resolver.results()
        active_streams = {make_stream_key(info): info for info in active_streams}
        for key, info in active_streams.items():
            if key not in known_streams.keys():
                info_tuple = StreamInfoTuple(
                    info.name(),
                    info.type(),
                    info.channel_count(),
                    info.nominal_srate(),
                    info.channel_format(),
                    info.source_id(),
                )
                known_streams[key] = info_tuple
                queue.put(("NEW", info_tuple))
        lost_streams = known_streams.keys() - active_streams.keys()
        logger.debug(
            f"Active streams: {len(known_streams)}, Lost streams: {len(lost_streams)}"
        )
        if lost_streams:
            for key in lost_streams:
                queue.put(("LOST", known_streams[key]))
                del known_streams[key]
        stop_event.wait(refresh_rate)


def make_stream_key(stream_info):
    key = stream_info.source_id()
    if key == "":
        key = stream_info.uid()
    return key


def main():
    """Log active streams on the network."""

    parser = argparse.ArgumentParser(
        description="""Log active streams on the network."""
    )
    parser.add_argument(
        "--prop", default=None, help="Property name to resolve streams."
    )
    parser.add_argument(
        "--value", default=None, help="Property value to resolve streams."
    )
    parser.add_argument(
        "--pred", default=None, help="Predicate string to resolve streams."
    )
    parser.add_argument(
        "--forget-after",
        type=int,
        default=5,
        help="Time in seconds after which lost streams are forgotten.",
    )
    parser.add_argument(
        "--refresh-rate",
        type=int,
        default=2,
        help="Refresh rate in seconds.",
    )
    parser.add_argument(
        "--notify-lost",
        action="store_true",
        help="Notify lost streams.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print extra debugging information."
    )

    args = parser.parse_args()

    logging.basicConfig()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    queue = Queue()
    stop_event = Event()
    thread = Thread(
        target=stream_notifier,
        args=(
            queue,
            stop_event,
            args.prop,
            args.value,
            args.pred,
            args.forget_after,
            args.refresh_rate,
            args.notify_lost,
        ),
    )
    try:
        thread.start()
        while True:
            info = queue.get()
            logger.info(f"Message: {info}")
    except KeyboardInterrupt:
        stop_event.set()
        thread.join()
