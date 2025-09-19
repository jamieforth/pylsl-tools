import argparse

def add_stream_args(
    parser,
    name_required=False,
    default_num_channels=1,
    default_nominal_srate=512,
    default_channel_format="float32",
):
    group = parser.add_argument_group(title="stream options")
    group.add_argument(
        "--name",
        required=name_required,
        help="Stream name.",
    )
    group.add_argument(
        "--content-type",
        default="data",
        help="Stream content type.",
    )
    group.add_argument(
        "-c",
        "--num-channels",
        default=default_num_channels,
        type=int,
        help="Number of stream channels.",
    )
    group.add_argument(
        "-s",
        "--sample-rate",
        default=default_nominal_srate,
        type=int,
        help="Stream sample rate.",
    )
    group.add_argument(
        "--channel-format",
        default=default_channel_format,
        choices=["float32", "double64", "string", "int64", "int32", "int16", "int8"],
        help="Channel datatype.",
    )
    group.add_argument(
        "--source-id",
        default=None,
        help="Unique identifier.",
    )

def add_marker_stream_args(
    parser,
    name_required=False,
    default_content_type="marker",
    default_num_channels=1,
):
    group = parser.add_argument_group(title="marker stream options")
    group.add_argument(
        "--name",
        required=name_required,
        help="Stream name.",
    )
    group.add_argument(
        "--content-type",
        default=default_content_type,
        help="Stream content type.",
    )
    group.add_argument(
        "-c",
        "--num-channels",
        default=default_num_channels,
        type=int,
        help="Number of stream channels.",
    )
    group.add_argument(
        "--source-id",
        default=None,
        help="Unique identifier.",
    )


def add_socket_args(parser, inlet=True, outlet=True):
    if inlet:
        group = parser.add_argument_group(title="inlet options")
        group.add_argument(
            "--inlet-max-buffer-size",
            type=int,
            default=360,
            help="""Maximum amount of data to buffer - in seconds if there is a
            nominal sampling rate, otherwise x100 in samples.""",
        )
        group.add_argument(
            "--inlet-max-chunk-size",
            type=int,
            default=1,
            help="""Max size chunks are transmitted.""",
        )
        group.add_argument(
            "--inlet-recover",
            default=True,
            action=argparse.BooleanOptionalAction,
            help="""Try to silently recover lost streams.""",
        )
        group.add_argument(
            "--inlet-processing_flags",
            type=int,
            default=0,
            help="""Post-processing options.""",
        )
    if outlet:
        group = parser.add_argument_group(title="outlet options")
        group.add_argument(
            "--outlet-max-buffer-size",
            type=int,
            default=360,
            help="""Maximum amount of data to buffer - in seconds if there is a
            nominal sampling rate, otherwise x100 in samples.""",
        )
        group.add_argument(
            "--outlet-max-chunk-size",
            type=int,
            default=1,
            help="""Max size chunks are transmitted.""",
        )
