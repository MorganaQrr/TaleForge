"""Hooks do projeto: funções chamadas por `[[!nome arg|Rótulo]]` ou `[hook:nome arg]`.

Cada hook recebe a engine e os argumentos. Devolver o nome de uma nota
navega até ela; devolver None mantém o menu na tela.
"""
import sys
from taleforge import hook
from taleforge import input as keys
from taleforge.colors import parse_color





@hook("dado")
def rolar_dado(engine, lados="6"):
    import random

    engine.say(f"[dim]Você rola um d{lados}:[/dim] [bold]{random.randint(1, int(lados))}[/bold]")

@hook("ask")
def ask(engine, var, *palavras):
    if var in engine.state:        # já respondeu: não pergunta no reload/back
        return
    r = engine.renderer
    engine.say(" ".join(palavras) + " ", newline=False)

    if not keys.is_interactive():
        text = sys.stdin.readline().strip()
    else:
        if keys.termios:           # descarta teclas apertadas durante a animação
            keys.termios.tcflush(sys.stdin.fileno(), keys.termios.TCIFLUSH)
        r.write("\x1b[?25h")       # mostra o cursor
        buf: list[str] = []
        try:
            while True:
                key = keys.read_key()
                if key == "enter":
                    if buf:        # não aceita nome vazio
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
            r.write("\x1b[?25l")   # esconde de novo
        text = "".join(buf).strip()

    r.newline()
    engine.state[var] = text.replace("[", "").replace("]", "")


@hook("eco")
def eco(engine, var):
    engine.say(str(engine.state.get(var, "")), newline=False)


@hook("cor")
def cor(engine, valor="nenhuma"):
    if valor.lower() in ("nenhuma", "none", "reset", "padrao"):
        engine.state.pop("cor_padrao", None)
        return
    bg = engine.config.get("theme.background", "#000000")
    engine.state["cor_padrao"] = parse_color(valor, bg)
