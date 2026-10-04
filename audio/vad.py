import io
import wave
import numpy as np

class AudioVAD:
    def __init__(self, sample_rate=16000, threshold=0.015, silence_duration_ms=600, min_speech_ms=400):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_duration_ms = silence_duration_ms
        self.min_speech_ms = min_speech_ms

        self.buffer = []
        self.is_speaking = False
        self.silence_samples = 0
        self.speech_samples = 0

    def set_params(self, threshold=None, silence_ms=None, min_speech_ms=None):
        if threshold is not None:
            self.threshold = threshold
        if silence_ms is not None:
            self.silence_duration_ms = silence_ms
        if min_speech_ms is not None:
            self.min_speech_ms = min_speech_ms

    def calculate_rms(self, pcm_chunk: np.ndarray) -> float:
        """Calculate Root Mean Square (RMS) volume of audio chunk."""
        if len(pcm_chunk) == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(pcm_chunk))))

    def process_chunk(self, pcm_chunk: np.ndarray) -> bytes | None:
        """
        Processes incoming float32 numpy audio chunk.
        Returns WAV bytes if a complete sentence/speech chunk is detected, else None.
        """
        rms = self.calculate_rms(pcm_chunk)
        chunk_len = len(pcm_chunk)

        if rms > self.threshold:
            # Voice activity detected
            self.is_speaking = True
            self.silence_samples = 0
            self.speech_samples += chunk_len
            self.buffer.append(pcm_chunk)
            return None
        else:
            if self.is_speaking:
                self.silence_samples += chunk_len
                self.buffer.append(pcm_chunk)
                
                max_silence_samples = int((self.silence_duration_ms / 1000.0) * self.sample_rate)
                
                if self.silence_samples >= max_silence_samples:
                    # Speech segment ended!
                    min_speech_samples = int((self.min_speech_ms / 1000.0) * self.sample_rate)
                    
                    if self.speech_samples >= min_speech_samples:
                        # Valid audio segment, export to WAV
                        full_pcm = np.concatenate(self.buffer, axis=0)
                        wav_bytes = self.pcm_to_wav(full_pcm)
                        
                        # Reset VAD state
                        self.reset()
                        return wav_bytes
                    else:
                        # Too short (noise click), discard
                        self.reset()
                        return None
            return None

    def reset(self):
        self.buffer = []
        self.is_speaking = False
        self.silence_samples = 0
        self.speech_samples = 0

    def pcm_to_wav(self, pcm_data: np.ndarray) -> bytes:
        """Converts float32 numpy array (-1.0 to 1.0) to 16-bit PCM WAV bytes."""
        # Convert float32 to int16
        int16_data = (np.clip(pcm_data, -1.0, 1.0) * 32767).astype(np.int16)
        
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(int16_data.tobytes())
        
        return wav_io.getvalue()
