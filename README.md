# TaleForge

Engine modular em Python para **RPGs de texto no terminal Linux (TTY)**.
Você escreve a história em arquivos `.md`/`.txt`, com efeitos embutidos no próprio texto;
a engine cuida de digitar, colorir, tremer, tocar sons e montar os menus.

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
└── hooks.py             # opcional — lógica específica do jogo
```

## Instalação

```bash
git clone https://github.com/MorganaQrr/TaleForge.git
cd TaleForge
python -m venv .venv && source .venv/bin/activate
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

Diretivas têm o formato `[atributo:valor]`. As de **estado** valem até `[/atributo]` (ou `[reset]`); as de **evento** acontecem uma vez.

| Diretiva | Tipo | Exemplo | O que faz |
|---|---|---|---|
| `color` | estado | `[color:#0fff]…[/color]` | Cor do texto: nome do rich, `#RGB`, `#RGBA`, `#RRGGBB`, `#RRGGBBAA` (alfa mistura com `theme.background`) |
| `bg` | estado | `[bg:#222]` | Cor de fundo |
| `bold` `italic` `underline` `dim` `strike` | estado | `[bold]…[/bold]` | Atributos de texto |
| `type_speed` | estado | `[type_speed:0.5]` | Multiplicador da velocidade (`0.5` = metade, `0` = instantâneo); `[type_speed:80cps]` = absoluto |
| `shake` | estado | `[shake:3]…[/shake]` | O texto digitado treme (amplitude em colunas) |
| `style` | estado | `[style:perigo]…[/style]` | Aplica um preset de `[styles.perigo]` do config |
| `pause` | evento | `[pause:1.5]` | Pausa em segundos |
| `wait` | evento | `[wait]` | Espera uma tecla |
| `jolt` | evento | `[jolt:3]` | Treme a linha atual uma vez |
| `clear` / `rule` | evento | `[clear]`, `---` | Limpa a tela / linha horizontal |
| `ascii` | evento | `[ascii:dragao.txt, color=red, align=center]` | Carrega arte ASCII (ou use `![[dragao.txt]]`) |
| `sound` | evento | `[sound:passos.ogg, volume=0.8, loop=true]` | Efeito pontual (`soundFX`) |
| `music` | evento | `[music:tema.ogg, volume=0.6, fade=1500]` / `[music:stop]` | Trilha contínua |
| `layer` / `stop_layer` | evento | `[layer:criaturas]…[/layer]` | Ativa uma camada de áudio; sons seguintes entram nela |
| `volume` | evento | `[volume:criaturas=0.3]` | Ajusta volume de uma camada |
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
* Hooks embutidos: `!quit`, `!back`, `!restart`, `!reload`, `!goto nota`.
* Um link no meio de uma frase (`abre [[porta|a porta]]`) aparece destacado no texto e também entra no menu.

### Hooks em Python (`hooks.py` do projeto)

```python
from taleforge import hook

@hook("pegar_chave")
def pegar_chave(engine):
    engine.state["chave"] = True        # dicionário livre para inventário/flags
    engine.audio.soundFX("chave.wav")
    engine.say("[color:#fa0]Você pega a chave.[/color]")   # renderiza marcação
    return None                          # ou "nome_da_nota" para navegar
```

`engine` também oferece `goto()`, `back()`, `restart()`, `quit()`, `history`, `config` e `audio`.

## ASCII art

`![[arte.txt]]` ou `[ascii:arte.txt]` buscam o arquivo em `assets/ascii/` (também aceitam caminho relativo à raiz ou absoluto). Arquivos com códigos ANSI são respeitados. Config: `ascii.mode` (`line` revela linha a linha, `instant`), `ascii.line_delay`.

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

Todo valor tem padrão (veja `DEFAULTS` em `taleforge/config.py`). Principais seções: `[project]`, `[paths]`, `[text]` (velocidade, pausas por pontuação, jitter), `[theme]`, `[effects]`, `[ascii]`, `[menu]`, `[audio]`, `[layers.*]`, `[styles.*]`, `[directives]` (aliases/desativar), `[plugins]`, `[hooks]`, `[behavior]`, `[dev]`.

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

`ctx` expõe `engine`, `renderer` e `state` (cor, estilo, velocidade, tremor do texto corrente).

## Estrutura do código

```
taleforge/
├── cli.py          run / new / check
├── engine.py       laço principal, navegação, hooks, cenas
├── markup.py       parser da marcação → tokens
├── directives.py   diretivas embutidas (usam o mesmo @directive dos plugins)
├── renderer.py     typewriter, estilos, tremor, ASCII
├── menu.py         menu navegável (setas/números)
├── audio.py        soundFX(), music(), camadas
├── loader.py       busca de notas + frontmatter
├── config.py       padrões + TOML/YAML
├── watch.py        hot-reload (watchdog, com fallback por polling)
├── check.py        validação de projeto
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
