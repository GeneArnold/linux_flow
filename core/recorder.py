"""Mic recording using sounddevice.

Records audio while active, returns WAV bytes ready to send to Groq Whisper.
"""

import io
import threading
import wave

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(
        self, device_index: int = -1, sample_rate: int = 16000, channels: int = 1
    ):
        self._device = None if device_index == -1 else device_index
        # Use the device's native sample rate if it doesn't support the requested one
        if self._device is not None:
            native_rate = int(sd.query_devices(self._device)["default_samplerate"])
            self._sample_rate = native_rate
        else:
            self._sample_rate = sample_rate
        self._channels = channels
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._stream = None
        self.on_level: callable | None = None  # optional callback(rms: float) per chunk

    def start(self) -> None:
        self._frames = []
        self._recording = True
        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> bytes:
        """Stop recording and return WAV bytes."""
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self._to_wav()

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if self._recording:
            self._frames.append(indata.copy())
            if self.on_level:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                self.on_level(rms)

    def _to_wav(self) -> bytes:
        if not self._frames:
            return b""
        audio = np.concatenate(self._frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    @staticmethod
    def list_devices() -> list[dict]:
        """Return input devices as a list of dicts with index, name, channels."""
        devices = []
        for i, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] > 0:
                devices.append(
                    {
                        "index": i,
                        "name": dev["name"],
                        "channels": dev["max_input_channels"],
                        "sample_rate": int(dev["default_samplerate"]),
                    }
                )
        return devices
