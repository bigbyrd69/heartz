"""AirGap Bridge sender: encode text as BFSK ultrasonic tones and transmit over speakers."""

from __future__ import annotations

import argparse
import sys
import time

import sounddevice as sd

from utils import (
    BridgeConfig,
    FALLBACK_FREQS,
    PRIMARY_FREQS,
    bits_to_waveform,
    encrypt_payload,
    frame_message,
)


def build_payload(message: str, encrypt: bool, passphrase: str | None) -> bytes:
    payload = message.encode("utf-8")
    if encrypt:
        if not passphrase:
            raise ValueError("--passphrase is required when --encrypt is enabled")
        payload = encrypt_payload(payload, passphrase)
    return payload


def transmit(message: str, cfg: BridgeConfig, encrypt: bool = False, passphrase: str | None = None) -> None:
    payload = build_payload(message, encrypt=encrypt, passphrase=passphrase)
    framed_bits = frame_message(payload)
    waveform = bits_to_waveform(framed_bits, cfg)

    total_bits = len(framed_bits)
    duration_s = len(waveform) / cfg.sample_rate
    print("\n=== AirGap Bridge Sender ===")
    print(f"Payload bytes: {len(payload)}")
    print(f"Total bits (incl. markers+checksum): {total_bits}")
    print(f"Configured bit rate: {cfg.bit_rate:.2f} bps")
    print(f"Estimated TX time: {duration_s:.2f} s")

    # Display progress during playback by polling elapsed stream time.
    start_time = time.time()
    sd.play(waveform, cfg.sample_rate)
    while sd.get_stream().active:
        elapsed = time.time() - start_time
        sent_bits = min(int(elapsed / cfg.bit_duration), total_bits)
        pct = (sent_bits / total_bits) * 100.0 if total_bits else 100.0
        print(
            f"\rTransmitting: {sent_bits}/{total_bits} bits ({pct:5.1f}%)",
            end="",
            flush=True,
        )
        time.sleep(0.05)

    sd.wait()
    print("\nTransmission complete.")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="AirGap Bridge BFSK sender")
    p.add_argument("--message", "-m", help="Message to transmit. If omitted, prompt interactively.")
    p.add_argument("--bit-duration", type=float, default=0.1, help="Bit duration in seconds")
    p.add_argument("--sample-rate", type=int, default=44100, help="Sample rate")
    p.add_argument("--fallback-freq", action="store_true", help="Use fallback 16k/17k frequencies")
    p.add_argument("--encrypt", action="store_true", help="Enable AES-GCM encryption")
    p.add_argument("--passphrase", help="Passphrase for AES encryption/decryption")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    message = args.message if args.message is not None else input("Enter message: ").strip()
    if not message:
        print("No message provided.", file=sys.stderr)
        return 1

    f0, f1 = FALLBACK_FREQS if args.fallback_freq else PRIMARY_FREQS
    cfg = BridgeConfig(
        sample_rate=args.sample_rate,
        bit_duration=args.bit_duration,
        freq_0=f0,
        freq_1=f1,
    )

    try:
        transmit(message, cfg, encrypt=args.encrypt, passphrase=args.passphrase)
    except Exception as exc:  # error handling surface for CLI users
        print(f"Sender error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
