"""Menu navegável de opções (setas, números, Enter) com fallback para stdin."""
from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from . import input as keys
from .markup import Option

if TYPE_CHECKING:  # pragma: no cover
    from .engine import Engine


def choose(engine: "Engine", options: list[Option]) -> int | str:
    """Devolve o índice escolhido ou "back" | "reload" | "quit"."""
    if keys.is_interactive():
        return _choose_tty(engine, options)
    return _choose_plain(engine, options)


def _choose_tty(engine: "Engine", options: list[Option]) -> int | str:
    r, cfg = engine.renderer, engine.config
    show_numbers = bool(cfg.get("menu.show_numbers", True))
    confirm_numbers = bool(cfg.get("menu.number_confirms", True))
    cursor = str(cfg.get("theme.menu_cursor", "▶"))
    hint = str(cfg.get("menu.hint", ""))
    item_style, sel_style = r.theme("menu_item"), r.theme("menu_selected")
    total = len(options) + (1 if hint else 0)

    def label(i: int, selected: bool) -> str:
        num = f"{i + 1}. " if show_numbers else ""
        mark = cursor if selected else " " * len(cursor)
        return r.paint(f"{mark} {num}{options[i].label}", sel_style if selected else item_style)

    def draw(sel: int, first: bool) -> None:
        if not first:
            r.write(f"\x1b[{total}A")
        for i in range(len(options)):
            r.write("\r\x1b[2K" + label(i, i == sel) + "\n")
        if hint:
            r.write("\r\x1b[2K" + r.paint(hint, r.theme("menu_hint")) + "\n")

    def finish(sel: int) -> int:
        r.write(f"\x1b[{total}A\r\x1b[J")
        r.write(label(sel, True) + "\n")
        r.col, r.line, r.last_char = 0, [], "\n"
        return sel

    r.ensure_newline()
    for _ in range(int(cfg.get("menu.spacing", 1))):
        r.newline()
    sel = 0
    draw(sel, True)
    while True:
        key = keys.read_key(on_idle=engine.poll_changed)
        if key in ("up", "k", "w"):
            sel = (sel - 1) % len(options)
        elif key in ("down", "j", "s"):
            sel = (sel + 1) % len(options)
        elif key in ("enter", "space"):
            return finish(sel)
        elif key == "backspace":
            r.write(f"\x1b[{total}A\r\x1b[J")
            return "back"
        elif key == "reload":
            r.write(f"\x1b[{total}A\r\x1b[J")
            return "reload"
        elif key.isdigit() and key != "0" and int(key) <= len(options):
            sel = int(key) - 1
            if confirm_numbers:
                return finish(sel)
        draw(sel, False)


def _choose_plain(engine: "Engine", options: list[Option]) -> int | str:
    r = engine.renderer
    out = engine.console.file
    r.ensure_newline()
    for _ in range(int(engine.config.get("menu.spacing", 1))):
        r.newline()
    for i, opt in enumerate(options, 1):
        out.write(f"  {i}. {opt.label}\n")
    while True:
        out.write("> ")
        out.flush()
        line = sys.stdin.readline()
        out.write("\n")
        if line == "":
            return "quit"
        line = line.strip()
        if line.isdigit() and 1 <= int(line) <= len(options):
            return int(line) - 1
        if line.lower() in ("q", "sair"):
            return "quit"
        if line.lower() in ("b", "voltar"):
            return "back"
