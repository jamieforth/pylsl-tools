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

```
# Low sample-rate test with two three-channel streams.
lsl-simulate --num-streams 2 --num-channels 3 --sample-rate 2 --debug
```

```
# High sample rate simulated EEG streams.
lsl-simulate --num-streams 10 --num-channels 30 --sample-rate 500 --content-type eeg
```

See `lsl-simulate --help` for all options.


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
