"""Script to send timestamped control messages over LSL."""

import argparse

from pylsltools import socket_options
from pylsltools.streams import ControlSender


def main():
    """Control stream."""
    parser = argparse.ArgumentParser(
        description="""Create a controller stream for sending timestamped
        messages to other pylsltools streams.""",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    socket_options.add_marker_stream_args(
        parser,
        name_required=True,
        default_content_type="control",
        default_num_channels=1,
    )
    parser.add_argument(
        "--latency", type=float, default=0.5, help="Scheduling latency in seconds."
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Print extra debugging information."
    )

    args = parser.parse_args()
    controller = ControlSender(
        args.name,
        content_type=args.content_type,
        source_id=args.source_id,
        latency=args.latency,
    )
    try:
        controller.start()
        # Block here until controller thread returns.
        controller.join()
    except Exception as exc:
        # Stop controller thread.
        controller.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main.")
        controller.stop()
    print("Main exit.")
