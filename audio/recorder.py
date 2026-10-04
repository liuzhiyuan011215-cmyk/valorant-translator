import time
import threading
import collections
import numpy as np
try:
    import sounddevice as sd
except ImportError:
    sd = None

from audio.vad import AudioVAD
from config import config_mgr

TARGET_RATE = 16000  # Live API expects 16 kHz mono PCM


def open_input_stream(device_index, callback):
    """
    Open a mono float32 input stream with 100 ms blocks and return (stream, sample_rate).
    For WASAPI devices ask Windows for 16 kHz directly (auto_convert uses the system's proper
    resampler, cleaner than our linear interpolation); otherwise fall back to the native rate.
    """
    attempts = []
    default_rate = 44100
    try:
        dev_info = sd.query_devices(device_index)
        default_rate = int(dev_info.get('default_samplerate', 44100))
        if sd.query_hostapis(dev_info['hostapi'])['name'] == 'Windows WASAPI':
            attempts.append((TARGET_RATE, sd.WasapiSettings(auto_convert=True)))
    except Exception as e:
        print(f"Could not query device info: {e}")
    attempts += [(rate, None) for rate in (default_rate, 44100, 48000, 16000)]

    last_err = None
    for rate, extra in attempts:
        try:
            stream = sd.InputStream(
                device=device_index,
                channels=1,
                samplerate=rate,
                blocksize=int(rate * 0.1),  # 100ms
                dtype='float32',
                callback=callback,
                extra_settings=extra
            )
            stream.start()
            print(f"Audio stream started on device {device_index} at {rate} Hz"
                  f"{' (WASAPI auto-convert)' if extra else ''}")
            return stream, rate
        except Exception as e:
            last_err = e
            print(f"Failed to open audio stream at {rate} Hz: {e}")
    raise Exception(f"无法打开选中的音频设备: {last_err}")


def to_16k(chunk: np.ndarray, rate: int) -> np.ndarray:
    """Resample a mono float32 chunk to 16 kHz (only needed when the device couldn't open at 16 kHz)."""
    if rate == TARGET_RATE:
        return chunk
    target_samples = int(len(chunk) * TARGET_RATE / rate)
    return np.interp(
        np.linspace(0, len(chunk), target_samples, endpoint=False),
        np.arange(len(chunk)),
        chunk
    ).astype(np.float32)


def to_pcm16(chunk: np.ndarray) -> bytes:
    """Convert float32 PCM (-1.0 to 1.0) to 16-bit little-endian PCM bytes."""
    return (np.clip(chunk, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


class AudioRecorder:
    def __init__(self, audio_chunk_callback, volume_callback=None):
        self.audio_chunk_callback = audio_chunk_callback
        self.volume_callback = volume_callback
        
        self.target_sample_rate = 16000
        self.block_size = 1600  # 100ms at 16kHz per official Google Live API specification
        self.actual_sample_rate = 16000
        
        # Pre-roll ring buffer: keeps last 1000ms (10 chunks) of audio
        # When sudden speech arrives (push-to-talk), pre-roll ensures the opening words are captured
        self.pre_roll_buffer = collections.deque(maxlen=10)
        self.in_speech = False
        self.silence_count = 0
        self.last_keepalive_time = 0.0
        
        self.vad = AudioVAD(
            sample_rate=self.target_sample_rate,
            threshold=config_mgr.get("vad_threshold", 0.015),
            silence_duration_ms=config_mgr.get("silence_duration_ms", 1000),
            min_speech_ms=config_mgr.get("min_speech_duration_ms", 500)
        )

        self.stream = None
        self.is_recording = False
        self.device_index = None

    @staticmethod
    def get_audio_devices() -> list[dict]:
        """
        List all available audio input devices.
        """
        if sd is None:
            return [{"index": -1, "name": "演示模式 (Sounddevice 未安装)", "hostapi": 0}]

        devices = []
        try:
            hostapis = sd.query_hostapis()
            all_devices = sd.query_devices()
            
            for idx, dev in enumerate(all_devices):
                if dev['max_input_channels'] > 0:
                    api_name = hostapis[dev['hostapi']]['name']
                    dev_name = f"{dev['name']} [{api_name}]"
                    devices.append({
                        "index": idx,
                        "name": dev_name,
                        "hostapi": api_name,
                        "raw_name": dev['name'],
                        "default_samplerate": int(dev.get('default_samplerate', 44100))
                    })
        except Exception as e:
            print(f"Error querying audio devices: {e}")
            devices.append({"index": -1, "name": "默认音频捕获设备", "hostapi": "", "default_samplerate": 44100})

        return devices

    @staticmethod
    def find_cable_device() -> dict | None:
        """
        Pick the one device this app should listen to: VB-Cable's CABLE Output.
        Teammates' voice is routed there, while a microphone would record yourself and stereo mix
        would add gunfire. The same device is listed once per Windows audio API; prefer WASAPI,
        then DirectSound, then MME (WDM-KS entries are VB-Cable internals), and take the first one
        that actually accepts 16-bit mono capture at its native rate.
        """
        if sd is None:
            return None
        preference = ["Windows WASAPI", "Windows DirectSound", "MME"]
        candidates = [
            d for d in AudioRecorder.get_audio_devices()
            if d["hostapi"] in preference
            and "cable" in d.get("raw_name", "").lower() and "output" in d.get("raw_name", "").lower()
        ]
        candidates.sort(key=lambda d: preference.index(d["hostapi"]))
        for d in candidates:
            try:
                sd.check_input_settings(device=d["index"], channels=1, samplerate=d["default_samplerate"])
                return d
            except Exception as e:
                print(f"Skipping {d['name']}: {e}")
        return None

    @staticmethod
    def find_microphone() -> dict | None:
        """Your microphone for hold-F8 speech: Windows' default recording device (WASAPI entry), never VB-Cable."""
        if sd is None:
            return None
        try:
            wasapi = next(i for i, h in enumerate(sd.query_hostapis()) if h['name'] == 'Windows WASAPI')
            default_index = sd.query_hostapis(wasapi)['default_input_device']
        except (StopIteration, Exception):
            return None
        mics = [d for d in AudioRecorder.get_audio_devices()
                if d["hostapi"] == "Windows WASAPI" and "cable" not in d.get("raw_name", "").lower()]
        mics.sort(key=lambda d: d["index"] != default_index)  # the default device first
        return mics[0] if mics else None

    def start(self, device_index=None):
        """Start streaming continuous audio to selected device."""
        if self.is_recording:
            return

        self.device_index = device_index
        self.pre_roll_buffer.clear()
        self.in_speech = False
        self.silence_count = 0
        self.last_keepalive_time = time.time()

        if sd is None or self.device_index == -1:
            print("Running audio recorder in mock mode...")
            self.is_recording = True
            return

        self.stream, self.actual_sample_rate = open_input_stream(self.device_index, self._audio_callback)
        self.is_recording = True

    def stop(self):
        """Stop listening."""
        self.is_recording = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"Error closing audio stream: {e}")
            self.stream = None
        self.pre_roll_buffer.clear()
        self.in_speech = False
        print("Audio recorder stopped.")

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """Callback executed by sounddevice background audio thread with pre-roll buffering."""
        if status:
            pass

        if not self.is_recording:
            return

        pcm_chunk = to_16k(indata[:, 0], self.actual_sample_rate)  # Mono channel

        # Calculate volume for GUI VU meter
        rms = self.vad.calculate_rms(pcm_chunk)
        if self.volume_callback:
            self.volume_callback(rms)

        raw_pcm_bytes = to_pcm16(pcm_chunk)

        # Intelligent Pre-Roll & Voice Gate
        threshold = config_mgr.get("vad_threshold", 0.015)

        if rms >= threshold:
            # Voice activity detected!
            if not self.in_speech:
                # Sudden speech onset: Flush 400ms pre-roll lead-in immediately!
                # This guarantees that the beginning of rapid / sudden speech is never clipped!
                while self.pre_roll_buffer:
                    self.audio_chunk_callback(self.pre_roll_buffer.popleft())
                self.in_speech = True

            self.silence_count = 0
            self.audio_chunk_callback(raw_pcm_bytes)
        else:
            if self.in_speech:
                # Post-roll hangover: keep streaming real silence for 3s after speech.
                # The Live Translate model only finalizes a sentence after it has *heard* the trailing
                # silence; if the stream stops early, the last words stay stuck on the server until
                # the next person talks, and then show up glued to the front of the next subtitle.
                self.silence_count += 1
                self.audio_chunk_callback(raw_pcm_bytes)
                if self.silence_count >= 30: # 3000ms
                    self.in_speech = False
                    self.silence_count = 0
            else:
                # Standby: Maintain pre-roll ring buffer (400ms)
                self.pre_roll_buffer.append(raw_pcm_bytes)
                
                # Keep WebSocket connection hot during silence with occasional keep-alive
                now = time.time()
                if now - self.last_keepalive_time > 2.5:
                    self.last_keepalive_time = now
                    self.audio_chunk_callback(raw_pcm_bytes)


class PushToTalkRecorder:
    """
    Microphone capture for hold-F8 speech. The mic is opened only while F8 is held and every
    chunk is forwarded (no energy gate: everything you say while holding the key counts).
    """
    def __init__(self, audio_chunk_callback):
        self.audio_chunk_callback = audio_chunk_callback
        self.stream = None
        self.rate = TARGET_RATE

    def start(self, device_index):
        if self.stream is None:
            self.stream, self.rate = open_input_stream(device_index, self._audio_callback)

    def stop(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception as e:
                print(f"Error closing microphone stream: {e}")
            self.stream = None

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        self.audio_chunk_callback(to_pcm16(to_16k(indata[:, 0], self.rate)))
