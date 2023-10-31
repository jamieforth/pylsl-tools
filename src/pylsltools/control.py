import argparse
from pylsltools.streams import ControlSender

def main():
    """Control stream."""
    parser = argparse.ArgumentParser(description="""Create a controller
    stream for sending messages to other pylsltools streams.""")
    parser.add_argument(
        '--name',
        help='Additional identifier to append to stream name.')
    parser.add_argument(
        '--content-type',
        default='control',
        help='Content type for marker stream.')
    parser.add_argument(
        '--source-id',
        help='Unique identifier for stream source.')
    parser.add_argument(
        '--latency',
        default=0.2,
        help='Scheduling latency.')
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Print extra debugging information.')

    args = parser.parse_args()
    controller = ControlSender(args.name, content_type=args.content_type,
                               source_id=args.source_id, latency=args.latency,
                               debug=args.debug)
    print('before start')
    try:
        controller.run()
        print('after start')
    except Exception as exc:
        # Stop all streams if one raises an error.
        controller.stop()
        raise exc
    except KeyboardInterrupt:
        print('Stopping main.')
        controller.stop()
    print('Main exit.')
