"""Constrained-random 4-byte pin roundtrips on UART and SPI graphs."""

import random
from pathlib import Path

import pytest

from loom.stream import load_graph, roundtrip

PLANS = Path(__file__).resolve().parents[1] / "plans"

_rng = random.Random(0)
PAYLOADS = [bytes(_rng.getrandbits(8) for _ in range(4)) for _ in range(16)]


@pytest.mark.parametrize("proto", ("uart", "spi"))
@pytest.mark.parametrize("idx", range(16))
def test_random_4byte_roundtrip(proto: str, idx: int):
    payload = PAYLOADS[idx]
    tx = load_graph(PLANS / f"{proto}_tx.toml")
    rx = load_graph(PLANS / f"{proto}_rx.toml")
    got, cycles = roundtrip(tx, rx, payload)
    assert got == payload, (proto, idx, payload, got, cycles)
