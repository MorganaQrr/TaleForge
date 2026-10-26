"""Renderização em TTY: typewriter, estilos, tremor, pausas e arte ASCII."""
from __future__ import annotations

import random
import re
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.console import COLOR_SYSTEMS
from rich.style import Style

from . import input as keys
from .markup import Embed, Literal, Option, Tag, Text, Token
from .paths import resolve_asset

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Engine

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@dataclass
class TextState:
    """Estilo corrente aplicado ao texto que está sendo digitado."""

    color: str | None = None
    bg: str | None = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    dim: bool = False
    strike: bool = False
    speed: float = 1.0   # multiplicador da velocidade base (0 = instantâneo)
    shake: int = 0       # amplitude do tremor, em colunas

    def reset(self) -> None:
        self.__init__()  # type: ignore[misc]

    def style(self) -> Style:
        return Style(color=self.color, bgcolor=self.bg, bold=self.bold or None,
                     italic=self.italic or None, underline=self.underline or None,
                     dim=self.dim or None, strike=self.strike or None)


@dataclass
class RenderContext:
    engine: "Engine"
    renderer: "Renderer"
    state: TextState = field(default_factory=TextState)
    note: object | None = None

    def apply(self, name: str, value: str | None = None, closing: bool = False) -> None:
        spec = self.engine.registry.resolve(name)
        if spec is None:
            self.engine.warn(f"diretiva desconhecida: {name}")
            return
        spec.fn(self, value, closing)


class Renderer:
    def __init__(self, engine: "Engine"):
        self.engine = engine
        self.console = engine.console
        self.skip = False
        self.col = 0
        self.line: list[tuple[str, Style]] = []
        self.last_char = "\n"

    # ---------------------------------------------------------- propriedades
    @property
    def cfg(self):
        return self.engine.config

    @property
    def instant(self) -> bool:
        return bool(self.cfg.get("text.instant", False))

    @property
    def interactive(self) -> bool:
        return self.console.is_terminal and keys.is_interactive() and not self.instant

    @property
    def base_cps(self) -> float:
        return max(float(self.cfg.get("text.type_speed", 45.0)), 0.1)

    @property
    def width(self) -> int:
        term = max(self.console.width, 20)
        limit = int(self.cfg.get("text.max_width", 0) or 0)
        width = min(term, limit) if limit > 0 else term
        return max(width - 1 - int(self.cfg.get("effects.max_shake", 3)), 10)

    def theme(self, name: str) -> Style:
        try:
            return Style.parse(str(self.cfg.get(f"theme.{name}", "") or ""))
        except Exception:
            return Style()

    # ------------------------------------------------------------ saída bruta
    def write(self, s: str) -> None:
        out = self.console.file
        out.write(s)
        out.flush()

    def paint(self, text: str, style: Style) -> str:
        return style.render(text, color_system=COLOR_SYSTEMS.get(self.console.color_system or ""))

    def sleep(self, seconds: float, skippable: bool = True) -> None:
        if seconds <= 0 or self.instant or self.skip:
            return
        if skippable and self.cfg.get("text.skippable", True) and keys.is_interactive():
            if keys.poll_key(seconds) is not None:
                self.skip = True
            return
        time.sleep(seconds)

    def newline(self) -> None:
        self.write("\n")
        self.col, self.line, self.last_char = 0, [], "\n"

    def ensure_newline(self) -> None:
        if self.col > 0:
            self.newline()

    def clear(self) -> None:
        if self.interactive:
            self.write("\x1b[2J\x1b[H")
        else:
            self.ensure_newline()
        self.col, self.line, self.last_char = 0, [], "\n"

    def begin_note(self) -> None:
        self.skip = False
        self.ensure_newline()

    def _put(self, ch: str, style: Style) -> None:
        self.write(self.paint(ch, style))
        self.line.append((ch, style))
        self.col += 1
        self.last_char = ch

    # ---------------------------------------------------------------- texto
    def _pause_after(self, text: str, i: int) -> float:
        ch = text[i]
        pauses = self.cfg.get("text.pauses", {}) or {}
        if ch not in pauses:
            return 0.0
        nxt = text[i + 1] if i + 1 < len(text) else " "
        return float(pauses[ch]) if (nxt.isspace() or ch == "\n") else 0.0

    def type_text(self, text: str, state: TextState, theme: str | None = None) -> None:
        style = self.theme(theme) if theme else state.style()
        speed = state.speed
        per_char = 0.0 if speed <= 0 else 1.0 / (self.base_cps * speed)
        jitter = float(self.cfg.get("text.jitter", 0.25))
        n, i = len(text), 0
        while i < n:
            ch = text[i]
            if ch == "\n":
                self.newline()
                self.sleep(self._pause_after(text, i) * (1 / speed if speed > 0 else 0))
                i += 1
                continue
            prev = text[i - 1] if i > 0 else self.last_char
            if not ch.isspace() and prev.isspace():  # início de palavra: quebra de linha
                j = i
                while j < n and not text[j].isspace():
                    j += 1
                if self.col > 0 and self.col + (j - i) > self.width:
                    self.newline()
            elif ch.isspace() and self.col >= self.width:
                self.newline()
                i += 1
                continue
            self._put(ch, style)
            if per_char:
                self.sleep(per_char * random.uniform(1 - jitter, 1 + jitter) + self._pause_after(text, i))
            i += 1
        if state.shake:
            self.jitter(state.shake)

    def jitter(self, amplitude: int) -> None:
        """Faz a linha atual tremer (deslocamento horizontal aleatório)."""
        if not self.interactive or amplitude <= 0 or not self.line or self.skip:
            return
        amp = min(int(amplitude), int(self.cfg.get("effects.max_shake", 3)))
        frames = int(self.cfg.get("effects.shake_frames", 14))
        interval = float(self.cfg.get("effects.shake_interval", 0.03))
        for _ in range(frames):
            self._redraw(random.randint(0, amp))
            self.sleep(interval, skippable=True)
            if self.skip:
                break
        self._redraw(0)

    def _redraw(self, offset: int) -> None:
        parts: list[str] = []
        buf, cur = "", None
        for ch, st in self.line:
            if st != cur and buf:
                parts.append(self.paint(buf, cur))  # type: ignore[arg-type]
                buf = ""
            cur, buf = st, buf + ch
        if buf:
            parts.append(self.paint(buf, cur))  # type: ignore[arg-type]
        self.write("\r\x1b[2K" + " " * offset + "".join(parts))

    # ------------------------------------------------------ blocos e ASCII
    def print_block(self, text: str, style: Style, mode: str | None = None,
                    align: str = "left") -> None:
        """Imprime um bloco pré-formatado (arte ASCII) linha a linha, sem quebrar."""
        self.ensure_newline()
        mode = mode or str(self.cfg.get("ascii.mode", "line"))
        delay = float(self.cfg.get("ascii.line_delay", 0.04))
        lines = text.split("\n")
        widest = max((len(_ANSI_RE.sub("", ln)) for ln in lines), default=0)
        pad = 0
        if align in ("center", "right"):
            pad = max(self.console.width - widest, 0)
            pad = pad // 2 if align == "center" else pad
        for ln in lines:
            has_ansi = "\x1b[" in ln
            self.write(" " * pad + (ln if has_ansi else self.paint(ln, style)) + "\n")
            if mode == "line":
                self.sleep(delay)
        self.col, self.line, self.last_char = 0, [], "\n"

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove ``` de abertura/fechamento (arquivos .md feitos para o Obsidian)."""
        lines = text.split("\n")
        first = next((i for i, l in enumerate(lines) if l.strip()), None)
        if first is not None and lines[first].lstrip().startswith("```"):
            lines = lines[first + 1:]
        last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
        if last is not None and lines[last].strip() == "```":
            lines = lines[:last]
        return "\n".join(lines)

    def print_ascii(self, name: str, state: TextState, color: str | None = None,
                    align: str = "left", mode: str | None = None) -> None:
        path = resolve_asset(self.cfg, name, "ascii")
        if path is None:
            self.engine.warn(f"arte ASCII não encontrada: {name}")
            return
        text = path.read_text(encoding="utf-8", errors="replace").rstrip("\n")
        if path.suffix.lower() == ".md":
            text = self._strip_fences(text)
        if state.color or color:  # cor escolhida pela nota vence ANSI embutido
            text = _ANSI_RE.sub("", text)
        style = state.style()
        if color:
            style = style + Style(color=color)
        self.print_block(text, style, mode, align)
    def rule(self) -> None:
        self.ensure_newline()
        self.write(self.paint("─" * min(self.width, 60), self.theme("rule")) + "\n")

    def wait_key(self, label: str | None = None) -> None:
        if not keys.is_interactive() or self.instant:
            return
        prompt = " " + (label or str(self.cfg.get("text.wait_prompt", "▼")))
        self.write(self.paint(prompt, self.theme("dim")))
        keys.read_key()
        self.write("\b" * len(prompt) + " " * len(prompt) + "\b" * len(prompt))
        self.skip = False

    def error(self, message: str) -> None:
        self.ensure_newline()
        self.write(self.paint(message, self.theme("error")) + "\n")

    # --------------------------------------------------------------- tokens
    def render(self, tokens: list[Token], note: object | None = None,
               state: TextState | None = None) -> None:
        ctx = RenderContext(self.engine, self, state or TextState(), note)
        for tok in tokens:
            if self.engine.stop_rendering:
                break
            if isinstance(tok, Text):
                self.type_text(tok.text, ctx.state, tok.theme)
            elif isinstance(tok, Option):
                if tok.inline:
                    self.type_text(tok.label, ctx.state, "option")
            elif isinstance(tok, Embed):
                self.print_ascii(tok.path, ctx.state)
            elif isinstance(tok, Literal):
                self.print_block(tok.text, ctx.state.style())
            elif isinstance(tok, Tag):
                spec = self.engine.registry.resolve(tok.name)
                if spec is None:
                    continue
                try:
                    spec.fn(ctx, tok.value, tok.closing)
                except Exception as exc:  # uma diretiva ruim não derruba a cena
                    self.engine.warn(f"erro em {tok.raw}: {exc}")
