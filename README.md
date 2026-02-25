# AirGap Bridge (Ultrasonic BFSK Prototype)

AirGap Bridge is a Python prototype for one-way text transfer between nearby laptops using **ultrasonic audio** only (no Wi-Fi/Bluetooth/network).

## Features

- BFSK modulation:
  - `18000 Hz` => bit `0`
  - `19000 Hz` => bit `1`
- Configurable bit duration (default `0.1 s`)
- Sample rate `44100 Hz`
- Framing protocol with markers:
  - `START_MARKER = 11111110`
  - `END_MARKER   = 01111111`
- XOR checksum byte for integrity validation
- Optional AES-GCM encryption (passphrase-based key derivation)
- Receiver auto-calibration mode for frequency drift
- Fallback frequency mode: `16000/17000 Hz`
- Live matplotlib spectrum + scrolling bitstream display

## Project structure

- `sender.py` — Converts text to framed bitstream, BFSK-modulates, and plays audio.
- `receiver.py` — Captures microphone audio, FFT-based frequency detection, frame decode.
- `utils.py` — Shared protocol, signal, checksum, and crypto helpers.

## Setup

1. Install Python 3.10+.
2. Install dependencies:

```bash
pip install numpy scipy sounddevice matplotlib cryptography
```

> `cryptography` is only required if you use `--encrypt` / `--decrypt`.

3. On Linux, ensure audio backend access (PulseAudio/ALSA/JACK as appropriate).

## How to run

Run on **two separate machines** (or two audio devices) in the same room.

### 1) Start receiver machine first

```bash
python receiver.py --calibrate
```

Common options:

```bash
python receiver.py --fallback-freq
python receiver.py --tolerance 350
python receiver.py --no-plot
python receiver.py --decrypt --passphrase "my secret"
```

### 2) Transmit from sender machine

```bash
python sender.py --message "Hello from AirGap Bridge"
```

Common options:

```bash
python sender.py --message "Secret" --encrypt --passphrase "my secret"
python sender.py --fallback-freq --message "Fallback frequencies test"
python sender.py --bit-duration 0.08 --message "Faster bits"
```

## Protocol notes

1. Sender UTF-8 encodes message bytes.
2. Optional AES-GCM encryption is applied to payload bytes.
3. Sender appends XOR checksum byte.
4. Sender frames payload bits with start/end markers.
5. Each bit is emitted as one tone segment of duration `bit_duration`.
6. Receiver processes `bit_duration` chunks with FFT and maps dominant frequency to bit.
7. Receiver searches for markers, reconstructs bytes, validates checksum, then UTF-8 decodes.

## Practical tuning tips

- Keep speaker and microphone close (0.2m–1m) and pointed toward each other.
- Reduce ambient high-frequency noise.
- If 18/19kHz fails on your hardware, use `--fallback-freq`.
- Increase tolerance modestly (e.g., 350–500Hz) for noisy channels.
- Increase bit duration (e.g., `0.12`) for improved robustness.

## Safety and limitations

- Not all laptop speakers/mics reproduce ultrasonic frequencies well.
- This is a prototype: no forward error correction and limited anti-noise protections.
- High-frequency playback may be uncomfortable for some people/animals; test responsibly.
