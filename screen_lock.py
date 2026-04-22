from __future__ import annotations

import queue
import threading
import tkinter as tk
from typing import Optional

import mss


class ScreenLockController:
    """
    App-level remote screen lock for the sender machine.

    It is intentionally reversible with an "unlock" command and does not try
    to replace the Windows secure workstation lock screen.
    """

    def __init__(self) -> None:
        self._thread: Optional[threading.Thread] = None
        self._command_queue: "queue.Queue[str]" = queue.Queue()
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._ready.clear()
        self._thread = threading.Thread(
            target=self._ui_thread,
            daemon=True,
            name="ScreenLockController",
        )
        self._thread.start()
        self._ready.wait(timeout=5)

    def lock(self) -> None:
        self.start()
        self._command_queue.put("lock")

    def unlock(self) -> None:
        self.start()
        self._command_queue.put("unlock")

    def stop(self) -> None:
        if self._thread is None:
            return

        self._command_queue.put("stop")
        self._thread.join(timeout=3)
        self._thread = None

    def _ui_thread(self) -> None:
        root = tk.Tk()
        root.withdraw()
        windows: list[tk.Toplevel] = []

        def process_commands() -> None:
            while True:
                try:
                    command = self._command_queue.get_nowait()
                except queue.Empty:
                    break

                if command == "lock":
                    self._show_overlay(root, windows)
                elif command == "unlock":
                    self._hide_overlay(windows)
                elif command == "stop":
                    self._hide_overlay(windows)
                    root.quit()
                    root.destroy()
                    return

            root.after(100, process_commands)

        self._ready.set()
        root.after(100, process_commands)
        root.mainloop()

    def _show_overlay(self, root: tk.Tk, windows: list[tk.Toplevel]) -> None:
        if windows:
            for window in windows:
                window.lift()
                window.focus_force()
            return

        with mss.mss() as sct:
            monitors = sct.monitors[1:] or sct.monitors[:1]

        for monitor in monitors:
            window = tk.Toplevel(root)
            window.overrideredirect(True)
            window.configure(bg="black")
            window.attributes("-topmost", True)
            window.geometry(
                f"{monitor['width']}x{monitor['height']}+{monitor['left']}+{monitor['top']}"
            )
            window.protocol("WM_DELETE_WINDOW", lambda: None)
            window.bind("<Escape>", lambda event: "break")
            window.bind("<Alt-F4>", lambda event: "break")
            window.bind("<Key>", lambda event: "break")
            window.bind("<Button>", lambda event: "break")
            window.bind("<Motion>", lambda event: "break")

            frame = tk.Frame(window, bg="black")
            frame.pack(fill="both", expand=True)

            title = tk.Label(
                frame,
                text="EKRAN ZABLOKOWANY",
                fg="white",
                bg="black",
                font=("Segoe UI", 30, "bold"),
            )
            title.pack(pady=(120, 20))

            subtitle = tk.Label(
                frame,
                text="Dostep tymczasowo zablokowany przez administratora.",
                fg="white",
                bg="black",
                font=("Segoe UI", 16),
            )
            subtitle.pack()

            window.focus_force()
            window.lift()
            windows.append(window)

    @staticmethod
    def _hide_overlay(windows: list[tk.Toplevel]) -> None:
        while windows:
            window = windows.pop()
            try:
                window.destroy()
            except tk.TclError:
                pass
