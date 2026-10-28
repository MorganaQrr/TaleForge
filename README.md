```markdown
# TaleForge

Engine modular em Python para **RPGs de texto no terminal Linux (TTY)**.
Você escreve a história em arquivos `.md`/`.txt`, com efeitos embutidos no próprio texto;
a engine cuida de digitar, colorir, tremer, tocar sons, montar os menus e reagir a tags.

> **Critério de aceite:** um RPG novo nasce só com arquivos `.md` + assets.
> Nenhuma linha da engine precisa ser editada.

```
meu_rpg/
├── config.toml          # opcional — tudo tem valor padrão
├── content/             # suas notas .md/.txt (subpastas ok)
│   ├── inicio.md
│   └── caverna.md
├── assets/
│   ├── ascii/           # artes ASCII
│   └── audio/           # .wav / .ogg / .mp3
│       └── ui/          # opcional — move.wav, select.wav (menu)
└── hooks.py             # opcional — lógica específica do jogo
```

## Instalação

```bash
git clone git@github.com:MorganaQrr/TaleForge.git
cd TaleForge
python3 -m venv .venv && source .venv/bin/activate
pip install -e .            # instala o comando `taleforge`
```

Requer Python 3.10+. Dependências: `rich`, `pygame`, `pyyaml`, `watchdog` (e `tomli` no 3.10).

## Começando

```bash
taleforge new meu_rpg                          # cria um projeto a partir do modelo
taleforge run meu_rpg                          # joga
taleforge run meu_rpg --watch                  # hot-reload: salve a nota e ela reaparece
taleforge check meu_rpg                        # valida links, assets, diretivas e hooks
taleforge run examples/torre_esquecida         # demo completa (com áudio em camadas)
```

Opções do `run`: `--start NOTA`, `--instant` (sem efeitos de digitação), `--no-audio`, `--watch`, `--debug` (grava `taleforge.log`).
Teclas: `↑/↓` (ou `w/s/j/k`) navegam, `Enter` confirma, números `1-9` escolhem direto, `Backspace` volta, qualquer tecla durante a digitação acelera o texto.

Uso como biblioteca: `from taleforge import Engine; Engine("meu_rpg").run()`

## Marcação inline

Diretivas têm o formato `[atributo:valor]`. As de **estado** valem até `[/atributo]` (ou `[reset]`); as de **evento** acontecem uma vez; as de **cena** alteram o estado global.

| Diretiva | Tipo | Exemplo | O que faz |
|---|---|---|---|
| `color` | estado | `[color:#0fff]…[/color]` | Cor do texto: nome do rich, `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA` (alfa mistura com `theme.background`) |
| `bg` | estado | `[bg:#222]` | Cor de fundo |
| `bold` `italic` `underline` `dim` `strike` | estado | `[bold]…[/bold]` | Atributos de texto |
| `type_speed` | estado | `[type_speed:0.5]` | Multiplicador da velocidade (`0.5` = metade, `0` = instantâneo); `[type_speed:80cps]` = absoluto |
| `shake` | estado | `[shake:3]…[/shake]` | O texto digitado treme (amplitude em colunas) |
| `style` | estado | `[style:perigo]…[/style]` | Aplica um preset de `[styles.perigo]` do config |
| `voice` | estado | `[voice:evil]…[/voice]` | Voz de digitação (blips enquanto o texto é digitado). `[voice:off]` silencia |
| `pause` | evento | `[pause:1.5]` | Pausa em segundos |
| `wait` | evento | `[wait]` | Espera uma tecla |
| `jolt` | evento | `[jolt:3]` | Treme a linha atual uma vez |
| `clear` / `rule` | evento | `[clear]`, `---` | Limpa a tela / linha horizontal |
| `ascii` | evento | `[ascii:dragao.txt, color=red, align=center]` | Carrega arte ASCII (ou use `![[dragao.txt]]`) |
| `sound` | evento | `[sound:passos.ogg, volume=0.8, loop=true]` | Efeito pontual (`soundFX`) |
| `music` | evento | `[music:tema.ogg, volume=0.6, fade=1500]` / `[music:stop]` | Trilha contínua |
| `layer` / `stop_layer` | evento | `[layer:criaturas]…[/layer]` | Ativa uma camada de áudio; sons seguintes entram nela |
| `volume` | evento | `[volume:criaturas=0.3]` | Ajusta volume de uma camada |
| `som_menu` | evento | `[som_menu:move=x.wav select=y.wav]` | Troca os sons do menu daqui pra frente; `[som_menu:off]` silencia |
| `tag` | cena | `[tag: #title, #magia]` | Dispara hooks `tag_title`, `tag_magia` e o `on_tag` genérico (não aparece no texto) |
| `hook` | evento | `[hook:dado 20]` | Chama um hook do projeto |
| `goto` / `end` | evento | `[goto:cap2]`, `[end]` | Salta de nota ao fim do texto / encerra o jogo |

Também: `**negrito**`, `*itálico*`, `` `código` ``, `# Título`, `> citação`, `---` (desligue com `text.markdown = false`); blocos ```` ``` ```` imprimem arte ASCII escrita na própria nota; `%% comentário %%` é ignorado; `\[` escapa um colchete. Tags desconhecidas ficam como texto (o `check` avisa).
Os nomes têm *aliases* em português configuráveis (`[cor:red]`, `[pausa:1]`, `[tremor:3]`, `[som:x.wav]`… veja `directives.aliases`).

## Opções e navegação

Links no padrão do Obsidian, `[[destino|rótulo]]`. Linhas só com links viram o menu da cena:

```markdown
Você chega a uma bifurcação.

[[floresta|Seguir pela floresta]]
[[caverna|Entrar na caverna]]
[[!rolar_dado 20|Tentar a sorte]]
[[!quit|Desistir]]
```

* `[[nota|Rótulo]]` salta para `content/nota.md` (busca por nome em qualquer subpasta; ignora maiúsculas e trata espaço, `_` e `-` como iguais).
* `[[!hook arg1 arg2|Rótulo]]` dispara um hook. Se ele devolver o nome de uma nota, a engine navega até ela; se devolver `None`, o menu continua.
* Hooks embutidos: `!quit`, `!back`, `!restart`, `!reload`, `!goto nota`, `!ask variavel palavras…`.
* Um link no meio de uma frase (`abre [[porta|a porta]]`) aparece destacado no texto e também entra no menu.

Além dos links da nota, o engine aceita **opções dinâmicas** injetadas por hooks (ver `add_option` / `global_options` abaixo).

## Tags

Tags servem para disparar hooks **sem** precisar de `[hook:...]` no corpo. Duas sintaxes equivalentes:

**No frontmatter** (YAML):

```markdown
---
tags: [title, batalha]
---
```

**No corpo** (é removido do texto visível):

```markdown
[tag: #title, #batalha]
```

A engine junta as duas listas (sem duplicar), normaliza (`#` removido, minúsculas) e para cada tag chama:

* `tag_<nome>` — o hook específico (`tag_title`, `tag_batalha`, …), **sem argumentos**;
* `on_tag` — o hook genérico, **recebendo o nome da tag** como argumento.

Assim dá para ter:

```python
@hook("tag_title")
def _tag_title(engine):
    engine.audio.music("title.mp3")

@hook("on_tag")
def _on_tag(engine, tag):
    engine.state.setdefault("tags_vistas", set()).add(tag)
```

As tags rodam **uma vez por nota**, logo depois do frontmatter (`music`, `layers`, `sound`, `ui_sound`) e antes do texto — então servem para preparar a cena inteira.

## Hooks em Python (`hooks.py` do projeto)

```python
from taleforge import hook

@hook("pegar_chave")
def pegar_chave(engine):
    engine.state["chave"] = True        # dicionário livre para inventário/flags
    engine.audio.soundFX("chave.wav")
    engine.say("[color:#fa0]Você pega a chave.[/color]")   # renderiza marcação
    return None                          # ou "nome_da_nota" para navegar
```

`engine` oferece `goto()`, `back()`, `restart()`, `quit()`, `history`, `config`, `audio`, `state`, `say()`, `ask()` e as opções dinâmicas abaixo.

### `engine.ask()` e o hook `!ask`

Coleta texto do jogador devolvendo o cursor e o echo ao terminal (funciona dentro do `terminal_session`):

```python
nome = engine.ask("Como te chamas? ", state_key="nome", default="Anônimo")
```

Pelo menu, use o hook:

```markdown
[[!ask nome Como te chamas?|Escolher nome]]
```

O `!ask` **embutido** recebe `state_key` primeiro, e o restante é o prompt. O hook do projeto pode sobrescrever (o seu em `hooks.py` faz validação, cursor, backspace etc.).

### Opções dinâmicas

Um hook pode **adicionar ou remover opções** do menu da cena corrente:

```python
@hook("init")
def init(engine):
    engine.add_option("Menu", "menu", engine.global_options)   # opção global
```

* `engine.extra_options` — opções **só desta cena**; limpas a cada nova nota.
* `engine.global_options` — opções **persistentes**, injetadas em todas as notas.
* `engine.ignored_options` — nomes que **não** devem aparecer no menu (útil para esconder “Menu” em certas notas).
* `engine.add_option(nome, alvo, target=None)` — adiciona; `target` default é `extra_options`.
* `engine.remove_option(nome, target=None)` — remove.

## Sons de digitação (voice)

Enquanto o texto é digitado, um som curtinho toca a cada N caracteres — o “blip” que dá voz ao narrador.

**Config:**

```toml
[voice]
enabled  = true
default  = "padrao"   # id da voz (sem extensão)
volume   = 0.5
every    = 2          # toca a cada 2 caracteres
min_gap  = 0.03       # intervalo mínimo entre blips (s)
```

**Onde ficam os arquivos:**

* Banco padrão da engine: `taleforge/voices/<id>.wav` (ou `.ogg`, `.mp3`, `.flac`);
* Banco do projeto: declare em `[voices.<id>] files = [...]` no `config.toml` (cada caminho é resolvido por `paths.audio`).

**Trocar de voz:**

* Em uma nota: `[voice:evil] … [/voice]`, ou `[voice:evil]` no frontmatter (`[voice] … [/voice]` para encerrar);
* Em código: `engine.config.set("voice.default", "evil")` (global), ou `state.voice` dentro de um `TextState`.

`[voice:off]` (ou `mudo`) silencia. Vozes inexistentes geram aviso uma única vez e caem em silêncio.

## Sons de interface (menu)

O menu (↑/↓ navegando, Enter confirmando) pode tocar dois sons distintos: **move** e **select**.

**Config:**

```toml
[ui_sound]
enabled = true
move    = "ui/move.wav"    # relativo a assets/audio
select  = "ui/select.wav"
volume  = 1.0
```

Coloque os arquivos em `assets/audio/ui/` (mesma convenção de `soundFX`).

**Por nota (frontmatter):**

```markdown
---
ui_sound:
  move:   "ui/move_tenso.wav"
  select: "ui/select_tenso.wav"
---
```

Ou desligar:

```markdown
---
ui_sound: off
---
```

**No corpo (diretiva):**

```markdown
[som_menu: off]                                  # silencia
[som_menu: on]                                   # volta ao config
[som_menu: move=ui/passo.wav]                    # só o move
[som_menu: move=a.wav select=b.wav]              # os dois
```

**Em código:**

```python
engine.audio.set_ui_sound("move", "ui/passo.wav")
engine.audio.set_ui_sound("off", None)   # silencia
engine.audio.reset_ui_sounds()           # volta ao config (chamado no início de cada nota)
```

A precedência é: **override da nota > config > silêncio**.

## ASCII art

`![[arte.txt]]` ou `[ascii:arte.txt]` buscam o arquivo em `assets/ascii/` (também aceitam caminho relativo à raiz ou absoluto). Arquivos com códigos ANSI são respeitados. Config: `ascii.mode` (`line` revela linha a linha, `instant`), `ascii.line_delay`.

Arquivos `.md` são aceitos: use `![[arte.md]]` ou `[ascii:arte.md]`, edite a arte no Obsidian dentro de um bloco ``` e as cercas de abertura/fechamento são removidas automaticamente.

## Áudio e camadas

`pygame.mixer` por trás de uma API pequena (`taleforge/audio.py`):

* `soundFX(arquivo, volume, loop, fade_ms)` — efeito pontual.
* `music(arquivo, volume, loop, fade_ms)` — trilha contínua. Na camada raiz usa `pygame.mixer.music` (streaming); em subcamadas, um `Sound` em loop num canal próprio, então várias trilhas podem soar juntas.
* **Camadas** formam uma árvore: o volume final de um som é o **produto** dos volumes da cadeia (`master × ambiente × criaturas × som`).

Declare no `config.toml`:

```toml
[layers.ambiente]
volume = 0.7
sounds = [{ file = "vento.wav", loop = true }]

[layers.criaturas]            # sub-camada de "ambiente"
parent = "ambiente"
volume = 0.9
sounds = [{ files = ["coruja.wav", "lobo.wav"], every = [6, 14], volume = 0.8 }]
```

Cada item de `sounds` pode ser `loop = true`, tocar uma vez ao ativar, ou repetir em intervalo aleatório com `every = [min, max]` (segundos), sorteando entre `files`.
Ative por texto (`[layer:criaturas]`), por código (`engine.audio.layer("criaturas").soundFX("x.ogg")`, `parent.layer("filha")`) ou pelo **frontmatter** da nota, que descreve a cena:

```markdown
---
music: tema.ogg        # "none" para parar
layers: [ambiente, criaturas]   # sincroniza: o que não estiver na lista para (exceto persist = true)
sound: porta.wav       # toca ao entrar
---
```

Sem pygame, sem placa de som ou com `audio.enabled = false`, o jogo roda em silêncio. Em máquinas sem áudio use `audio.driver = "dummy"`.

## Configuração (`config.toml` ou `settings.yaml`)

Todo valor tem padrão (veja `DEFAULTS` em `taleforge/config.py`). Principais seções: `[project]`, `[paths]`, `[text]` (velocidade, pausas por pontuação, jitter), `[theme]`, `[effects]`, `[ascii]`, `[menu]`, `[voice]`, `[ui_sound]`, `[audio]`, `[layers.*]`, `[voices.*]`, `[styles.*]`, `[directives]` (aliases/desativar), `[plugins]`, `[hooks]`, `[behavior]`, `[dev]`.

Blocos mais recentes:

```toml
[voice]
enabled = true
default = "padrao"
volume  = 0.5
every   = 2          # caracteres entre blips
min_gap = 0.03       # intervalo mínimo entre blips

[ui_sound]
enabled = true
move    = "ui/move.wav"
select  = "ui/select.wav"
volume  = 1.0
```

## Extensões (plugins)

Novas diretivas entram sem tocar na engine:

```python
# meu_plugin.py  (na pasta do projeto ou instalado)
from taleforge import directive

@directive("eco", kind="event")
def eco(ctx, value, closing):
    ctx.renderer.type_text(value.upper(), ctx.state)
```

```toml
[plugins]
modules = ["meu_plugin"]
```

`ctx` expõe `engine`, `renderer` e `state` (cor, estilo, velocidade, tremor, voz do texto corrente).

## Estrutura do código

```
taleforge/
├── cli.py          run / new / check
├── engine.py       laço principal, navegação, hooks, cenas, tags, ask
├── markup.py       parser da marcação → tokens
├── directives.py   diretivas embutidas (usam o mesmo @directive dos plugins)
├── renderer.py     typewriter, estilos, tremor, ASCII
├── menu.py         menu navegável (setas/números), sons de UI
├── audio.py        soundFX(), music(), camadas, voice, ui_sound
├── loader.py       busca de notas + frontmatter
├── config.py       padrões + TOML/YAML
├── watch.py        hot-reload (watchdog, com fallback por polling)
├── check.py        validação de projeto
├── voices/         banco de vozes padrão (.wav/.ogg/.mp3/.flac)
└── templates/      modelo usado por `taleforge new`
```

## Testes

```bash
pip install -e ".[dev]"
pytest
```

## Limitações conhecidas

* Só Linux/macOS (usa `termios`); sem TUI em `textual` ainda e sem DSP com `numpy` (a mixagem é feita pelo `pygame.mixer`).
* O tremor reescreve a linha atual, então vale para texto de uma linha (a quebra de linha automática é feita pela engine).
* Não há condicionais em opções/texto: use hooks e `engine.state`.

## Licença

MIT — veja [LICENSE](LICENSE).

## Novidades

### Voices, UI sound, tags e `ask`

- **Voice (sons de digitação)** — `[voice:evil] … [/voice]` na nota, `voice.default` no config, arquivos em `taleforge/voices/<id>.wav` (banco padrão) ou em `[voices.<id>] files` (banco do projeto). Volume, intervalo e frequência configuráveis.
- **Sons de interface** — `[ui_sound]` no config, `[som_menu: move=x select=y]` na nota e frontmatter `ui_sound:` deixam o menu com som próprio, sem tocar em código.
- **Tags** — `[tag: #title, #magia]` no corpo (removido do texto) ou `tags: [title, magia]` no frontmatter disparam hooks `tag_title`, `tag_magia` e o genérico `on_tag`. Bom para preparar cena, esconder opções, escolher trilha.
- **`ask` / `engine.ask()`** — coleta input restaurando echo/cursor. Funciona como hook `[[!ask nome|Rótulo]]` e como método. Aceita `state_key` e `default`.
- **Opções dinâmicas** — hooks podem injetar opções no menu com `engine.add_option(nome, alvo)` e `engine.global_options` / `engine.extra_options` / `engine.ignored_options`.

### Arte ASCII em arquivos `.md`

- `.md` agora é aceito como arte ASCII: `![[arte.md]]` ou `[ascii:arte.md]`. Dá para editar a arte no Obsidian, dentro de um bloco de código, e ela aparece embutida na nota.
- As cercas ``` de abertura e fechamento são removidas automaticamente ao exibir um arquivo `.md`.
- Cor da arte: `[ascii:arte.md, color=#ed9e00]` (alias em português: `[arte:arte.md, color=#ed9e00]`). Quando uma cor é definida, os códigos ANSI embutidos na arte são descartados para a cor da nota valer.
- A extensão `.md` já está na lista padrão `ascii.extensions`. Projetos com `[ascii] extensions` próprio no `config.toml` precisam incluí-la.
```

---
