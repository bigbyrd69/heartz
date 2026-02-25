"""Tkinter chat-style app for AirGap Bridge ultrasonic messaging."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

import sounddevice as sd

from utils import (
    BridgeConfig,
    FALLBACK_FREQS,
    PRIMARY_FREQS,
    decrypt_payload,
    detect_dominant_frequency,
    extract_latest_frame,
    frame_message,
    frequency_to_bit,
    bits_to_waveform,
    unframe_message,
    encrypt_payload,
)


class ReceiverWorker(threading.Thread):
    """Background receiver thread that continuously decodes ultrasonic frames."""

    def __init__(self, cfg: BridgeConfig, out_queue: queue.Queue, stop_event: threading.Event, decrypt: bool, passphrase: str):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.decrypt = decrypt
        self.passphrase = passphrase

    def run(self) -> None:
        chunk_size = self.cfg.samples_per_bit
        bit_buffer: list[str] = []

        try:
            with sd.InputStream(
                samplerate=self.cfg.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=chunk_size,
            ) as stream:
                while not self.stop_event.is_set():
                    data, overflowed = stream.read(chunk_size)
                    if overflowed:
                        self.out_queue.put(("status", "Audio overflow detected"))

                    freq = detect_dominant_frequency(data[:, 0], self.cfg.sample_rate)
                    bit = frequency_to_bit(freq, self.cfg)
                    if bit is None:
                        continue

                    bit_buffer.append(bit)
                    if len(bit_buffer) > 12000:
                        bit_buffer = bit_buffer[-12000:]

                    self.out_queue.put(("bit", bit))
                    frame = extract_latest_frame(bit_buffer)
                    if not frame:
                        continue

                    try:
                        payload = unframe_message(frame)
                        if self.decrypt:
                            if not self.passphrase:
                                raise ValueError("Passphrase required for decryption")
                            payload = decrypt_payload(payload, self.passphrase)
                        message = payload.decode("utf-8", errors="replace")
                        self.out_queue.put(("message", message))
                    except Exception as exc:  # keep receiver alive
                        self.out_queue.put(("status", f"Decode error: {exc}"))
                    finally:
                        bit_buffer.clear()
        except Exception as exc:
            self.out_queue.put(("status", f"Receiver stopped: {exc}"))


class AirGapChatApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AirGap Bridge Chat")
        self.root.geometry("760x520")

        self.events: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.rx_thread: ReceiverWorker | None = None
        self.bit_scroll = ""

        self._build_ui()
        self.root.after(100, self._poll_events)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=8)

        self.freq_mode = tk.StringVar(value="primary")
        ttk.Label(top, text="Freq mode:").pack(side="left")
        ttk.Radiobutton(top, text="18/19k", variable=self.freq_mode, value="primary").pack(side="left", padx=4)
        ttk.Radiobutton(top, text="16/17k fallback", variable=self.freq_mode, value="fallback").pack(side="left", padx=4)

        self.decrypt_var = tk.BooleanVar(value=False)
        self.encrypt_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text="Encrypt sends", variable=self.encrypt_var).pack(side="left", padx=8)
        ttk.Checkbutton(top, text="Decrypt receives", variable=self.decrypt_var).pack(side="left", padx=8)

        ttk.Label(top, text="Passphrase:").pack(side="left", padx=(12, 2))
        self.passphrase = ttk.Entry(top, width=18, show="*")
        self.passphrase.pack(side="left")

        controls = ttk.Frame(self.root)
        controls.pack(fill="x", padx=10)
        ttk.Button(controls, text="Start Listening", command=self.start_receiver).pack(side="left")
        ttk.Button(controls, text="Stop Listening", command=self.stop_receiver).pack(side="left", padx=8)

        self.status = tk.StringVar(value="Idle")
        ttk.Label(controls, textvariable=self.status).pack(side="left", padx=12)

        self.chat_log = scrolledtext.ScrolledText(self.root, height=19, state="disabled")
        self.chat_log.pack(fill="both", expand=True, padx=10, pady=8)

        bit_frame = ttk.LabelFrame(self.root, text="Live received bitstream (tail)")
        bit_frame.pack(fill="x", padx=10)
        self.bit_var = tk.StringVar(value="")
        ttk.Label(bit_frame, textvariable=self.bit_var, font=("Courier", 9)).pack(fill="x", padx=6, pady=4)

        compose = ttk.Frame(self.root)
        compose.pack(fill="x", padx=10, pady=8)
        self.message_entry = ttk.Entry(compose)
        self.message_entry.pack(side="left", fill="x", expand=True)
        self.message_entry.bind("<Return>", lambda _e: self.send_message())
        ttk.Button(compose, text="Send", command=self.send_message).pack(side="left", padx=6)

    def _cfg(self) -> BridgeConfig:
        f0, f1 = PRIMARY_FREQS if self.freq_mode.get() == "primary" else FALLBACK_FREQS
        return BridgeConfig(freq_0=f0, freq_1=f1)

    def append_log(self, line: str) -> None:
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", line + "\n")
        self.chat_log.see("end")
        self.chat_log.configure(state="disabled")

    def start_receiver(self) -> None:
        if self.rx_thread and self.rx_thread.is_alive():
            return
        self.stop_event.clear()
        self.rx_thread = ReceiverWorker(
            cfg=self._cfg(),
            out_queue=self.events,
            stop_event=self.stop_event,
            decrypt=self.decrypt_var.get(),
            passphrase=self.passphrase.get(),
        )
        self.rx_thread.start()
        self.status.set("Listening")
        self.append_log("[system] Receiver started")

    def stop_receiver(self) -> None:
        self.stop_event.set()
        self.status.set("Stopped")
        self.append_log("[system] Receiver stopped")

    def send_message(self) -> None:
        msg = self.message_entry.get().strip()
        if not msg:
            return

        cfg = self._cfg()
        try:
            payload = msg.encode("utf-8")
            if self.encrypt_var.get():
                phrase = self.passphrase.get()
                if not phrase:
                    raise ValueError("Passphrase is required when encryption is enabled")
                payload = encrypt_payload(payload, phrase)

            bits = frame_message(payload)
            waveform = bits_to_waveform(bits, cfg)
            duration = len(waveform) / cfg.sample_rate
            bitrate = cfg.bit_rate

            self.append_log(f"[me] {msg}")
            self.append_log(f"[system] TX {len(bits)} bits @ {bitrate:.1f} bps ({duration:.2f}s)")
            self.message_entry.delete(0, "end")

            threading.Thread(target=self._play_waveform, args=(waveform, cfg.sample_rate), daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Send error", str(exc))

    def _play_waveform(self, waveform, sample_rate: int) -> None:
        try:
            sd.play(waveform, sample_rate)
            sd.wait()
            self.events.put(("status", "Transmission complete"))
        except Exception as exc:
            self.events.put(("status", f"TX error: {exc}"))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break

            if kind == "message":
                self.append_log(f"[peer] {payload}")
            elif kind == "status":
                self.status.set(payload)
            elif kind == "bit":
                self.bit_scroll = (self.bit_scroll + payload)[-120:]
                self.bit_var.set(self.bit_scroll)

        self.root.after(100, self._poll_events)


def main() -> int:
    root = tk.Tk()
    app = AirGapChatApp(root)
    root.protocol("WM_DELETE_WINDOW", lambda: (app.stop_receiver(), root.destroy()))
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
