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

Generate test synthetic data streams.

```
# Low sample-rate test with two three-channel streams.
lsl-simulate --num-streams 2 --num-channels 3 --sample-rate 2 --debug
```

```
# High sample rate simulated EEG streams.
lsl-simulate --num-streams 10 --num-channels 30 --sample-rate 500 --content-type eeg
```

See `lsl-simulate --help` for all options.

Streams can also be remote controlled by an `lsl-control` stream by
passing in the control stream name, e.g.

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
reliably there must be a specified latency larger than any network
latency (default 0.5 seconds). Any messages that arrive late will
print a warning but streams should be able to catch up.


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
