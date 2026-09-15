"""Send a Big Chungus PNG over the wire graphs and confirm SHA-256 identity."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from loom.stream import load_graph, roundtrip

from payloads import big_chungus_png
from test_all_protocols import PAIRS

PLANS = Path(__file__).resolve().parents[1] / "plans"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_fixture_is_png():
    payload = big_chungus_png()
    assert payload.startswith(PNG_MAGIC)
    assert len(payload) > 32


@pytest.mark.parametrize("name,tx,rx", PAIRS, ids=[p[0] for p in PAIRS])
def test_big_chungus_png_sha256_roundtrip(name, tx, rx):
    payload = big_chungus_png()
    want = _sha256(payload)
    got, cycles = roundtrip(load_graph(PLANS / tx), load_graph(PLANS / rx), payload)
    got_hash = _sha256(got)
    assert got.startswith(PNG_MAGIC), (name, got[:16])
    assert got_hash == want, (
        f"{name}: sha256 mismatch want={want} got={got_hash} "
        f"bytes {len(got)}/{len(payload)} cycles={cycles}"
    )
    assert got == payload
    assert cycles > 0
