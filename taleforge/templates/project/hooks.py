"""Hooks do projeto: funções chamadas por `[[!nome arg|Rótulo]]` ou `[hook:nome arg]`.

Cada hook recebe `engine` + argumentos. O retorno importa:
  - str  → navega até a nota com esse nome
  - None → o menu continua na mesma cena

Hooks incluídos no template (apague o que não usar):
  !dado 20                        rola 1dN (aceita `d20` também)
  !ask_nome Como te chamas?       nome curto (≤20 chars, sem `[]`, não vazio)
  !eco chars.heroi.nome           imprime valor do `engine.state` (caminho pontilhado)
  !cor #c1f5ed                    cor padrão desta nota (use `nenhuma` p/ limpar)
  !init                           (vazio) ponto de entrada para setup global

`[[!ask var Pergunta?|Rótulo]]` e `[[!goto nota|Rótulo]]` continuam sendo os
embutidos da engine. NÃO redefina hooks com esses nomes sem saber o que faz —
`engine.hooks` é um dict e o último `@hook(...)` vence.
"""
import random
import sys

from taleforge import hook
from taleforge import input as keys
from taleforge.colors import parse_color


def _resolve_state(state, path: str):
    """Navega `a.b.c` ou `party.0.hp` no dicionário de estado.
    Devolve None se o caminho não existir (dict, lista ou tipo errado)."""
    node = state
    for part in path.split("."):
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, (list, tuple)):
            try:
                node = node[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return node


# ── Utilitários ────────────────────────────────────────────────────

@hook("dado")
def rolar_dado(engine, lados="6"):
    """[hook:dado 20] — rola 1dN. Aceita `d20`, `20`, `D20`."""
    raw = (lados or "6").strip().lower().lstrip("d") or "6"
    try:
        n = int(raw)
        if n < 2:
            raise ValueError
    except ValueError:
        engine.say(f"[color:#ff4455]dado inválido: {lados!r}[/color]")
        return
    engine.say(f"[dim]Você rola um d{n}:[/dim] [bold]{random.randint(1, n)}[/bold]")


@hook("eco")
def eco(engine, *parts):
    """[hook:eco chars.heroi.nome] — imprime um valor do estado.
    Ignora o resto da linha se o caminho não existir."""
    path = " ".join(parts).strip()
    val = _resolve_state(engine.state, path) if path else ""
    engine.say("" if val is None else str(val), newline=False)


@hook("cor")
def cor(engine, valor="nenhuma"):
    """[hook:cor #c1f5ed] — cor padrão do texto nesta nota.
    `nenhuma`, `none`, `reset` ou `padrao` limpa a cor padrão."""
    if valor.lower() in ("nenhuma", "none", "reset", "padrao"):
        engine.state.pop("cor_padrao", None)
        return
    bg = engine.config.get("theme.background", "#000000")
    try:
        engine.state["cor_padrao"] = parse_color(valor, bg)
    except Exception as exc:
        engine.warn(f"cor inválida {valor!r}: {exc}")


# ── Entrada do jogador ─────────────────────────────────────────────

@hook("ask_nome")
def ask_nome(engine, *palavras):
    """[hook:ask_nome Como te chamas?] — coleta um nome curto (≤20 chars).

    Não pergunta de novo se `nome` já está no estado (reload/back).
    Filtra `[` e `]` para o nome nunca virar marcação.
    Para texto longo use o `!ask` embutido (modo canônico, sem limite)."""
    if "nome" in engine.state:
        return
    r = engine.renderer
    engine.say(" ".join(palavras) + " ", newline=False)

    if not keys.is_interactive():
        text = sys.stdin.readline().strip()
    else:
        termios = getattr(keys, "termios", None)  # None em Windows
        if termios:
            try:
                termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
            except Exception:
                pass
        r.write("\x1b[?25h")  # mostra cursor
        buf: list[str] = []
        try:
            while True:
                key = keys.read_key()
                if key == "enter":
                    if buf:
                        break
                elif key == "backspace":
                    if buf:
                        buf.pop()
                        r.write("\b \b")
                elif key == "space":
                    if buf and len(buf) < 20:
                        buf.append(" ")
                        r.write(" ")
                elif len(key) == 1 and len(buf) < 20:
                    buf.append(key)
                    r.write(key)
        finally:
            r.write("\x1b[?25l")
        text = "".join(buf).strip()

    r.newline()
    engine.state["nome"] = text.replace("[", "").replace("]", "")
    engine.say(f"[dim]Prazer, {engine.state['nome']}.[/dim]")


# ── Exemplos descomentados para adaptar ────────────────────────────

@hook("init")
def init(engine):
    """Chamado uma vez quando a engine sobe. Setup global vai aqui.
    Descomente para adicionar um "Menu" permanente em todas as notas."""
    # engine.add_option("Menu", "menu", engine.global_options)
    # engine.add_option("Personagem", "personagem_menu", engine.global_options)
    pass


# @hook("pegar_chave")
# def pegar_chave(engine):
#     """[[!pegar_chave|Pegar a chave]] — pega item e navega para uma nota."""
#     if engine.state.get("tem_chave"):
#         engine.say("[dim]Você já tem a chave.[/dim]")
#         return None
#     engine.state["tem_chave"] = True
#     engine.audio.soundFX("chave.wav")     # arquivo em assets/audio/
#     engine.say("[color:#fa0]Você pega a chave.[/color]")
#     return "caverna"                       # navega para content/caverna.md
