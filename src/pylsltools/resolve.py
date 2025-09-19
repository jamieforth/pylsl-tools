import argparse
import logging
import asyncio
from .streams.base_stream import StreamInfoBoundData

from pylsl import ContinuousResolver

logger = logging.getLogger(__name__)

_sentinel = None

class StreamResolver:
    """Convenience class wrapping a resolve_stream coroutine."""

    def __init__(
        self,
        prop=None,
        value=None,
        pred=None,
        forget_after=5,
        refresh_rate=2,
        notify_lost=True,
        queue=None,
        stop_event=None,
    ):
        # Initialise queue and stop_event if not provided by the caller.
        if queue is None:
            queue = asyncio.Queue()
        if stop_event is None:
            stop_event = asyncio.Event()

        # Set class attributes.
        self.queue = queue
        self.stop_event = stop_event
        self.args = (
            prop,
            value,
            pred,
            forget_after,
            refresh_rate,
            notify_lost,
        )

    async def get(self):
        return await self.queue.get()

    def task_done(self):
        self.queue.task_done()

    def task(self):
        return resolve_streams(self.queue, self.stop_event, *self.args)


async def resolve_streams(
    queue,
    stop_event,
    prop=None,
    value=None,
    pred=None,
    forget_after=5,
    refresh_rate=2,
    notify_lost=True,
):
    logger.debug("Start ContinuousResolver thread")

    resolver = ContinuousResolver(prop, value, pred, forget_after)

    known_streams = {}

    while not stop_event.is_set():
        # Continuous resolver always returns new StreamInfo objects so we need
        # to check if we've seen each stream before.
        active_streams = resolver.results()
        active_streams = {make_stream_key(info): info for info in active_streams}
        for key, info in active_streams.items():
            if key not in known_streams.keys():
                # Convert to a data class so info can be serialised.
                info_data = StreamInfoBoundData(
                    info.name(),
                    info.type(),
                    info.channel_count(),
                    info.nominal_srate(),
                    info.channel_format(),
                    info.source_id(),
                    info.version(),
                    info.created_at(),
                    info.uid(),
                    info.session_id(),
                    info.hostname()
                )
                known_streams[key] = info_data
                # Send NEW notification to parent thread.
                await queue.put(("NEW", info_data))
        lost_streams = known_streams.keys() - active_streams.keys()
        logger.debug(
            f"Active streams: {len(known_streams)}, Lost streams: {len(lost_streams)}"
        )
        if lost_streams:
            for key in lost_streams:
                if notify_lost:
                    # Send LOST notification to parent thread.
                    await queue.put(("LOST", known_streams[key]))
                # Forget lost streams.
                del known_streams[key]
        await asyncio.sleep(refresh_rate)
    # Put sentinel when coroutine returns.
    await queue.put(_sentinel)


def make_stream_key(stream_info):
    key = stream_info.source_id()
    if key == "":
        key = stream_info.uid()
    return key


def add_cli_args(parser, pred_only=False):
    group = parser.add_argument_group(title="resolve options")
    if not pred_only:
        group.add_argument(
            "--prop", default=None, help="Property name to resolve streams."
        )
        group.add_argument(
            "--value", default=None, help="Property value to resolve streams."
        )
    group.add_argument(
        "--pred", default=None, help="Predicate string to resolve streams."
    )
    group.add_argument(
        "--forget-after",
        type=int,
        default=5,
        help="Time in seconds after which lost streams are forgotten.",
    )
    group.add_argument(
        "--refresh-rate",
        type=int,
        default=2,
        help="Refresh rate in seconds.",
    )
    group.add_argument(
        "--notify-lost",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Notify lost streams.",
    )


async def __handle_resolve_messages(resolver):
    async with asyncio.TaskGroup() as tg:
        tg.create_task(resolver.task())
        tg.create_task(__log_messages(resolver))


async def __log_messages(resolver):
    while True:
        message = await resolver.get()
        if message is _sentinel:
            # Notify resolver sentinel has been handled.
            resolver.task_done()
            break
        logger.info(message)
        # Notify resolver message has been handled.
        resolver.task_done()


def main():
    """Log active streams on the network."""
    parser = argparse.ArgumentParser(
        description="""Log stream activity on the network.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_cli_args(parser)
    parser.add_argument(
        "--verbose", action="store_true", help="Print extra debugging information."
    )
    args = parser.parse_args()

    # Logging
    logging.basicConfig()
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    resolver = StreamResolver(
        args.prop,
        args.value,
        args.pred,
        args.forget_after,
        args.refresh_rate,
        args.notify_lost,
    )
    try:
        with asyncio.Runner() as runner:
            # Block here until runner returns.
            runner.run(__handle_resolve_messages(resolver))
    except KeyboardInterrupt:
        pass
