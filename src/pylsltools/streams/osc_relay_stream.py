"""OscRelayStream stream.

For re-encoding and/or pre-processing a stream with optional remote
control and streaming over OSC.
"""

import os
import textwrap
import time
import mne

import numpy as np
#from mne_realtime import LSLClient
from pylsltools import ControlStates
from .base_stream import DataStream
from .monitor_stream import MonitorSender
from pythonosc import osc_bundle_builder, osc_message_builder, udp_client


class OscRelayStream(DataStream):
    """Relay, monitor and pre-process streams."""

    control_states = ControlStates

    def __init__(
        self,
        id,
        stream_info,
        stream_args,
        sc_args,
        *,
        recv_message_queue=None,
        send_message_queue=None,
        **kwargs,
    ):
        sender_name = stream_info.name
        name = "_osc_relay_" + stream_info.name
        sender_source_id = stream_info.source_id
        source_id = f"_osc_relay_{stream_info.source_id}:{os.getpid()}"

        super().__init__(
            name,
            content_type,
            channel_count,
            nominal_srate,
            channel_format,
            source_id=source_id,
            recv_message_queue=recv_message_queue,
            send_message_queue=send_message_queue,
        )

        # Initialise local attributes.
        self.id = id
        self.sc_ip = sc_ip
        self.sclang_port = sclang_port
        self.scsynth_port = scsynth_port
        self.latency = latency
        self.info = info
        self.stream_args = stream_args

        self.running_min = 0
        self.running_max = 1

        self.init = False

    def run(self):
        import time
        time.sleep(5)

    def run2(self):
        """Relay process main loop."""

        # if self.monitor:
        #     self.monitor = MonitorSender('_monitor_' + self.name,
        #                                  content_type='monitor',
        #                                  debug=self.debug)

        # The maximum number of values that you can set with a
        # single setn message is 1633 when the server is using
        # UDP as its communication protocol

        num_control_channels = 6
        block_count = -1

        #block_size = 512 # 4 channels
        #block_size = 256 # 8 channels
        block_size = 128 # 16 channels
        #block_size = 64 # 32 channels

        buf_periods = 8
        buf_frames = block_size * buf_periods
        #sample_count = 0
        self.eeg_synth_running = False

        # HACK: Override stream metadata because ANT.
        self.channel_count = min(self.channel_count,
                                 self.max_channels)
        if self.debug:
            print('Channel count', self.channel_count)

        ch_types = ['eeg'] * self.channel_count
        ch_names = ['Fp1', 'Fpz', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'FC5',
                    'FC1', 'FC2', 'FC6', 'M1', 'T7', 'C3', 'Cz', 'C4', 'T8',
                    'M2', 'CP5', 'CP1', 'CP2', 'CP6', 'P7', 'P3', 'Pz', 'P4',
                    'P8', 'POz', 'O1', 'Oz', 'O2'] # 'CPz'
        ch_names = ch_names[:self.channel_count]
        if self.debug:
            print(f'Channel names: {ch_names}')
            print(f'Channel types: {ch_types}')
            print(f'Number of channels {len(ch_names)}')

        mne_info = mne.create_info(ch_names, self.nominal_srate,
                                   ch_types=ch_types)
        if self.debug:
            print(mne_info)
        try:
            with LSLClient(info=mne_info, host=self.sender_source_id,
                           ) as client:

                self.scsynth = udp_client.SimpleUDPClient(self.sc_ip,
                                                          self.scsynth_port)
                self.sclang = udp_client.SimpleUDPClient(self.sc_ip,
                                                         self.sclang_port)

                client_info = client.get_measurement_info()
                buf_channels = len(client_info.ch_names)

                buf_index = 0

                reconnect_count = 1

                # Main loop.
                while not self.is_stopped():
                    if not self.recv_message_queue.empty():
                        message = self.recv_message_queue.get()
                        self.handle_message(message)
                    if not self.init:
                        self.request_init(num_control_channels, buf_frames,
                                          buf_channels)
                        if self.debug:
                            print('Waiting for init')
                        time.sleep(2)
                        continue

                    # Fist value will be 1 because we have to wait one
                    # additional block-size period for LSL to give us the data.
                    block_count = block_count + 1
                    logical_time = self.current_logical_time(block_size,
                                                             block_count)



                    # PULL DATA

                    # Epoch data has shape (n_epochs, n_channels, n_times).
                    # Timeout must be large enough to ensure we get enough data
                    # for FFT.
                    epoch = client.get_data_as_epoch(
                        n_samples=block_size,
                        timeout=self.total_buffed_duration(block_size, buf_periods))
                    if epoch is None:
                        print(f'Stream dropped? {self.name} waiting: {reconnect_count}')
                        reconnect_count = reconnect_count + 1
                        if reconnect_count < 8:
                            continue
                        else:
                            break



                    if self.debug:
                        real_time = time.time()
                        print(textwrap.fill(textwrap.dedent(f'''\
                        ** count: {block_count}
                        logical {logical_time:.3f}
                        real {time.time():.3f}
                        diff {(real_time - logical_time):.3f}
                        ''')))

                    #print(epoch.times)
                    #print(epoch.get_data())
                    # print(f"Epoch shape: {epoch.get_data().shape}")

                    # Process data.
                    #epoch.pick(["eeg"])
                    # max_channels = min(len(epoch.ch_names), 32)
                    # epoch.pick(range(0, max_channels))
                    print(f"Picks: {epoch.get_data().shape}")
                    print(f"Mean V: {np.mean(epoch.get_data())}")

                    # Send buffer to scsynth
                    buf_index = self.update_buffer(logical_time,
                                                   epoch.get_data()[0],
                                                   buf_index, block_size,
                                                   buf_channels, buf_frames,
                                                   buf_periods)


                    # Filter is longer (8251) than signal!
                    #channels = channels.filter(l_freq=0.2, h_freq=50, verbose=False)

                    # "welch" if instance_type.startswith("Raw") else "multitaper"


                    ### FFT

                    n_fft = block_size
                    if self.nominal_srate > 100:
                        spectrum = epoch.compute_psd(method="welch", fmin=2,
                                                     fmax=50,
                                                     #picks=["Fz", "Pz", "C3", "C4"],
                                                     n_fft=n_fft,
                                                     n_per_seg=64,
                                                     n_overlap=0
                                                     )
                        psd, fft_freq = spectrum.get_data(return_freqs=True)
                        #print(f"PSD shape: {psd.shape}")

                        # Grouped by event as this is an epoch?
                        psd = psd[0]

                        eeg_band_fft = np.zeros(len(self.eeg_bands))
                        for i, freq in zip(range(len(self.eeg_bands)), self.eeg_bands.values()):
                            lo, hi = freq
                            freq_ix = np.where(
                                (fft_freq >= lo) &
                                (fft_freq <= hi))[0]
                            #eeg_band_fft.append((np.mean(psd[0, freq_ix]) * 1e11 * 10).clip(0, 1))
                            eeg_band_fft[i] = np.mean(psd[:, freq_ix] * 1)

                        #eeg_band_fft = eeg_band_fft.tolist()
                        print(eeg_band_fft)
                        # bundle = osc_bundle_builder.OscBundleBuilder(
                        #     osc_bundle_builder.IMMEDIATELY)
                        # msg = osc_message_builder.OscMessageBuilder(address='/test')
                        # msg.add_arg(4.0)
                        # bundle.add_content(msg.build())
                        # msg.add_arg(2)
                        # bundle.add_content(msg.build())
                        # self.sclang.send(bundle.build())
                        # self.sclang.send_message('/c_setn', [
                        #     self.bus_idx,
                        #     num_control_channels,
                        #     *eeg_band_fft
                        # ])
                        self.scsynth.send_message('/c_setn', [
                            self.bus_idx,
                            num_control_channels,
                            *eeg_band_fft
                        ])
        except KeyboardInterrupt:
            print(f'Stopping: {self.name}')
        finally:
            # Call stop on exiting the main loop to ensure cleanup.
            self.stop()
            self.cleanup()
            print(f'Ended: {self.name}.')

    def handle_message(self, message):
        if message[0] == '/lsl/init':
            self.init = True
            self.init_time = time.time()
            self.buf_count = 0
            self.bus_idx = message[1]
            self.buf_num = message[2]
            self.eeg_group = message[3]
            self.eeg_synth = message[4]
            self.eeg_bus = message[5]

    def cleanup(self):
        print('OScRelay cleanup')
        self.notify_quit()

    # OSC messages
    def request_init(self, num_control_channels, buf_frames, buf_channels):
        if self.debug:
            print('Sending OSC init')
        self.sclang.send_message('/lsl/new', [
            self.id,
            self.sender_name,
            self.sender_source_id,
            self.sender_hostname,
            self.nominal_srate,
            num_control_channels,
            buf_frames,
            buf_channels,
        ])

    def notify_quit(self):
        if self.debug:
            print('Sending OSC free')
        # Free sc resources.
        if self.init:
            # self.sclang.send_message('/lsl/free',[
            #     self.id,
            #     self.sender_name,
            #     self.sender_source_id,
            #     self.sender_hostname
            # ])
            bundle = osc_bundle_builder.OscBundleBuilder(
                time.time() + self.latency)
            msg = osc_message_builder.OscMessageBuilder('/lsl/free')
            msg.add_arg(self.sender_name)
            msg.add_arg(self.sender_source_id)
            msg.add_arg(self.sender_hostname)
            bundle.add_content(msg.build())
            self.sclang.send(bundle.build())

            # Since we started the synth we should really free it (our
            # latency may be different to sclang).
            bundle = osc_bundle_builder.OscBundleBuilder(
                time.time() + self.latency)
            msg = osc_message_builder.OscMessageBuilder(address='/n_free')
            msg.add_arg(self.eeg_synth)
            bundle.add_content(msg.build())
            self.scsynth.send(bundle.build())

            self.init = False

    def normalise(self, sig):
        av = np.mean(sig)
        print('average', av)
        sig = sig - av
        sd = np.std(sig, axis=0)
        sig = sig / sd
        #print(self.name, sig[0:10])
        # sig = (sig / (self.running_max - self.running_min)) + self.running_min
        return sig

    def update_buffer(self, logical_time, sig, buf_index, block_size,
                      buf_channels, buf_frames, buf_periods):
        #print(f'size: {sig.size}')
        #print(f'sig shape: {sig.shape}')
        #print(sig[0:10])

        # if sig.shape[0] > 8:
        #     sig = sig[0:8]


        #sig = np.ravel(sig, 'K')
        if sig.shape[0] > 1:
            #sig = sig.T
            sig = sig.T.flatten()
        #print(f'ravel: {sig}')
        #print(f'ravel size: {sig.size}')
        #print(f'list size: {len(sig.tolist())}')
        if np.isnan(sig).any():
            print(f'********* NaNs in {self.name}')
            return

        #print(self.name, sig[0:10])

        #sig = self.normalise(sig)

        print(f'**** bufnum: {self.buf_num} buf_index: {buf_index}')

        bundle = osc_bundle_builder.OscBundleBuilder(
            logical_time + self.latency)
        msg = osc_message_builder.OscMessageBuilder(address='/b_setn')
        msg.add_arg(self.buf_num)
        msg.add_arg(buf_index)
        msg.add_arg(block_size * buf_channels)
        for val in sig.tolist():
            msg.add_arg(val)
        bundle.add_content(msg.build())
        print('****************** update buffer')
        self.scsynth.send(bundle.build())

        buf_index = (buf_index + (block_size * buf_channels)) % (buf_frames * buf_channels)

        if not self.eeg_synth_running:
            #logical_time = time.time() + ((block_size * buf_periods) / self.nominal_srate)

            bundle = osc_bundle_builder.OscBundleBuilder(
                logical_time + self.buf_read_latency(
                    block_size,
                    buf_periods) + self.latency)
            msg = osc_message_builder.OscMessageBuilder(address='/s_new')
            # Synth
            msg.add_arg(f'eegRead{buf_channels}')
            # Synth ID
            msg.add_arg(self.eeg_synth)
            # Add action
            msg.add_arg(0)
            # Target
            msg.add_arg(self.eeg_group)
            # Args
            msg.add_arg('out')
            msg.add_arg(self.eeg_bus)
            msg.add_arg('bufnum')
            msg.add_arg(self.buf_num)
            msg.add_arg('rate')
            msg.add_arg(self.nominal_srate / 48000)
            # Add msg to bundle.
            bundle.add_content(msg.build())
            print('******************', msg)
            self.scsynth.send(bundle.build())

        self.eeg_synth_running = True

        return buf_index

    def current_logical_time(self, block_size, block_count):
        return self.init_time + (
            block_count * (block_size / self.nominal_srate)
        )

    def total_buffed_duration(self, block_size, buf_periods):
        return self.block_size_duration(block_size) * buf_periods

    def block_size_duration(self, block_size):
        return block_size / self.nominal_srate

    def buf_read_latency(self, block_size, buf_periods):
        return (block_size * (buf_periods - 1)) / self.nominal_srate

    def print(self, name, now, timestamp, content_type, data):
        print(textwrap.fill(textwrap.dedent(f'''\
        {name}:
        now: {now:.6f},
        timestamp: {timestamp:.6f},
        {content_type}: {data}
        '''), 200))
