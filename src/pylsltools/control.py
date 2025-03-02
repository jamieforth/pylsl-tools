"""Script to send timestamped control messages over LSL."""

import argparse
from pylsltools.streams import ControlSender


def main():
    """Control stream."""
    parser = argparse.ArgumentParser(
        description="""Create a controller stream for sending timestamped
    messages to other pylsltools streams."""
    )
    parser.add_argument("--name", required=True, help="Name of the control stream.")
    parser.add_argument(
        "--content-type", default="control", help="Content type for marker stream."
    )
    parser.add_argument(
        "--source-id", default="", help="Unique identifier for stream source."
    )
    parser.add_argument(
        "--latency", type=float, default=0.5, help="Scheduling latency in seconds."
    )
    parser.add_argument(
        "--debug", action="store_true", help="Print extra debugging information."
    )

    args = parser.parse_args()
    controller = ControlSender(
        args.name,
        content_type=args.content_type,
        source_id=args.source_id,
        latency=args.latency,
        debug=args.debug,
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
