"""Parser da marcação inline das notas (.md/.txt).

Sintaxe reconhecida:

    [atributo:valor]   abre/aplica uma diretiva        [color:#0fff]
    [atributo]         diretiva sem valor (flag)        [bold]
    [/atributo]        encerra a diretiva               [/color]
    [[destino|rótulo]] opção de menu (padrão Obsidian)  [[caverna|Entrar]]
    [[!hook arg|rótulo]] opção que dispara um hook      [[!acender_tocha|Acender]]
    ![[arte.txt]]      embute uma arte ASCII (estilo Obsidian)
    ```...```          bloco literal (arte ASCII escrita na própria nota)
    \\[                 colchete literal

Markdown básico (opcional): **negrito**, *itálico*, `código`, # título, > citação, ---.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

# ---------------------------------------------------------------- tokens


@dataclass(frozen=True)
class Text:
    text: str
    theme: str | None = None  # chave de [theme] (ex.: "option")


@dataclass(frozen=True)
class Tag:
    name: str          # nome canônico (aliases já resolvidos)
    value: str | None
    closing: bool = False
    raw: str = ""


@dataclass(frozen=True)
class Option:
    target: str        # nome de nota, ou "!hook args"
    label: str
    inline: bool = False  # True quando a opção aparece no meio de uma frase
    raw: str = ""

    @property
    def is_hook(self) -> bool:
        return self.target.startswith("!")


@dataclass(frozen=True)
class Embed:
    path: str
    raw: str = ""


@dataclass(frozen=True)
class Literal:
    text: str


Token = Text | Tag | Option | Embed | Literal

# ---------------------------------------------------------------- regex

TOKEN_RE = re.compile(
    r"""
    (?P<embed>!\[\[(?P<embed_body>[^\[\]\n]+?)\]\])
  | (?P<option>\[\[(?P<opt_body>[^\[\]\n]+?)\]\])
  | (?P<tag>\[(?P<close>/?)(?P<name>[A-Za-z_][\w-]*)(?::(?P<value>[^\[\]\n]*))?\])
    """,
    re.X,
)
FENCE_RE = re.compile(r"^```[^\n]*\n(.*?)^```[ \t]*$\n?", re.S | re.M)
OPT_ONLY_RE = re.compile(r"\s*(?:\[\[[^\[\]\n]+?\]\]\s*)+")
COMMENT_RE = re.compile(r"%%.*?%%", re.S)

_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITAL_STAR = re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])")
_ITAL_UND = re.compile(r"(?<![\w_])_(?=[^\s_])(.+?)(?<=[^\s_])_(?![\w_])")
_CODE = re.compile(r"`([^`\n]+)`")
_HEAD = re.compile(r"^#{1,6}\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_ESC = "\x01"


def make_option(body: str, inline: bool = False, raw: str = "") -> Option:
    """`[[destino|rótulo]]`; sem `|` o rótulo é o próprio destino."""
    target, sep, label = body.partition("|")
    target = target.strip()
    label = label.strip() if sep else ""
    if target.startswith("!"):
        label = label or target[1:].split(" ", 1)[0]
    else:
        target = target.split("#", 1)[0].strip() or target  # ignora âncora de seção
        label = label or body.partition("|")[0].strip()
    return Option(target, label, inline, raw or f"[[{body}]]")


def _markdown_inline(line: str) -> str:
    """Converte markdown inline em tags da engine, preservando tags existentes."""
    saved: list[str] = []

    def keep(m: re.Match) -> str:
        saved.append(m.group(0))
        return f"\x00{len(saved) - 1}\x00"

    line = TOKEN_RE.sub(keep, line)
    line = _CODE.sub(r"[style:code]\1[/style]", line)
    line = _BOLD.sub(r"[bold]\2[/bold]", line)
    line = _ITAL_STAR.sub(r"[italic]\1[/italic]", line)
    line = _ITAL_UND.sub(r"[italic]\1[/italic]", line)
    return re.sub(r"\x00(\d+)\x00", lambda m: saved[int(m.group(1))], line)


def _markdown_line(line: str) -> str:
    if _RULE.match(line):
        return "[rule]"
    if m := _HEAD.match(line):
        return f"[style:heading]{_markdown_inline(m.group(1))}[/style]"
    if m := _QUOTE.match(line):
        return f"[style:quote]{_markdown_inline(m.group(1))}[/style]"
    return _markdown_inline(line)


def _tokenize_line(
    line: str,
    known: Callable[[str], str | None],
    ascii_exts: tuple[str, ...],
    unknown: list[str] | None,
) -> list[Token]:
    out: list[Token] = []
    pos = 0

    def add_text(s: str) -> None:
        if s:
            out.append(Text(s.replace(_ESC, "[")))

    for m in TOKEN_RE.finditer(line):
        add_text(line[pos : m.start()])
        pos = m.end()
        if m.group("embed"):
            path = m.group("embed_body").split("|")[0].strip()
            if path.lower().endswith(ascii_exts):
                out.append(Embed(path, m.group(0)))
            else:
                add_text(m.group(0))
        elif m.group("option"):
            out.append(make_option(m.group("opt_body"), inline=True, raw=m.group(0)))
        else:
            canonical = known(m.group("name"))
            if canonical is None:
                if m.group("value") is not None and unknown is not None:
                    unknown.append(m.group("name"))
                add_text(m.group(0))
            else:
                out.append(
                    Tag(canonical, (m.group("value") or "").strip() or None,
                        bool(m.group("close")), m.group(0))
                )
    add_text(line[pos:])
    return out


def _parse_plain(body, known, markdown, ascii_exts, unknown) -> list[Token]:
    tokens: list[Token] = []
    lines = body.split("\n")
    for i, raw_line in enumerate(lines):
        last = i == len(lines) - 1
        line = raw_line.replace("\\[", _ESC)
        if OPT_ONLY_RE.fullmatch(line):  # linha só com opções: vira item de menu
            for m in re.finditer(r"\[\[([^\[\]\n]+?)\]\]", line):
                tokens.append(make_option(m.group(1), inline=False, raw=m.group(0)))
            continue
        if markdown:
            line = _markdown_line(line)
        tokens.extend(_tokenize_line(line, known, ascii_exts, unknown))
        if not last:
            tokens.append(Text("\n"))
    return tokens


def parse_note(
    body: str,
    known: Callable[[str], str | None],
    *,
    markdown: bool = True,
    ascii_exts: tuple[str, ...] = (".txt", ".ans", ".asc", ".art"),
    unknown: list[str] | None = None,
) -> list[Token]:
    """Converte o corpo de uma nota em tokens.

    `known(nome)` devolve o nome canônico da diretiva ou None se não existir
    (tags desconhecidas permanecem como texto literal).
    """
    body = COMMENT_RE.sub("", body.replace("\r\n", "\n")).strip("\n")
    tokens: list[Token] = []
    pos = 0
    for m in FENCE_RE.finditer(body):
        tokens.extend(_parse_plain(body[pos : m.start()], known, markdown, ascii_exts, unknown))
        tokens.append(Literal(m.group(1).rstrip("\n")))
        pos = m.end()
    tokens.extend(_parse_plain(body[pos:], known, markdown, ascii_exts, unknown))
    # remove linhas em branco entre o texto e o bloco final de opções
    end = len(tokens)
    while end > 0 and isinstance(tokens[end - 1], Option) and not tokens[end - 1].inline:
        end -= 1
    start = end
    while start > 0 and isinstance(tokens[start - 1], Text) and not tokens[start - 1].text.strip():
        start -= 1
    del tokens[start:end]
    while tokens and isinstance(tokens[-1], Text) and not tokens[-1].text.strip():
        tokens.pop()
    return tokens


def options_of(tokens: list[Token]) -> list[Option]:
    return [t for t in tokens if isinstance(t, Option)]
