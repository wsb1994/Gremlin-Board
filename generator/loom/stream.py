"""Stream bytes through a TX graph and a RX graph on the same pins."""

from __future__ import annotations

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan


_WRAP: dict[tuple[int, ...], tuple[int, int, int, int]] = {}


def load_graph(path) -> list[int]:
    plan = Plan.from_toml(path)
    words = compile_plan(plan).assemble()
    _WRAP[tuple(words)] = (
        plan.wrap_bottom,
        plan.wrap_top,
        plan.sideset_count,
        plan.side_base,
    )
    return words


def _wired_and(tx: Engine, rx: Engine, pullup: int = 0xFF) -> int:
    """Protocol-agnostic GPIO: driven bits override pull-up; two drivers AND."""
    bus = pullup
    for sm in (tx.sm, rx.sm):
        for i in range(8):
            if (sm.oe_reg >> i) & 1:
                if not ((sm.out_reg >> i) & 1):
                    bus &= ~(1 << i)
                # drive-1 leaves pull-up/other as-is (wired-AND)
    return bus


def roundtrip(
    tx_words: list[int],
    rx_words: list[int],
    payload: bytes,
    max_cycles: int | None = None,
) -> tuple[bytes, int]:
    if max_cycles is None:
        max_cycles = 64 + len(payload) * 800
    tx = Engine()
    rx = Engine()
    tx.load(tx_words)
    rx.load(rx_words)
    tb, tt, tsc, tsb = _WRAP.get(tuple(tx_words), (0, 31, 0, 0))
    rb, rt, rsc, rsb = _WRAP.get(tuple(rx_words), (0, 31, 0, 0))
    tx.sm.wrap_bottom, tx.sm.wrap_top = tb, tt
    rx.sm.wrap_bottom, rx.sm.wrap_top = rb, rt
    tx.sm.sideset_count, tx.sm.side_base = tsc, tsb
    rx.sm.sideset_count, rx.sm.side_base = rsc, rsb
    tx.sm.run = True
    rx.sm.run = True
    src = list(payload)
    got: list[int] = []
    idle = 0
    cyc = 0
    for cyc in range(max_cycles):
        if src and not tx.sm.tx.full:
            tx.sm.tx.push(src.pop(0))
        bus = _wired_and(tx, rx)
        tx.sm.tick(bus)
        rx.sm.tick(bus)
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
