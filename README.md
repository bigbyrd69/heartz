# AirGap Bridge (Ultrasonic BFSK Chat + CLI)

AirGap Bridge is a Python prototype for text transfer between nearby laptops using **ultrasonic audio only** (no Wi-Fi/Bluetooth/network).

## What you get

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
