"""UART 8N1 encode/decode on the production graphs: framing, jitter, dual-SM."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.stream import load_graph, roundtrip

from test_random_jitter import uart_wave

PLANS = Path(__file__).resolve().parents[1] / "plans"
SEEDS = range(12)


def _apply(eng: Engine, name: str, sm: int = 0, slot: int | None = None) -> None:
    plan = Plan.from_toml(PLANS / name)
    eng.load(compile_plan(plan).assemble(), sm=sm, slot=slot)
    smobj = eng.sms[sm]
    smobj.wrap_bottom = plan.wrap_bottom
    smobj.wrap_top = plan.wrap_top


def _decode(plan: str, pins: list[int]) -> tuple[bytes, list[int]]:
    eng = Engine()
    _apply(eng, plan)
    eng.sm.run = True
    got: list[int] = []
    out: list[int] = []
    for g in pins:
        eng.sm.tick(g)
        out.append(eng.sm.out_reg)
        if not eng.sm.rx.empty:
            got.append(eng.sm.rx.pop())
    return bytes(got), out


@pytest.mark.parametrize("seed", SEEDS)
def test_uart_8n1_random_in_band(seed: int):
    rng = random.Random(seed)
    payload = bytes(rng.getrandbits(8) for _ in range(rng.randint(1, 6)))
    err = rng.uniform(-0.03, 0.03)
    pins = uart_wave(payload, rng, baud_err=err, jitter=1)
    got, out = _decode("uart_8n1_rx.toml", pins)
    assert got == payload, (seed, err, payload.hex(), got.hex())
    assert not any(o & 2 for o in out), "frame flag on a clean frame"


def test_uart_8n1_roundtrip_payloads():
    tx = load_graph(PLANS / "uart_8n1_tx.toml")
    rx = load_graph(PLANS / "uart_8n1_rx.toml")
    for payload in (b"Hi", b"\x00\xff", b"UART10"):
        got, _ = roundtrip(tx, rx, payload)
        assert got == payload


def test_uart_8n1_runt_start_rejected():
    # 2-cycle glitch low, then idle; decoder must not emit a byte
    pins = [1] * 8 + [0, 0] + [1] * 40
    got, out = _decode("uart_8n1_rx.toml", pins)
    assert got == b""


def test_uart_8n1_bad_stop_sets_flag():
    rng = random.Random(0)
    # force stop bit low by building a raw frame: start+8 data+stop0
    byte = 0x55
    bits = [0] + [(byte >> i) & 1 for i in range(8)] + [0]
    pins = [1] * 8
    for b in bits:
        pins.extend([b] * 8)
    pins.extend([1] * 24)
    got, out = _decode("uart_8n1_rx.toml", pins)
    assert any(o & 2 for o in out), "expected frame-error flag on pin1"


def test_dual_sm_tx_and_rx_slots():
    eng = Engine(n_sm=2, n_slots=4)
    _apply(eng, "uart_8n1_tx.toml", sm=0, slot=0)
    _apply(eng, "uart_8n1_rx.toml", sm=1, slot=1)
    for b in b"Hi":
        eng.sms[0].tx.push(b)
    eng.run_cycles(400)
    got = bytes(eng.sms[1].rx.q)
    assert got == b"Hi", got
