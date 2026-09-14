"""Stream bytes through a TX graph and a RX graph on the same pins."""

from __future__ import annotations

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan


def load_graph(path) -> list[int]:
    return compile_plan(Plan.from_toml(path)).assemble()


def roundtrip(
    tx_words: list[int],
    rx_words: list[int],
    payload: bytes,
    max_cycles: int | None = None,
) -> tuple[bytes, int]:
    if max_cycles is None:
        max_cycles = 64 + len(payload) * 120
    tx = Engine()
    rx = Engine()
    tx.load(tx_words)
    rx.load(rx_words)
    tx.sm.run = True
    rx.sm.run = True
    src = list(payload)
    got: list[int] = []
    idle = 0
    cyc = 0
    for cyc in range(max_cycles):
        if src and not tx.sm.tx.full:
            tx.sm.tx.push(src.pop(0))
        tx.sm.tick(0)
        rx.sm.tick(tx.sm.out_reg)
        if not rx.sm.rx.empty:
            b = rx.sm.rx.pop()
            if b is not None:
                got.append(b)
                idle = 0
        else:
            idle += 1
        if not src and len(got) >= len(payload) and tx.sm.tx.empty:
            break
        if idle > 512 and len(got) >= len(payload):
            break
    return bytes(got), cyc + 1
