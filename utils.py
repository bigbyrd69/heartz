"""Shared utilities for AirGap Bridge BFSK ultrasonic data transfer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Sequence

import numpy as np
from scipy.signal import windows

# Protocol markers (byte-aligned bit strings)
START_MARKER = "11111110"
END_MARKER = "01111111"

# Primary and fallback frequencies
PRIMARY_FREQS = (18000.0, 19000.0)
FALLBACK_FREQS = (16000.0, 17000.0)


@dataclass(frozen=True)
class BridgeConfig:
    """Runtime configuration shared between sender and receiver."""

    sample_rate: int = 44100
    bit_duration: float = 0.1
    freq_0: float = PRIMARY_FREQS[0]
    freq_1: float = PRIMARY_FREQS[1]
    tolerance_hz: float = 300.0
    amplitude: float = 0.35

    @property
    def samples_per_bit(self) -> int:
        return int(self.sample_rate * self.bit_duration)

    @property
    def bit_rate(self) -> float:
        return 1.0 / self.bit_duration


# ---------------------
# Binary framing helpers
# ---------------------
def bytes_to_bits(data: bytes) -> str:
    """Convert bytes to an 8-bit padded bit string."""
    return "".join(f"{b:08b}" for b in data)


def bits_to_bytes(bits: str) -> bytes:
    """Convert a bit string to bytes. Expects whole bytes only."""
    if len(bits) % 8 != 0:
        raise ValueError("Bit stream length must be divisible by 8")
    return bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits), 8))


def xor_checksum(data: bytes) -> int:
    """Simple XOR checksum across bytes for lightweight integrity checks."""
    checksum = 0
    for b in data:
        checksum ^= b
    return checksum


def add_checksum(data: bytes) -> bytes:
    """Append XOR checksum byte to payload."""
    return data + bytes([xor_checksum(data)])


def verify_and_strip_checksum(data: bytes) -> bytes:
    """Verify last byte as XOR checksum and return original payload."""
    if not data:
        raise ValueError("Empty payload")
    payload, rx_checksum = data[:-1], data[-1]
    calc = xor_checksum(payload)
    if calc != rx_checksum:
        raise ValueError(
            f"Checksum mismatch: expected {calc:#04x}, received {rx_checksum:#04x}"
        )
    return payload


def frame_message(payload: bytes) -> str:
    """Frame payload using start/end markers and checksum byte."""
    checksummed = add_checksum(payload)
    payload_bits = bytes_to_bits(checksummed)
    return START_MARKER + payload_bits + END_MARKER


def unframe_message(bitstream: str) -> bytes:
    """Extract framed payload and validate checksum.

    The receiver accumulates raw bits continuously. Once a full frame is
    detected (START marker followed by END marker), payload bits are decoded
    back to bytes and integrity is validated via XOR checksum.
    """
    start_idx = bitstream.find(START_MARKER)
    if start_idx == -1:
        raise ValueError("START marker not found")

    payload_start = start_idx + len(START_MARKER)
    end_idx = bitstream.find(END_MARKER, payload_start)
    if end_idx == -1:
        raise ValueError("END marker not found")

    payload_bits = bitstream[payload_start:end_idx]
    if len(payload_bits) % 8 != 0:
        raise ValueError("Payload bit length is not byte-aligned")

    checksummed = bits_to_bytes(payload_bits)
    return verify_and_strip_checksum(checksummed)


# ---------------------
# Optional AES helpers
# ---------------------
def _derive_key(passphrase: str) -> bytes:
    """Derive a 32-byte key from passphrase using SHA-256."""
    return hashlib.sha256(passphrase.encode("utf-8")).digest()


def encrypt_payload(data: bytes, passphrase: str) -> bytes:
    """Encrypt payload with AES-GCM.

    Output format: [12-byte nonce][ciphertext+tag]. If cryptography is not
    available, raises RuntimeError so callers can report a clear message.
    """
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError(
            "AES encryption requested but 'cryptography' is not installed"
        ) from exc

    key = _derive_key(passphrase)
    nonce = np.random.bytes(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_payload(data: bytes, passphrase: str) -> bytes:
    """Decrypt payload produced by encrypt_payload."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:
        raise RuntimeError(
            "AES decryption requested but 'cryptography' is not installed"
        ) from exc

    if len(data) < 13:
        raise ValueError("Encrypted payload is too short")
    nonce, ciphertext = data[:12], data[12:]
    key = _derive_key(passphrase)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)


# ------------------------
# Signal processing helpers
# ------------------------
def generate_tone(frequency: float, duration: float, sample_rate: int, amplitude: float) -> np.ndarray:
    """Generate one sine tone segment for a single BFSK bit.

    Signal generation notes:
    - Each bit maps to a fixed frequency (f0 for 0, f1 for 1).
    - Tone duration equals bit_duration; concatenating tone segments creates
      the full modulated transmission waveform.
    """
    t = np.arange(int(sample_rate * duration)) / sample_rate
    return (amplitude * np.sin(2 * np.pi * frequency * t)).astype(np.float32)


def bits_to_waveform(bits: str, cfg: BridgeConfig) -> np.ndarray:
    """Convert bit stream to BFSK waveform by concatenating per-bit tones."""
    segments: List[np.ndarray] = []
    for bit in bits:
        freq = cfg.freq_1 if bit == "1" else cfg.freq_0
        segments.append(generate_tone(freq, cfg.bit_duration, cfg.sample_rate, cfg.amplitude))
    if not segments:
        return np.array([], dtype=np.float32)
    return np.concatenate(segments)


def detect_dominant_frequency(chunk: np.ndarray, sample_rate: int) -> float:
    """Detect dominant frequency using FFT magnitude peak.

    FFT detection notes:
    - Apply Hann window to reduce spectral leakage.
    - Compute real FFT (`rfft`) for non-negative frequencies.
    - Dominant bin is used as the candidate tone frequency.
    """
    if chunk.ndim > 1:
        chunk = chunk[:, 0]

    if len(chunk) == 0:
        return 0.0

    window = windows.hann(len(chunk), sym=False)
    spectrum = np.fft.rfft(chunk * window)
    freqs = np.fft.rfftfreq(len(chunk), d=1.0 / sample_rate)
    idx = int(np.argmax(np.abs(spectrum)))
    return float(freqs[idx])


def frequency_to_bit(freq: float, cfg: BridgeConfig) -> str | None:
    """Map detected frequency to bit using configurable tolerance."""
    if abs(freq - cfg.freq_0) <= cfg.tolerance_hz:
        return "0"
    if abs(freq - cfg.freq_1) <= cfg.tolerance_hz:
        return "1"
    return None


def extract_latest_frame(bits: Sequence[str]) -> str | None:
    """Find the latest complete frame in a rolling bit buffer.

    Framing protocol notes:
    - Receiver runs continuously, so it stores a scrolling bitstream.
    - A frame begins at START marker and ends at END marker.
    - We return only the newest complete frame to avoid duplicate decoding.
    """
    s = "".join(bits)
    start = s.rfind(START_MARKER)
    if start == -1:
        return None
    payload_start = start + len(START_MARKER)
    end = s.find(END_MARKER, payload_start)
    if end == -1:
        return None
    return s[start : end + len(END_MARKER)]
