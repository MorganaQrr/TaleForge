import io
import sys

from taleforge import Engine
from taleforge.check import check_project
from taleforge.config import Config, deep_merge


def run(project, console, stdin_text, **kw):
    cons, buf = console
    sys.stdin = io.StringIO(stdin_text)
    try:
        eng = Engine(project, console=cons, instant=True, audio=False, **kw)
        eng.run()
    finally:
        sys.stdin = sys.__stdin__
    return eng, buf.getvalue()


def test_new_project_needs_only_md_and_assets(project, console):
    """Critério de aceite: nenhum código, nenhum config — só .md + assets."""
    assert not (project / "config.toml").exists()
    eng, out = run(project, console, "1\n1\n2\n")
    assert "Olá mundo." in out
    assert "( o.o )" in out            # ASCII carregada de assets/ascii
    assert "Você está na sala." in out  # navegou para outra nota
    assert eng.history == ["inicio", "sala"]  # inicio → sala → inicio


def test_defaults_merge_and_override(project):
    (project / "config.toml").write_text('[text]\ntype_speed = 99\n[project]\nstart="sala"\n')
    cfg = Config.load(project)
    assert cfg.get("text.type_speed") == 99
    assert cfg.get("text.jitter") == 0.25           # padrão preservado
    assert cfg.get("project.start") == "sala"
    assert deep_merge({"a": {"b": 1}}, {"a": {"c": 2}}) == {"a": {"b": 1, "c": 2}}


def test_yaml_config(project):
    (project / "settings.yaml").write_text("project:\n  start: sala\n")
    assert Config.load(project).get("project.start") == "sala"


def test_hooks_goto_and_state(project, console):
    (project / "hooks.py").write_text(
        "from taleforge import hook\n"
        "@hook('abrir')\n"
        "def abrir(engine, nome):\n"
        "    engine.state['aberto'] = nome\n"
        "    return 'sala'\n")
    (project / "content" / "inicio.md").write_text("Início\n\n[[!abrir cofre|Abrir]]\n")
    eng, out = run(project, console, "1\n1\n")
    assert eng.state["aberto"] == "cofre"
    assert "Você está na sala." in out


def test_plugin_directive_via_config(project, console):
    (project / "meuplugin.py").write_text(
        "from taleforge import directive\n"
        "@directive('eco')\n"
        "def eco(ctx, value, closing):\n"
        "    ctx.renderer.type_text(value.upper(), ctx.state)\n")
    (project / "config.toml").write_text('[plugins]\nmodules=["meuplugin"]\n')
    (project / "content" / "inicio.md").write_text("[eco:oi]\n\n[[!quit|Sair]]\n")
    _, out = run(project, console, "1\n")
    assert "OI" in out


def test_aliases_and_disabled_directives(project, console):
    (project / "config.toml").write_text('[directives]\ndisabled=["color"]\n')
    (project / "content" / "inicio.md").write_text("[cor:red]a[/cor] [color:red]b\n\n[[!quit|x]]\n")
    _, out = run(project, console, "1\n")
    assert "[color:red]" in out  # desativada → literal
    assert "[cor:red]" in out      # o alias "cor" resolve para color, que está desativada


def test_goto_and_end_directives(project, console):
    (project / "content" / "inicio.md").write_text("Um [goto:sala]\n")
    _, out = run(project, console, "")
    assert "Você está na sala." in out


def test_missing_note_does_not_crash(project, console):
    (project / "content" / "inicio.md").write_text("x\n\n[[nao_existe|Ir]]\n[[!quit|Sair]]\n")
    eng, out = run(project, console, "1\n2\n")
    assert "nota não encontrada" in out


def test_back_and_restart_hooks(project, console):
    (project / "content" / "sala.md").write_text("Sala\n\n[[!back|Voltar]]\n")
    _, out = run(project, console, "1\n1\n2\n")
    assert out.count("Olá mundo.") == 2


def test_check_reports_problems(project):
    (project / "content" / "inicio.md").write_text(
        "[sound:nada.ogg][foo:1] ![[sumiu.txt]]\n\n[[fantasma|X]]\n[[!naoexiste|Y]]\n[[sala|Z]]\n")
    eng = Engine(project, audio=False, instant=True)
    rep = check_project(eng)
    text = "\n".join(rep.errors)
    assert "fantasma" in text and "naoexiste" in text and "sumiu.txt" in text and "nada.ogg" in text
    assert any("foo" in w for w in rep.warnings)
    assert not rep.ok
