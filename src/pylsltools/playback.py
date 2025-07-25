import argparse
import multiprocessing as mp
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pdxdf import hdf5

from pylsltools.streams import GeneratorStream


@dataclass
class StreamInfoAV:
    name: str
    content_type: str
    channel_count: np.int16
    nominal_srate: np.float64
    channel_format: str
    channel_info: dict
    desc: dict                  # should include av_spec number


def stream_generator(
    path, start=0, stop=None, loop=False, read_chunk_size=60, debug=False
):
    with pd.HDFStore(path, mode="r") as store:
        nrows = store.get_storer("stream").nrows
        if start >= nrows:
            raise ValueError(f"Start index ({start}) must be less than {nrows}.")
        if stop is None:
            req_nrows = nrows - start
        else:
            stop = min(nrows, stop)
            req_nrows = stop - start
        if debug:
            print(f"Total rows: {nrows}, requested: {req_nrows}")
        if read_chunk_size == 0 or req_nrows <= read_chunk_size:
            # Load entire dataset and generate an infinite stream if loop=True.
            if debug:
                print("Loading all rows")
            df = pd.read_hdf(store, "stream", start=start, stop=stop)
            while True:
                for sample in sample_generator(df):
                    yield sample
                if not loop:
                    break
                elif debug:
                    print("Loop")
        else:
            # Load chunk-by-chunk.
            while True:
                df_iter = pd.read_hdf(
                    store,
                    "stream",
                    start=start,
                    stop=stop,
                    iterator=True,
                    chunksize=read_chunk_size,
                )
                for chunk in df_iter:
                    if debug:
                        print(f"Read chunk size: {chunk.shape[0]}")
                    for sample in sample_generator(chunk):
                        yield sample
                if not loop:
                    break
                elif debug:
                    print("Loop")


def sample_generator(df):
    i = 0
    while i < df.shape[0]:
        yield (df.index[i], df.iloc[i].to_numpy())
        i += 1


def main():
    """Create a stream from a DataFrame (HDF5)."""

    # Use multiprocessing spawn on all platforms.
    mp.set_start_method("spawn")

    parser = argparse.ArgumentParser(
        description="""Create an LSL stream from a DataFrame (HDF5)."""
    )

    parser.add_argument(
        "path",
        help="Path to a HDF5 file",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=0,
        help="Start sample index.",
    )
    parser.add_argument(
        "--stop",
        type=int,
        default=None,
        help="Stop sample index.",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Loop playback.",
    )
    parser.add_argument(
        "--read-chunk-size",
        type=int,
        default=120,
        help="Number of samples to read from disk (0 loads entire DataFrame)",
    )
    parser.add_argument(
        "--latency",
        type=float,
        default=0.1,
        help="Scheduling latency in seconds.",
    )
    parser.add_argument(
        "--start-delay",
        type=float,
        default=0,
        help="Start time delay in seconds.",
    )
    parser.add_argument(
        "--source-id",
        default="",
        help="Unique identifier for stream source.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=0,
        help="""Desired outlet chunk size in samples. Inlets can override
        this.""",
    )
    parser.add_argument(
        "--max-buffered",
        type=int,
        default=360,
        help="""Maximum amount of data to buffer - in seconds if there is a
        nominal sampling rate, otherwise x100 in samples.""",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print extra debugging information.",
    )

    args = parser.parse_args()

    info = hdf5.load_stream_info(args.path)
    generator_fn = stream_generator
    generator_args = [
        args.path,
        args.start,
        args.stop,
        args.loop,
        args.read_chunk_size,
    ]

    stream = GeneratorStream(
        info.name,
        info.content_type,
        info.channel_count,
        info.nominal_srate,
        info.channel_format,
        generator_fn,
        generator_args,
        source_id=args.source_id,
        desc=info.desc,
        channel_info=info.channel_info,
        latency=args.latency,
        start_delay=args.start_delay,
        chunk_size=args.chunk_size,
        max_buffered=args.max_buffered,
        debug=args.debug,
    )
    try:
        stream.start()
        stream.join()
    except Exception as exc:
        # Stop all streams if one raises an error.
        stream.stop()
        raise exc
    except KeyboardInterrupt:
        print("Stopping main.")
        stream.stop()
    finally:
        print("Main exit.")
