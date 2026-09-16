"""Constrained-random pin waveforms: baud error, edge jitter, gaps, glitches.

The decoders never see the encoder graph here. Waveforms are synthesised
directly so the constraints (systematic baud error, per-edge jitter, idle
gaps, runt pulses, SPI clock asymmetry) are explicit and reproducible.

Contract under test:
  * inside the tolerance band the payload is recovered exactly;
  * `uart_rx_frame` rejects runt start bits and flags bad stop bits on pin1;
  * SPI mode-0 decode is insensitive to clock asymmetry, inter-byte gaps and
    MOSI noise while SCK is low.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from loom.interp import Engine
from loom.stream import load_graph

PLANS = Path(__file__).resolve().parents[1] / "plans"
BIT = 8  # cycles per UART bit at the graphs' nominal rate
SEEDS = range(24)


def _decode(plan: str, pins: list[int]) -> tuple[bytes, list[int]]:
    """Run a decoder graph over a per-cycle gpio_in list.

    Returns (rx bytes, per-cycle gpio_out trace)."""
    eng = Engine()
    eng.load(load_graph(PLANS / plan))
    eng.sm.run = True
    got: list[int] = []
    out: list[int] = []
    for g in pins:
        eng.sm.tick(g)
        out.append(eng.sm.out_reg)
        # host drains the 4-deep RX FIFO as bytes arrive
        if not eng.sm.rx.empty:
            got.append(eng.sm.rx.pop())
    return bytes(got), out


# ---------------------------------------------------------------- UART


def uart_wave(
    payload: bytes,
    rng: random.Random,
    baud_err: float = 0.0,
    jitter: int = 0,
    gap: tuple[int, int] = (BIT, 4 * BIT),
    lead: int = 16,
) -> list[int]:
    """8N1 on pin0, LSB first, idle high.

    baud_err: systematic bit-period error (e.g. 0.04 = +4%).
    jitter:   each edge moves by an integer in [-jitter, +jitter] cycles.
    gap:      idle cycles between frames, uniform in [lo, hi].
    """
    wave = [1] * lead
    period = BIT * (1.0 + baud_err)
    for byte in payload:
        bits = [0] + [(byte >> i) & 1 for i in range(8)] + [1]
        t0 = len(wave)
        edges = []
        for k in range(len(bits) + 1):
            e = t0 + round(k * period) + (rng.randint(-jitter, jitter) if 0 < k < len(bits) else 0)
            edges.append(e)
        for k in range(1, len(edges)):
            edges[k] = max(edges[k], edges[k - 1] + 1)  # every bit >= 1 cycle
        for k, b in enumerate(bits):
            wave.extend([b] * (edges[k + 1] - edges[k]))
        wave.extend([1] * rng.randint(*gap))
    wave.extend([1] * 4 * BIT)
    return wave


@pytest.mark.parametrize("plan", ("uart_rx.toml", "uart_rx_frame.toml"))
@pytest.mark.parametrize("seed", SEEDS)
def test_uart_random_in_band(plan: str, seed: int):
    """±3% baud error plus ±1 cycle edge jitter, random gaps: payload exact.

    At 8 cycles/bit the theoretical ceiling is ~5.9% (half a bit over 8.5
    bits); ±1 cycle of jitter on top eats ~1.5% of that."""
    rng = random.Random(seed)
    payload = bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 6)))
    err = rng.uniform(-0.03, 0.03)
    pins = uart_wave(payload, rng, baud_err=err, jitter=1)
    got, out = _decode(plan, pins)
    assert got == payload, (seed, err, payload.hex(), got.hex())
    if plan == "uart_rx_frame.toml":
        assert not any(o & 2 for o in out), "frame flag raised on a clean frame"


def _band(plan: str, errs) -> list[float]:
    ok = []
    for e in errs:
        rng = random.Random(1000 + int(e * 1000))
        payload = bytes([0x55, 0xA3, 0x00, 0xFF])
        pins = uart_wave(payload, rng, baud_err=e, jitter=0)
        got, _ = _decode(plan, pins)
        if got == payload:
            ok.append(e)
    return ok


@pytest.mark.parametrize("plan", ("uart_rx.toml", "uart_rx_frame.toml"))
def test_uart_baud_tolerance_band(plan: str):
    """Sweep systematic baud error; the pass band must cover at least ±4%."""
    errs = [e / 100 for e in range(-15, 16)]
    ok = _band(plan, errs)
    assert min(ok) <= -0.04 and max(ok) >= 0.04, f"{plan}: pass band {min(ok):+.2f}..{max(ok):+.2f}"


@pytest.mark.parametrize("seed", SEEDS)
def test_uart_frame_rejects_glitches(seed: int):
    """Runt low pulses (1-4 cycles) in idle produce no byte and no flag."""
    rng = random.Random(seed)
    pins = [1] * 16
    for _ in range(rng.randint(1, 8)):
        pins += [0] * rng.randint(1, 4) + [1] * rng.randint(8, 40)
    pins += [1] * 128
    got, out = _decode("uart_rx_frame.toml", pins)
    assert got == b"", f"glitch decoded as {got.hex()}"
    assert not any(o & 2 for o in out)


@pytest.mark.parametrize("seed", SEEDS)
def test_uart_frame_flags_break_then_recovers(seed: int):
    """A break (line low >= 2 frames) raises the flag, pushes nothing, and the
    next clean frame decodes and clears the flag."""
    rng = random.Random(seed)
    payload = bytes([rng.getrandbits(8)])
    pins = [1] * 16 + [0] * rng.randint(2 * 10 * BIT, 4 * 10 * BIT) + [1] * rng.randint(BIT, 4 * BIT)
    n_break = len(pins)
    pins += uart_wave(payload, rng, lead=0)
    got, out = _decode("uart_rx_frame.toml", pins)
    assert any(o & 2 for o in out[:n_break + BIT]), "break not flagged"
    assert got == payload, (got.hex(), payload.hex())
    assert out[-1] & 2 == 0, "flag not cleared by the good frame"


def test_uart_plain_decoder_is_fooled_by_glitch():
    """Documents why uart_rx_frame exists: the plain decoder has no start
    verify, so a 2-cycle runt starts a frame."""
    pins = [1] * 16 + [0, 0] + [1] * 200
    got, _ = _decode("uart_rx.toml", pins)
    assert got == b"\xff"


# ---------------------------------------------------------------- SPI


def spi_wave(
    payload: bytes,
    rng: random.Random,
    high: tuple[int, int] = (2, 12),
    low: tuple[int, int] = (2, 12),
    gap: tuple[int, int] = (4, 40),
    noise: bool = True,
) -> list[int]:
    """Mode 0, MSB first. pin0 = MOSI, pin1 = SCK, pin2 = CS (active-low).

    Each SCK half period is drawn independently. MOSI changes on the falling
    edge with a random hold (0..low-1). Between bytes CS is high and MOSI
    toggles randomly if noise=True; the decoder waits CS low, samples only on
    rising SCK, then waits CS high, so it must ignore inter-byte noise.
    """
    wave: list[int] = []
    cs = 4  # pin 2 idle-high

    def idle(n: int):
        for _ in range(n):
            mosi = rng.getrandbits(1) if noise else 0
            wave.append(cs | mosi)  # CS=1, SCK=0

    idle(8)
    for byte in payload:
        mosi = 0
        for i in range(7, -1, -1):
            bit = (byte >> i) & 1
            lo = rng.randint(*low)
            hold = rng.randint(0, lo - 1) if i != 7 else 0
            # low half: old bit for `hold` cycles, then the new bit; CS=0
            for c in range(lo):
                mosi = mosi if c < hold else bit
                wave.append(mosi)
            hi = rng.randint(*high)
            wave.extend([2 | bit] * hi)  # CS=0, SCK=1, MOSI stable
        wave.append(bit)  # final falling edge, CS still low
        idle(rng.randint(*gap))
    idle(16)
    return wave


@pytest.mark.parametrize("seed", SEEDS)
def test_spi_random_clock_gaps_noise(seed: int):
    rng = random.Random(seed)
    payload = bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 6)))
    pins = spi_wave(payload, rng)
    got, _ = _decode("spi_rx.toml", pins)
    assert got == payload, (seed, payload.hex(), got.hex())


@pytest.mark.parametrize("seed", range(8))
def test_spi_fastest_legal_clock(seed: int):
    """2+2 cycle SCK (the decoder's floor) with 4-cycle gaps still decodes."""
    rng = random.Random(seed)
    payload = bytes(rng.getrandbits(8) for _ in range(4))
    pins = spi_wave(payload, rng, high=(2, 2), low=(2, 2), gap=(4, 4), noise=True)
    got, _ = _decode("spi_rx.toml", pins)
    assert got == payload, (payload.hex(), got.hex())
