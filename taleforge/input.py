"""Entrada de teclado em TTY (Linux/macOS): modo cbreak, polling e teclas especiais."""
from __future__ import annotations

import contextlib
import os
import select
import sys
import time
from typing import Callable, Iterator

try:
    import termios
    import tty
except ImportError:  # pragma: no cover - Windows
    termios = None  # type: ignore
    tty = None  # type: ignore

_SEQUENCES = {
    "\x1b[A": "up", "\x1b[B": "down", "\x1b[C": "right", "\x1b[D": "left",
    "\x1bOA": "up", "\x1bOB": "down", "\x1bOC": "right", "\x1bOD": "left",
}
_SINGLE = {"\r": "enter", "\n": "enter", "\x7f": "backspace", "\x08": "backspace",
           "\x1b": "esc", " ": "space"}


def is_interactive() -> bool:
    """True quando stdin e stdout são um terminal de verdade."""
    try:
        return bool(termios and sys.stdin.isatty() and sys.stdout.isatty())
    except (ValueError, OSError):
        return False


def _decode(data: str) -> str:
    for seq, name in _SEQUENCES.items():
        if data.startswith(seq):
            return name
    return _SINGLE.get(data[0], data[0])


def poll_key(timeout: float) -> str | None:
    """Espera até `timeout` s por uma tecla. Fora de TTY apenas dorme e devolve None."""
    if not is_interactive():
        if timeout > 0:
            time.sleep(timeout)
        return None
    fd = sys.stdin.fileno()
    ready, _, _ = select.select([fd], [], [], max(timeout, 0))
    if not ready:
        return None
    data = os.read(fd, 32).decode("utf-8", "ignore")
    return _decode(data) if data else None


def read_key(on_idle: Callable[[], bool] | None = None, interval: float = 0.2) -> str:
    """Bloqueia até uma tecla. Se `on_idle()` devolver True, retorna "reload"."""
    while True:
        key = poll_key(interval)
        if key:
            return key
        if on_idle and on_idle():
            return "reload"


@contextlib.contextmanager
def terminal_session() -> Iterator[None]:
    """cbreak + cursor oculto durante a execução; restaura o terminal ao sair."""
    if not is_interactive():
        yield
        return
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write("\x1b[?25l")
        sys.stdout.flush()
        yield
    finally:
        termios.tcflush(fd, termios.TCIFLUSH)
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        sys.stdout.write("\x1b[?25h\x1b[0m")
        sys.stdout.flush()
