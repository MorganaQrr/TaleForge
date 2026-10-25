import io
import os
import sys
import wave
import struct
from pathlib import Path

import pytest

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console  # noqa: E402


def make_wav(path: Path, seconds: float = 0.3, rate: int = 11025) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * ((i // 20) % 2 * 2 - 1)))
                               for i in range(int(rate * seconds))))
    return path


@pytest.fixture
def project(tmp_path):
    """Cria um projeto só com .md + assets (sem config.toml, sem código)."""
    (tmp_path / "content").mkdir()
    (tmp_path / "content" / "inicio.md").write_text(
        "# Título\n\n[color:#0fff]Olá[/color] **mundo**.\n\n![[arte.txt]]\n\n"
        "[[sala|Ir à sala]]\n[[!quit|Sair]]\n", encoding="utf-8")
    (tmp_path / "content" / "sala.md").write_text(
        "Você está na sala.\n\n[[inicio|Voltar]]\n", encoding="utf-8")
    (tmp_path / "assets" / "ascii").mkdir(parents=True)
    (tmp_path / "assets" / "ascii" / "arte.txt").write_text("/\\_/\\\n( o.o )\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def console():
    buf = io.StringIO()
    return Console(file=buf, force_terminal=False, width=80, highlight=False), buf
