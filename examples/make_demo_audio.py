"""Gera os sons de demonstração (WAV sintetizados) da torre_esquecida.

Uso: python examples/make_demo_audio.py
Não depende de nada além da biblioteca padrão.
"""
import math
import random
import struct
import wave
from pathlib import Path

RATE = 11025
OUT = Path(__file__).parent / "torre_esquecida" / "assets" / "audio"


def write(name, samples):
    OUT.mkdir(parents=True, exist_ok=True)
    peak = max(1e-9, max(abs(s) for s in samples))
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(s / peak * 0.8 * 32767)) for s in samples))


def env(i, n, attack=0.05, release=0.3):
    t = i / n
    a = min(1.0, t / attack) if attack else 1.0
    r = min(1.0, (1 - t) / release) if release else 1.0
    return a * r


def wind(seconds=3.0):
    random.seed(1)
    n, lp, out = int(RATE * seconds), 0.0, []
    for i in range(n):
        lp += (random.uniform(-1, 1) - lp) * 0.08
        out.append(lp * (0.6 + 0.4 * math.sin(2 * math.pi * i / n * 2)))
    # costura as pontas para o loop não estalar
    fade = int(RATE * 0.1)
    for i in range(fade):
        k = i / fade
        out[i] = out[i] * k + out[n - fade + i] * (1 - k)
    return out[: n - fade]


def owl():
    n, out = int(RATE * 1.0), []
    for i in range(n):
        t = i / RATE
        f = 380 if t < 0.35 else (0 if t < 0.5 else 340)
        e = env(i, n, 0.02, 0.5)
        out.append(math.sin(2 * math.pi * f * t) * e * (f > 0))
    return out


def steps():
    random.seed(2)
    n, out = int(RATE * 1.0), []
    for i in range(n):
        t = i / RATE
        k = (t % 0.4) / 0.4
        out.append(random.uniform(-1, 1) * math.exp(-k * 12) * (t < 0.8))
    return out


def rumble():
    random.seed(3)
    n, lp, out = int(RATE * 1.6), 0.0, []
    for i in range(n):
        lp += (random.uniform(-1, 1) - lp) * 0.02
        out.append(lp * env(i, n, 0.02, 0.8) + 0.5 * math.sin(2 * math.pi * 45 * i / RATE) * env(i, n, 0.02, 0.8))
    return out


def drone(seconds=6.0):
    n = int(RATE * seconds)
    out = []
    for i in range(n):
        t = i / RATE
        trem = 0.75 + 0.25 * math.sin(2 * math.pi * t / seconds * 2)
        v = sum(math.sin(2 * math.pi * f * t) / (j + 1) for j, f in enumerate((110, 164.8, 220)))
        out.append(v * trem)
    return out


if __name__ == "__main__":
    for name, fn in [("vento.wav", wind), ("coruja.wav", owl), ("passos.wav", steps),
                     ("estrondo.wav", rumble), ("drone.wav", drone)]:
        write(name, fn())
        print("gerado", OUT / name)
