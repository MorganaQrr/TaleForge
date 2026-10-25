from taleforge.colors import parse_color
from taleforge.markup import Embed, Literal, Option, Tag, Text, make_option, options_of, parse_note

KNOWN = {"color", "shake", "type_speed", "pause", "bold", "italic", "style", "rule", "sound"}  # noqa: E501


def known(name):
    return name.lower() if name.lower() in KNOWN else None


def test_inline_tags_and_text():
    toks = parse_note("a [color:#0fff]b[/color] [shake:3]c", known)
    assert toks[0] == Text("a ")
    assert toks[1] == Tag("color", "#0fff", False, "[color:#0fff]")
    assert toks[3].closing and toks[3].name == "color"
    assert Tag("shake", "3", False, "[shake:3]") in toks


def test_unknown_tags_stay_literal_and_are_reported():
    unknown = []
    toks = parse_note("x [foo:bar] y", known, unknown=unknown)
    assert "".join(t.text for t in toks if isinstance(t, Text)) == "x [foo:bar] y"
    assert unknown == ["foo"]


def test_options_obsidian_style():
    toks = parse_note("Texto\n\n[[sala|Ir à sala]]\n[[!pegar chave|Pegar]]\n[[solo]]", known)
    opts = options_of(toks)
    assert [(o.target, o.label, o.inline) for o in opts] == [
        ("sala", "Ir à sala", False), ("!pegar chave", "Pegar", False), ("solo", "solo", False)]
    assert opts[1].is_hook
    # sem linhas em branco sobrando entre texto e menu
    assert isinstance(toks[-4], Text) and toks[-4].text == "Texto"


def test_inline_option_keeps_label_in_text():
    toks = parse_note("Você abre [[porta|a porta]] devagar.", known)
    assert any(isinstance(t, Option) and t.inline for t in toks)


def test_make_option_strips_section_anchor():
    assert make_option("nota#secao|Rótulo").target == "nota"


def test_embed_and_literal_block():
    toks = parse_note("![[dragao.txt]]\n```\n*/\\*\n```\n![[nota.md]]", known)
    assert any(isinstance(t, Embed) and t.path == "dragao.txt" for t in toks)
    assert any(isinstance(t, Literal) and t.text == "*/\\*" for t in toks)
    # embed de arquivo que não é arte ASCII vira texto
    assert any(isinstance(t, Text) and "![[nota.md]]" in t.text for t in toks)


def test_markdown_becomes_tags_and_can_be_disabled():
    toks = parse_note("**negrito** e *itálico*", known)
    assert [t.name for t in toks if isinstance(t, Tag)] == ["bold", "bold", "italic", "italic"]
    plain = parse_note("**negrito**", known, markdown=False)
    assert plain == [Text("**negrito**")]


def test_escaped_bracket_and_comments():
    toks = parse_note(r"\[color:red] %%oculto%% fim", known)
    assert "".join(t.text for t in toks if isinstance(t, Text)) == "[color:red]  fim"


def test_colors():
    assert parse_color("#0fff") == "#00ffff"
    assert parse_color("#f00") == "#ff0000"
    assert parse_color("#ff000080", "#000000") == "#800000"
    assert parse_color("red") == "red"
    for bad in ("#12", "nao_existe_cor", ""):
        try:
            parse_color(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
