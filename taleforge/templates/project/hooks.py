"""Hooks do projeto: funções chamadas por `[[!nome arg|Rótulo]]` ou `[hook:nome arg]`.

Cada hook recebe a engine e os argumentos. Devolver o nome de uma nota
navega até ela; devolver None mantém o menu na tela.
"""
from taleforge import hook


@hook("dado")
def rolar_dado(engine, lados="6"):
    import random

    engine.say(f"[dim]Você rola um d{lados}:[/dim] [bold]{random.randint(1, int(lados))}[/bold]")
