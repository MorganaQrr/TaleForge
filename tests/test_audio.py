import time

import pytest

pytest.importorskip("pygame")

from taleforge import Engine  # noqa: E402

from conftest import make_wav  # noqa: E402


@pytest.fixture
def audio_project(project):
    make_wav(project / "assets" / "audio" / "a.wav")
    make_wav(project / "assets" / "audio" / "b.wav")
    (project / "config.toml").write_text(
        '[audio]\ndriver="dummy"\nmaster_volume=0.5\n'
        '[layers.fx]\nvolume=0.5\nsounds=[{file="a.wav", loop=true}]\n'
        '[layers.criaturas]\nparent="fx"\nvolume=0.5\nsounds=[{files=["b.wav"], every=[0.1,0.1]}]\n')
    return project


def test_layer_tree_volume_is_product(audio_project):
    eng = Engine(audio_project, instant=True)
    try:
        a = eng.audio
        assert a.available
        assert a.layers["criaturas"].parent is a.layers["fx"]
        assert a.layers["criaturas"].effective_volume == pytest.approx(0.5 * 0.5 * 0.5)
        a.set_volume("fx", 1.0)
        assert a.layers["criaturas"].effective_volume == pytest.approx(0.25)
    finally:
        eng.audio.shutdown()


def test_soundfx_music_and_nested_scheduling(audio_project):
    eng = Engine(audio_project, instant=True)
    a = eng.audio
    try:
        h = a.soundFX("a.wav", volume=0.8)
        assert h is not None and h.volume == pytest.approx(0.8 * 0.5)  # master 0.5
        m = a.music("b.wav")
        assert m is not None and a.master._music_file == "b.wav"
        assert a.music("b.wav") is m                      # mesma trilha não reinicia
        a.enter_layer("criaturas")                        # ativa o pai (fx) também
        assert a.layers["fx"].active and a.layers["criaturas"].active
        assert a.layers["fx"]._handles                    # loop de fx tocando
        assert a.layers["criaturas"]._scheduled
        deadline = time.time() + 3                        # agendador dispara b.wav sozinho
        while time.time() < deadline and not any(
                h.source == "b.wav" for h in a.layers["criaturas"]._handles):
            time.sleep(0.05)
        assert any(h.source == "b.wav" for h in a.layers["criaturas"]._handles)
        a.stop_layer("fx")                                # para a subárvore
        assert not a.layers["fx"].active and not a.layers["criaturas"].active
        a.exit_layer()
    finally:
        a.shutdown()


def test_frontmatter_scene_sync(audio_project):
    eng = Engine(audio_project, instant=True)
    try:
        eng.audio.sync_layers(["criaturas"])
        assert eng.audio.layers["fx"].active
        eng.audio.sync_layers([])
        assert not eng.audio.layers["fx"].active
        assert not eng.audio.layers["criaturas"].active
    finally:
        eng.audio.shutdown()


def test_missing_file_and_disabled_audio_do_not_crash(audio_project):
    eng = Engine(audio_project, instant=True)
    try:
        assert eng.audio.soundFX("nao_existe.wav") is None
        assert any("não encontrado" in w for w in eng.warnings)
    finally:
        eng.audio.shutdown()
    off = Engine(audio_project, instant=True, audio=False)
    assert not off.audio.available
    assert off.audio.soundFX("a.wav") is None
    off.audio.enter_layer("fx")
    off.audio.shutdown()
