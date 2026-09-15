"""Competition and design criteria, checked in Python before any RTL emit.

A criterion is a predicate over engine source, graphs, and interpreter runs.
If this module raises, Verilog generation is not allowed.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE_CORE = (
    ROOT / "generator" / "loom" / "isa.py",
    ROOT / "generator" / "loom" / "interp.py",
    ROOT / "generator" / "loom" / "compile.py",
    ROOT / "generator" / "loom" / "ir.py",
)

# These names belong in graphs (plans/), not in the executor.
PROTOCOL_NAMES = ("uart", "spi", "i2c", "usb", "ethernet", "jtag", "sdcard")

REQUIRED_PRIMITIVES = frozenset(
    {
        "pull",
        "push",
        "set_pins",
        "set_pindirs",
        "wait_pin",
        "out_lsb",
        "out_msb",
        "in_lsb",
        "in_msb",
        "delay",
        "jmp",
        "jmp_x_dec",
        "jmp_y_eq0",
        "mov",
        "set_x",
        "set_bit",
        "clr_bit",
    }
)


def engine_source() -> str:
    return "\n".join(p.read_text().lower() for p in ENGINE_CORE)


def assert_engine_has_no_protocol_names() -> None:
    src = engine_source()
    hits = [n for n in PROTOCOL_NAMES if n in src]
    if hits:
        raise AssertionError(
            "engine core names a protocol; protocols must be graphs, not ISA: "
            + ", ".join(hits)
        )


def assert_pin_and_time_primitives() -> None:
    from loom.ir import PRIMITIVES

    missing = REQUIRED_PRIMITIVES - set(PRIMITIVES)
    if missing:
        raise AssertionError(f"missing pin/time primitives: {sorted(missing)}")


def assert_criteria() -> None:
    assert_engine_has_no_protocol_names()
    assert_pin_and_time_primitives()
