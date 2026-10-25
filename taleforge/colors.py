"""Interpretação de cores: nomes do rich, #RGB, #RGBA, #RRGGBB e #RRGGBBAA."""
from __future__ import annotations

import re

from rich.color import Color, ColorParseError

_HEX = re.compile(r"^#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def _rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def parse_color(value: str, background: str = "#000000") -> str:
    """Devolve uma cor aceita pelo rich. Cores com alfa são misturadas ao fundo.

    `#0fff` → ciano opaco; `#f008` → vermelho a ~53% sobre `background`.
    Levanta ValueError se a cor for inválida.
    """
    v = (value or "").strip()
    if not v:
        raise ValueError("cor vazia")
    if v.startswith("#"):
        m = _HEX.match(v)
        if not m:
            raise ValueError(f"cor hexadecimal inválida: {v}")
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        r, g, b = _rgb(h)
        alpha = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        if alpha < 1.0:
            br, bg_, bb = _rgb(background if _HEX.match(background) else "#000000")
            r, g, b = (round(c * alpha + k * (1 - alpha)) for c, k in ((r, br), (g, bg_), (b, bb)))
        return f"#{r:02x}{g:02x}{b:02x}"
    try:
        Color.parse(v)
    except ColorParseError as exc:
        raise ValueError(f"cor desconhecida: {v}") from exc
    return v
