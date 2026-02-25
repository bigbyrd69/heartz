"""AirGap Bridge receiver: detect BFSK bits from microphone audio and decode messages."""

from __future__ import annotations

import argparse
import collections
import sys
from typing import Deque

import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd

from utils import (
    BridgeConfig,
    FALLBACK_FREQS,
    PRIMARY_FREQS,
    decrypt_payload,
    detect_dominant_frequency,
    extract_latest_frame,
    frequency_to_bit,
    unframe_message,
)


def auto_calibrate(cfg: BridgeConfig, seconds: float = 2.0) -> BridgeConfig:
    """Estimate ambient spectral peaks near expected BFSK bands.

    Calibration mode records ambient audio and searches for strongest peaks in
    windows near default frequencies. This helps compensate for clock drift,
    codec shifts, and speaker/mic frequency response differences.
    """
    print(f"Calibrating for {seconds:.1f}s... please keep environment quiet.")
    data = sd.rec(int(seconds * cfg.sample_rate), samplerate=cfg.sample_rate, channels=1, dtype="float32")
    sd.wait()
    chunk = data[:, 0]

    window = np.hanning(len(chunk))
    spectrum = np.abs(np.fft.rfft(chunk * window))
    freqs = np.fft.rfftfreq(len(chunk), d=1.0 / cfg.sample_rate)

    def peak_near(target: float, span: float = 1200.0) -> float:
        mask = (freqs >= target - span) & (freqs <= target + span)
        if not np.any(mask):
            return target
        local_freqs = freqs[mask]
        local_spec = spectrum[mask]
        return float(local_freqs[int(np.argmax(local_spec))])

    f0 = peak_near(cfg.freq_0)
    f1 = peak_near(cfg.freq_1)

    print(f"Calibration result: f0={f0:.1f}Hz, f1={f1:.1f}Hz")
    return BridgeConfig(
        sample_rate=cfg.sample_rate,
        bit_duration=cfg.bit_duration,
        freq_0=f0,
        freq_1=f1,
        tolerance_hz=cfg.tolerance_hz,
        amplitude=cfg.amplitude,
    )


def decode_frame(frame_bits: str, decrypt: bool, passphrase: str | None) -> str:
    payload = unframe_message(frame_bits)
    if decrypt:
        if not passphrase:
            raise ValueError("--passphrase is required for decryption")
        payload = decrypt_payload(payload, passphrase)
    return payload.decode("utf-8", errors="replace")


def run_receiver(cfg: BridgeConfig, decrypt: bool = False, passphrase: str | None = None, visualize: bool = True) -> None:
    """Continuously receive and decode BFSK stream.

    Error handling strategy:
    - Unknown frequencies are ignored (noise rejection).
    - Decode failures are reported but loop keeps running for subsequent frames.
    - Rolling buffer limits memory while keeping enough history for marker search.
    """
    chunk_size = cfg.samples_per_bit
    bit_buffer: Deque[str] = collections.deque(maxlen=12000)
    raw_scroll: Deque[str] = collections.deque(maxlen=120)

    plt.ion()
    fig, (ax_spec, ax_bits) = plt.subplots(2, 1, figsize=(10, 6)) if visualize else (None, (None, None))
    if visualize:
        spectrum_line, = ax_spec.plot([], [], lw=1.2)
        ax_spec.set_xlim(14000, 21000)
        ax_spec.set_ylim(0, 1)
        ax_spec.set_title("Live frequency spectrum")
        ax_spec.set_xlabel("Frequency (Hz)")
        ax_spec.set_ylabel("Normalized magnitude")
        bit_text = ax_bits.text(0.01, 0.5, "", family="monospace", fontsize=10)
        ax_bits.set_axis_off()
        ax_bits.set_title("Bitstream scrolling")

    print("\n=== AirGap Bridge Receiver ===")
    print(
        f"Listening with f0={cfg.freq_0:.1f}Hz, f1={cfg.freq_1:.1f}Hz, "
        f"tolerance=±{cfg.tolerance_hz:.1f}Hz"
    )
    print("Press Ctrl+C to stop.\n")

    with sd.InputStream(samplerate=cfg.sample_rate, channels=1, dtype="float32", blocksize=chunk_size) as stream:
        while True:
            data, overflowed = stream.read(chunk_size)
            if overflowed:
                print("[warn] audio overflow detected")

            chunk = data[:, 0]
            freq = detect_dominant_frequency(chunk, cfg.sample_rate)
            bit = frequency_to_bit(freq, cfg)

            if bit is not None:
                bit_buffer.append(bit)
                raw_scroll.append(bit)

            # Update live visualization
            if visualize:
                window = np.hanning(len(chunk))
                spectrum = np.abs(np.fft.rfft(chunk * window))
                freqs = np.fft.rfftfreq(len(chunk), d=1.0 / cfg.sample_rate)
                if np.max(spectrum) > 0:
                    spectrum = spectrum / np.max(spectrum)
                mask = (freqs >= 14000) & (freqs <= 21000)
                spectrum_line.set_data(freqs[mask], spectrum[mask])
                bit_text.set_text("".join(raw_scroll))
                fig.canvas.draw_idle()
                fig.canvas.flush_events()

            # Console status line with dominant freq and current bit
            latest_bits = "".join(list(raw_scroll)[-48:])
            print(f"\r{freq:8.1f} Hz | bit={bit or '-'} | {latest_bits}", end="", flush=True)

            # Try decode newest full frame (if markers found)
            frame = extract_latest_frame(bit_buffer)
            if frame:
                print("\nFrame detected. Attempting decode...")
                try:
                    msg = decode_frame(frame, decrypt=decrypt, passphrase=passphrase)
                    print(f"[decoded] {msg}\n")
                    bit_buffer.clear()
                    raw_scroll.clear()
                except Exception as exc:
                    print(f"[decode-error] {exc}\n")
                    bit_buffer.clear()
                    raw_scroll.clear()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AirGap Bridge BFSK receiver")
    p.add_argument("--bit-duration", type=float, default=0.1, help="Bit duration in seconds")
    p.add_argument("--sample-rate", type=int, default=44100, help="Sample rate")
    p.add_argument("--fallback-freq", action="store_true", help="Use fallback 16k/17k frequencies")
    p.add_argument("--tolerance", type=float, default=300.0, help="Frequency tolerance in Hz")
    p.add_argument("--calibrate", action="store_true", help="Run auto-calibration before receiving")
    p.add_argument("--decrypt", action="store_true", help="Decrypt AES-GCM payload")
    p.add_argument("--passphrase", help="Passphrase for AES decryption")
    p.add_argument("--no-plot", action="store_true", help="Disable matplotlib live visualization")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    f0, f1 = FALLBACK_FREQS if args.fallback_freq else PRIMARY_FREQS
    cfg = BridgeConfig(
        sample_rate=args.sample_rate,
        bit_duration=args.bit_duration,
        freq_0=f0,
        freq_1=f1,
        tolerance_hz=args.tolerance,
    )

    try:
        if args.calibrate:
            cfg = auto_calibrate(cfg)
        run_receiver(cfg, decrypt=args.decrypt, passphrase=args.passphrase, visualize=not args.no_plot)
    except KeyboardInterrupt:
        print("\nStopped by user.")
        return 0
    except Exception as exc:
        print(f"Receiver error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
