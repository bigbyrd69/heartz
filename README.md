# AirGap Bridge (Ultrasonic BFSK Chat + CLI)

AirGap Bridge is a Python prototype for text transfer between nearby laptops using **ultrasonic audio only** (no Wi-Fi/Bluetooth/network).

## What you get
# AirGap Bridge (Ultrasonic BFSK Prototype)

AirGap Bridge is a Python prototype for one-way text transfer between nearby laptops using **ultrasonic audio** only (no Wi-Fi/Bluetooth/network).

## Features

- BFSK modulation:
  - `18000 Hz` => bit `0`
  - `19000 Hz` => bit `1`
- Fallback mode: `16000/17000 Hz`
- Configurable bit duration (default `0.1 s`) at `44100 Hz`
- Frame markers:
  - `START_MARKER = 11111110`
  - `END_MARKER   = 01111111`
- XOR checksum validation
- Optional AES-GCM encryption/decryption
- Receiver auto-calibration mode
- Live spectrum visualization + scrolling bitstream (receiver CLI)
- **Installable chat-style app** (`airgap-chat`) for quick send/receive usage

## Files

- `sender.py` — CLI sender
- `receiver.py` — CLI receiver
- `chat_app.py` — GUI chat-style app
- `utils.py` — protocol, crypto, and signal helpers
- `pyproject.toml` — installable package config + app entry points

## Install

### Option A (recommended): install app commands

```bash
python -m pip install .
```

This installs these commands:

- `airgap-chat` (GUI app)
- `airgap-sender` (CLI sender)
- `airgap-receiver` (CLI receiver)

### Option B: run directly from source

```bash
python sender.py --message "hello"
python receiver.py --calibrate
python chat_app.py
```

## Start talking (chat app)

1. On **both laptops**, run:

```bash
airgap-chat
```

2. Click **Start Listening** on both sides.
3. Type a message and press **Send**.
4. Received messages appear as `[peer] ...`.

Tips:
- If ultrasonic hardware is weak, switch to **16/17k fallback** in the UI.
- If using encryption, enable encrypt/decrypt and set the same passphrase on both sides.

## CLI usage (advanced)

### Receiver machine first

```bash
airgap-receiver --calibrate
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
airgap-receiver --fallback-freq
airgap-receiver --tolerance 350
airgap-receiver --no-plot
airgap-receiver --decrypt --passphrase "my secret"
```

### Sender machine

```bash
airgap-sender --message "Hello from AirGap Bridge"
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
airgap-sender --message "Secret" --encrypt --passphrase "my secret"
airgap-sender --fallback-freq --message "Fallback frequencies"
airgap-sender --bit-duration 0.08 --message "Faster bits"
```

## Protocol summary

1. UTF-8 encode message bytes.
2. Optionally AES-GCM encrypt payload.
3. Append XOR checksum byte.
4. Add start/end markers.
5. Modulate each bit to sine tone segment (BFSK).
6. Receiver FFT-detects dominant freq each bit window.
7. Map freq to bits (± tolerance), reconstruct frame, verify checksum, decode text.

## Notes / limitations

- Laptop microphones/speakers vary significantly above 16 kHz.
- This is a prototype (no FEC/retransmit protocol yet).
- Keep devices relatively close and reduce high-frequency ambient noise.
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
