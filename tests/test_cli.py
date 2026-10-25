import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cli(*args, stdin=""):
    import os
    env = {**os.environ, "PYTHONPATH": str(ROOT), "SDL_AUDIODRIVER": "dummy"}
    return subprocess.run([sys.executable, "-m", "taleforge", *args], input=stdin, text=True,
                          capture_output=True, env=env, timeout=60)


def test_new_then_check_then_run(tmp_path):
    dest = tmp_path / "meu_rpg"
    assert cli("new", str(dest)).returncode == 0
    assert (dest / "content" / "inicio.md").exists()
    chk = cli("check", str(dest))
    assert chk.returncode == 0, chk.stdout + chk.stderr
    run = cli("run", str(dest), "--instant", "--no-audio", stdin="1\n2\n")
    assert run.returncode == 0
    assert "Bem-vinda" in run.stdout


def test_new_refuses_nonempty_dir(tmp_path):
    (tmp_path / "x").write_text("1")
    assert cli("new", str(tmp_path)).returncode == 1


def test_bundled_example_is_valid():
    assert cli("check", str(ROOT / "examples" / "torre_esquecida")).returncode == 0
