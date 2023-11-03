# pylsl-tools

## Install
### Install into an existing environment

```
pip install -e git+https://github.com/jamieforth/pylsl-tools.git#egg=pylsltools
```

### Create a new environment from this repo using `pipenv`

```
git clone https://github.com/jamieforth/pylsl-tools.git
cd pylsl-tools
pipenv install
```

## Usage
### lsl-simulate

Generate test synthetic data streams. Each synthetic stream runs in
its own process and generates data slightly ahead of time according to
the `--latency`` option (default 0.2 seconds) to ensure all processes
have sufficient time to generate samples. Any processes that fail to
generate their data in time will print a warning message to increase
the latency.

With the `--sync`` option (default) all samples are generated with
respect to a synchronised logical time (i.e. all timestamps will
correspond exactly to the sample rate). With the --no-sync option
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
lsl-simulate --num-streams 10 --num-channels 30 --sample-rate 500 --content-type eeg
```

See `lsl-simulate --help` for all options.

Streams can also be remote controlled by an `lsl-control` stream by
passing in the control stream name.

```
lsl-simulate --control-name ctrl1 ...
```


### lsl-control

Send timestamped control messages to other streams.

```
# Send control messages to other devices.
lsl-control --name ctrl1
```

This will then allow commands to be typed into the terminal which will
be executed by receiving streams at the correct time. For this to work
reliably there must be a specified latency larger than any real-world
network latency (default 0.5 seconds). Any messages that arrive late
will print a warning on the receiving device. If a simulated stream
receives a late message it will catch up without dropping samples (by
sending a burst of samples each with the correct logical timestamp).
Real-time streams will drop samples but will send correctly
timestamped samples from the point at which they receive a late
message.

See `lsl-control --help` for all options.

### lsl-relay

```
lsl-relay --debug
```

```
# Run with Ant Server.
lsl-relay --keep-orig-timestamps --monitor
```

```
# Run with Ant EEGO App.
lsl-relay --monitor
```

See `lsl-relay --help` for all options.


### lsl-monitor

Show monitoring information for all `_monitor_` streams on the network
(created by `lsl-relay --monitor`).

```
lsl-monitor
```

See `lsl-monitor --help` for all options.
