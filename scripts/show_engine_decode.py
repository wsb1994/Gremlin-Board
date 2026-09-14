#!/usr/bin/env python3
"""Engine decode: RX graphs read the same pins the TX graphs just drove."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generator"))

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan

PLANS = ROOT / "plans"
HELLO = b"Hi"
CYCLES = 500


def words(plan: str) -> list[int]:
    return compile_plan(Plan.from_toml(PLANS / plan)).assemble()


def encode(plan: str) -> list[int]:
    eng = Engine()
    eng.load(words(plan))
    for b in HELLO:
        eng.sm.tx.push(b)
    eng.run_cycles(CYCLES)
    return eng.trace_out


def decode(plan: str, gpio: list[int]) -> bytes:
    eng = Engine()
    eng.load(words(plan))
    eng.run_cycles(len(gpio), gpio)
    return bytes(eng.sm.rx.q)


def decode_blank(gpio: list[int]) -> bytes:
    """Same pins, empty program — proves decode is the graph, not the core."""
    eng = Engine()
    eng.run_cycles(len(gpio), gpio)
    return bytes(eng.sm.rx.q)


def line(label: str, value: bytes) -> None:
    hexes = " ".join(f"{b:02x}" for b in value)
    print(f"  {label:18s} {value!r:12s}  [{hexes}]")


def main() -> None:
    pairs = (
        ("UART", "uart_tx.toml", "uart_rx.toml"),
        ("SPI", "spi_tx.toml", "spi_rx.toml"),
        ("I2C", "i2c_tx.toml", "i2c_rx.toml"),
    )
    print(f"payload in: {HELLO!r}\n")
    for name, tx, rx in pairs:
        pins = encode(tx)
        got = decode(rx, pins)
        none = decode_blank(pins)
        print(f"{name}")
        line("engine TX graph", HELLO)
        line("engine RX graph", got)
        line("engine, no graph", none)
        print()


if __name__ == "__main__":
    main()
