"""Microphone recording via sounddevice / PipeWire.

Captures raw PCM audio from the selected input device and packages it as
WAV bytes ready to send to the Groq Whisper API.

Key notes:
- sounddevice talks to PipeWire (or ALSA/PulseAudio) transparently.
- device_index=-1 means "system default". Any other value is a sounddevice
  device index — see Recorder.list_devices() or `python main.py --list-mics`.
- We query the device's native sample rate at init time rather than forcing
  16 kHz. Some devices (e.g. Apple EarPods on USB) don't support 16 kHz
  and raise a PortAudio error if forced. The native rate works fine for Whisper.
- Audio is accumulated as int16 numpy frames while recording; stop() assembles
  them into a proper WAV header so we can POST raw bytes to Groq.
- on_level fires per chunk with the RMS amplitude so the waveform overlay
  can visualise mic activity in real time without reading from the buffer.
"""

import io
import wave

import numpy as np
import sounddevice as sd


class Recorder:
    def __init__(
        self, device_index: int = -1, sample_rate: int = 16000, channels: int = 1
    ):
        # -1 → sounddevice default; otherwise use the explicit device index
        self._device = None if device_index == -1 else device_index

        # Always use the device's native rate to avoid PortAudio "unsupported rate" errors.
        # Groq Whisper accepts any standard sample rate, not just 16 kHz.
        if self._device is not None:
            native_rate = int(sd.query_devices(self._device)["default_samplerate"])
            self._sample_rate = native_rate
        else:
            self._sample_rate = sample_rate

        self._channels = channels
        self._frames: list[np.ndarray] = []
        self._recording = False
        self._stream = None

        # Optional callback: fired each audio chunk with the RMS float.
        # Wired to Overlay.push_level by the engine.
        self.on_level: callable | None = None

    def start(self) -> None:
        """Open the input stream and begin collecting audio frames."""
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
        """Close the stream and return all captured audio as WAV bytes.
        Returns empty bytes b"" if nothing was recorded.
        """
        self._recording = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        return self._to_wav()

    def _callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        """sounddevice audio callback — runs on a C-level audio thread.
        Keep this fast: no GTK calls, no blocking, no heavy computation.
        """
        if self._recording:
            self._frames.append(indata.copy())
            if self.on_level:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                self.on_level(rms)

    def _to_wav(self) -> bytes:
        """Concatenate all recorded frames into a properly-headered WAV buffer."""
        if not self._frames:
            return b""
        audio = np.concatenate(self._frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # int16 = 2 bytes per sample
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio.tobytes())
        return buf.getvalue()

    @staticmethod
    def list_devices() -> list[dict]:
        """Return all available input devices as a list of dicts.
        Used by the mic selector UI dropdown and the --list-mics CLI flag.
        """
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
