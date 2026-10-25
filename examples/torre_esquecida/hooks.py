"""Hooks da Torre Esquecida: mostram estado do jogo (engine.state) e navegação por hook."""
from taleforge import hook


@hook("pegar_tocha")
def pegar_tocha(engine):
    if engine.state.get("tocha"):
        engine.say("[dim]Você já está com a tocha.[/dim]")
        return None
    engine.state["tocha"] = True
    engine.audio.soundFX("passos.wav", volume=0.4)
    engine.say("Você acende a tocha. [color:#fa0]A luz dança nas paredes.[/color]")
    return None  # continua no mesmo menu


@hook("tentar_porta")
def tentar_porta(engine):
    if engine.state.get("tocha"):
        return "porao"        # devolver um nome de nota navega até ela
    engine.say("[style:sussurro]Escuro demais para achar a fechadura...[/style]")
    return None


@hook("inventario")
def inventario(engine):
    itens = [k for k, v in engine.state.items() if v] or ["nada"]
    engine.say("[dim]Inventário:[/dim] " + ", ".join(itens))
