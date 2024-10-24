# pylsl-tools

## Install
### Prerequisites
#### Linux/Mac

Install the [`liblsl` system library](https://github.com/sccn/liblsl).

#### Windows

None. A pre-built binary wheel distribution of `liblsl` will be
installed automatically when installing `pylsl-tools`.

### Option 1: Create a new environment from this repo using `PDM`

PDM is a package and dependency manager, this is simplest way to set
up a self-contained virtual environment with everything installed.

First install PDM: https://pdm-project.org/.

```
git clone https://github.com/jamieforth/pylsl-tools.git
cd pylsl-tools
pdm install

# Or optionally install additional dependencies.

pdm install --with xdf
```

The full install includes
[pyxdf-tools](https://github.com/jamieforth/pyxdf-tools/tree/main) for
processing `xdf` files.

#### Updating

```
git pull
pdm update
```

#### Activating the virtual environment

The virtual environment can be activated/deactivated in the usual way.

```
source .venv/bin/activate
deactivate
```

### Option 2: Install into an existing environment

```
pip install -e git+https://github.com/jamieforth/pylsl-tools.git#egg=pylsltools
```

```
# Optionally install additional dependencies.
pip install -e 'git+https://github.com/jamieforth/pylsl-tools.git#egg=pylsltools[xdf]'
```

## Usage
### lsl-simulate

Generate test synthetic data streams. Each synthetic stream runs in
its own process and generates data slightly ahead of time according to
the `--latency` option (default 0.2 seconds) to ensure all processes
have sufficient time to generate samples. Any processes that fail to
generate their data in time will print a warning message to increase
the latency.

With the `--sync` option (default) all samples are generated with
respect to a synchronised logical time (i.e. all timestamps will
correspond exactly to the sample rate). With the `--no-sync` option
timestamps will be real-time timestamps (i.e. there will be a very
small amount of real-world jitter). In practice the jitter should be
very small so long as their is sufficient latency to ensure all
process can meet the demand of the sample rate.

```
# Low sample-rate test with two three-channel streams.
lsl-simulate --num-streams 2 --num-channels 3 --sample-rate 2 --debug
```

```
# Higher sample rate simulated EEG streams.
lsl-simulate --num-streams 1 --num-channels 35 --sample-rate 512 --content-type eeg
```

See `lsl-simulate --help` for all options.

Streams can also be remote controlled by an `lsl-control` stream by
passing in the control stream name.

```
lsl-simulate --num-streams 1 --num-channels 35 --sample-rate 512 --content-type eeg --control-name ctrl1
```


### lsl-control

Send timestamped control messages to other streams.

```
# Send control messages to other devices.
lsl-control --name ctrl1
```

This will then allow commands to be typed into the terminal which will
be executed by receiving streams at the “correct time” (= real-time
resolved time according to LSL). Crucially, the accuracy of the
synchronised start time across multiple devices is entirely dependent
on the stability of the LSL clocks.

For this to work reliably all simulated stream clocks must be given
time to stabilise (ideally a couple of minutes) and there must be a
specified latency larger than any real-world network latency (default
0.5 seconds). Any messages that arrive late will print a warning on
the receiving device. If a simulated stream receives a late message it
will catch up without dropping samples (by sending a burst of samples
each with the correct logical timestamp).  Real-time streams will drop
samples but will send correctly timestamped samples from the point at
which they receive a late message.

See `lsl-control --help` for all options.

### lsl-relay

```
lsl-relay --debug
```

```
# Run with Ant Server.
lsl-relay
```

```
# Run with Ant EEGO App.
lsl-relay --re-encode-timestamps
```

See `lsl-relay --help` for all options.


### lsl-monitor

Show monitoring information for all `_monitor_` streams on the network
(created by `lsl-relay --monitor`).

```
lsl-monitor
```

See `lsl-monitor --help` for all options.
