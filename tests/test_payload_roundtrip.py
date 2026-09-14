"""Round-trip every payload on every wire graph (interpreter)."""

from pathlib import Path

import pytest

from loom.stream import load_graph, roundtrip

from payloads import PAYLOADS, PROTOCOLS

PLANS = Path(__file__).resolve().parents[1] / "plans"


@pytest.mark.parametrize("proto", PROTOCOLS)
@pytest.mark.parametrize("name", sorted(PAYLOADS))
def test_interp_roundtrip(proto: str, name: str):
    payload = PAYLOADS[name]
    assert payload, name
    tx = load_graph(PLANS / f"{proto}_tx.toml")
    rx = load_graph(PLANS / f"{proto}_rx.toml")
    got, cycles = roundtrip(tx, rx, payload)
    assert got == payload, (proto, name, got[:32], payload[:32], cycles)
