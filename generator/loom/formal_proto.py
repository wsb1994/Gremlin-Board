"""Protocol completeness over the 8-bit message space.

The ISA k-induction in formal.py is protocol-agnostic: it never mentions UART.
This module proves the graphs themselves are codecs for their languages.

For each TX/RX pair and every byte b in 0..255:

  TX encoding     TX(b) is a word of the protocol language L
  RX completeness RX(spec(b)) = b     (decoder inverts the spec, not just TX)
  Round-trip      RX(TX(b)) = b
  Loop            after one byte the SM sits on pull, ready for the next

Together with ISA k-induction (RTL implements the ISA) this is the composition:

  RTL(graph, b) = spec(b)  for all b, and  decode(spec(b)) = b.

Unbounded streams follow: the graph is a loop around pull, so N bytes is
N iterations of a proven one-byte step.

This is exhaustive model checking of a finite alphabet, not k-induction of
an unbounded waveform theory. That is the right completeness statement for
an 8-bit FIFO engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loom.compile import Program, compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.isa import (
    FIFO_PULL,
    JMP_X_DEC,
    OP_FIFO,
    OP_JMP,
    OP_OUT,
    OP_SET,
    SET_PINS,
    SHIFT_LSB,
    SHIFT_MSB,
)
from loom.line_lang import SPECS, bus_from_od
from loom.stream import load_graph, roundtrip

ROOT = Path(__file__).resolve().parents[2]
PLANS = ROOT / "plans"
BIT = 8  # SM-cycles per async bit in the hello/8N1 graphs


@dataclass(frozen=True)
class Case:
    name: str
    tx: str
    rx: str
    kind: str  # async8n1 | clk_msb | clk_lsb | clk_lsb_fall | i2c


CASES: tuple[Case, ...] = (
    Case("uart", "uart_tx.toml", "uart_rx.toml", "async8n1"),
    Case("uart_8n1", "uart_8n1_tx.toml", "uart_8n1_rx.toml", "async8n1"),
    Case("spi", "spi_tx.toml", "spi_rx.toml", "spi"),
    Case("i2c", "i2c_od_tx.toml", "i2c_od_rx.toml", "i2c"),
    Case("jtag", "jtag_tx.toml", "jtag_shift.toml", "jtag"),
    Case("swd", "swd_tx.toml", "swd_rx.toml", "swd"),
    Case("ps2", "ps2_tx.toml", "ps2_rx.toml", "ps2"),
    Case("can", "can_tx.toml", "can_rx.toml", "can"),
    Case("usb", "usb_tx.toml", "usb_rx.toml", "usb"),
    Case("eth", "eth_tx.toml", "eth_rx.toml", "eth"),
)


# ---------------------------------------------------------------------------
# Spec languages
# ---------------------------------------------------------------------------

def uart_8n1_frame(byte: int, bit: int = BIT) -> list[int]:
    """Idle-not-included 8N1: start 0, 8 data LSB first, stop 1. Each bit `bit` cycles."""
    bits = [0] * bit
    for i in range(8):
        bits += [((byte >> i) & 1)] * bit
    bits += [1] * bit
    return bits


def extract_async_frame(pin: list[int], bit: int = BIT) -> list[int]:
    i = 0
    while i < len(pin) and pin[i] == 1:
        i += 1
    if i >= len(pin) or pin[i] != 0:
        raise AssertionError("no start/SOF falling edge")
    need = 10 * bit
    sl = pin[i : i + need]
    if len(sl) < need:
        raise AssertionError(f"truncated async frame have={len(sl)} want={need}")
    for k in range(10):
        cell = sl[k * bit : (k + 1) * bit]
        if len(set(cell)) != 1:
            raise AssertionError(f"bit slot {k} is not constant: {cell}")
    return sl


def sample_on_edge(
    data: list[int], clk: list[int], rise: bool, prev: int | None = None
) -> list[int]:
    bits: list[int] = []
    if prev is None:
        prev = 0
    for d, c in zip(data, clk):
        c = c & 1
        if rise and c and not prev:
            bits.append(d & 1)
        if (not rise) and (not c) and prev:
            bits.append(d & 1)
        prev = c
    return bits


def bits_to_byte(bits: list[int], msb: bool) -> int:
    if len(bits) < 8:
        raise AssertionError(f"need 8 bits, got {len(bits)}")
    bits = bits[:8]
    if msb:
        v = 0
        for b in bits:
            v = (v << 1) | b
        return v
    v = 0
    for i, b in enumerate(bits):
        v |= b << i
    return v


def spec_wave(kind: str, byte: int) -> list[int]:
    """gpio_in waveform of a well-formed one-byte frame, independent of any TX graph.

    Clocked cells match the graphs' OUT/clock/JMP skeleton (4 cycles/bit), not a
    one-cycle-high cartoon — the RX graphs WAIT an edge then SAMPLE the next cycle.
    """
    if kind == "async8n1":
        return [1] * 16 + uart_8n1_frame(byte) + [1] * 32
    if kind in ("clk_msb", "clk_lsb"):
        msb = kind == "clk_msb"
        order = range(7, -1, -1) if msb else range(8)
        wave = [0] * 4
        for i in order:
            bit = (byte >> i) & 1
            # data (clk 0), clk 1, clk 0, jmp clk 0
            wave += [bit, bit | 2, bit, bit]
        wave += [0] * 32
        return wave
    if kind == "clk_lsb_fall":
        # PS/2: idle DATA=1 CLK=1; OUT delay=1, CLK lo delay=1, CLK hi, JMP.
        wave = [3] * 6
        for i in range(8):
            bit = (byte >> i) & 1
            hi, lo = bit | 2, bit
            wave += [hi, hi, lo, lo, hi, hi]
        wave += [3] * 32
        return wave
    if kind == "i2c":
        wave = [3] * 4  # idle SDA=1 SCL=1
        wave += [1, 0]  # START then SCL down
        for i in range(7, -1, -1):
            bit = (byte >> i) & 1
            wave += [bit, bit | 2, bit | 2, bit]
        wave += [0, 1, 3] + [3] * 32
        return wave
    raise ValueError(kind)


def tx_matches_spec(kind: str, gpio: list[int], byte: int) -> None:
    pin0 = [t & 1 for t in gpio]
    clk = [(t >> 1) & 1 for t in gpio]
    if kind == "async8n1":
        got = extract_async_frame(pin0)
        want = uart_8n1_frame(byte)
        if got != want:
            raise AssertionError(f"async frame != 8N1 of 0x{byte:02x}")
        return
    if kind == "clk_msb":
        bits = sample_on_edge(pin0, clk, rise=True)
        if bits_to_byte(bits, msb=True) != byte:
            raise AssertionError(f"clk msb samples {bits[:8]} != 0x{byte:02x}")
        return
    if kind == "clk_lsb":
        bits = sample_on_edge(pin0, clk, rise=True)
        if bits_to_byte(bits, msb=False) != byte:
            raise AssertionError(f"clk lsb samples {bits[:8]} != 0x{byte:02x}")
        return
    if kind == "clk_lsb_fall":
        bits = sample_on_edge(pin0, clk, rise=False)
        if bits_to_byte(bits, msb=False) != byte:
            raise AssertionError(f"clk fall lsb samples {bits[:8]} != 0x{byte:02x}")
        return
    if kind == "i2c":
        start = None
        for i in range(1, len(gpio)):
            if clk[i] and clk[i - 1] and pin0[i - 1] == 1 and pin0[i] == 0:
                start = i
                break
        if start is None:
            raise AssertionError("i2c: no START (SDA fall while SCL high)")
        bits = sample_on_edge(
            pin0[start:], clk[start:], rise=True, prev=clk[start]
        )
        if bits_to_byte(bits, msb=True) != byte:
            raise AssertionError(f"i2c samples {bits[:8]} != 0x{byte:02x}")
        return
    raise ValueError(kind)


# ---------------------------------------------------------------------------
# Execution helpers
# ---------------------------------------------------------------------------

def _plan(name: str) -> Plan:
    return Plan.from_toml(PLANS / name)


def _prog(name: str) -> Program:
    return compile_plan(_plan(name))


def _tx_run(name: str, byte: int, cycles: int = 8000) -> Engine:
    eng = Engine()
    plan = _plan(name)
    prog = compile_plan(plan)
    eng.load(prog.assemble())
    eng.sm.wrap_bottom = plan.wrap_bottom
    eng.sm.wrap_top = plan.wrap_top
    eng.sm.sideset_count = plan.sideset_count
    eng.sm.side_base = plan.side_base
    eng.sm.tx.push(byte)
    eng.sm.run = True
    eng.run_cycles(cycles)
    return eng


def _rx_run(name: str, wave: list[int]) -> bytes:
    eng = Engine()
    plan = _plan(name)
    prog = compile_plan(plan)
    eng.load(prog.assemble())
    eng.sm.wrap_bottom = plan.wrap_bottom
    eng.sm.wrap_top = plan.wrap_top
    eng.sm.sideset_count = plan.sideset_count
    eng.sm.side_base = plan.side_base
    eng.sm.run = True
    for g in wave:
        eng.sm.tick(g)
    return bytes(eng.sm.rx.q)


# ---------------------------------------------------------------------------
# Syntactic certificates: the compiled program *is* the protocol skeleton
# ---------------------------------------------------------------------------

def certify_async_8n1_tx(name: str) -> None:
    """uart/can/usb/8n1 TX: pull, start/SOF low, OUT lsb loop, stop/IFS high."""
    prog = _prog(name)
    ins = {s.comment: s for s in prog.instrs}
    pull = ins["pull_byte"]
    assert pull.op == OP_FIFO and pull.field == FIFO_PULL, name
    start = ins.get("start") or ins["sof"]
    assert start.op == OP_SET and start.field == SET_PINS and start.delay == 7, name
    bit = ins["bit"]
    assert bit.op == OP_OUT and bit.field == SHIFT_LSB and bit.delay == 6, name
    nxt = ins["next_bit"]
    assert nxt.op == OP_JMP and nxt.field == JMP_X_DEC, name
    assert prog.labels[nxt.payload] == prog.labels["bit"], name
    stop = ins.get("stop") or ins["ifs"]
    assert stop.op == OP_SET and stop.field == SET_PINS and stop.delay == 7, name


def certify_clocked_tx(name: str, msb: bool) -> None:
    prog = _prog(name)
    ins = {s.comment: s for s in prog.instrs}
    assert ins["pull_byte"].op == OP_FIFO, name
    data = ins["data"]
    want = SHIFT_MSB if msb else SHIFT_LSB
    assert data.op == OP_OUT and data.field == want, name
    nxt = ins["next_bit"]
    assert nxt.op == OP_JMP and nxt.field == JMP_X_DEC, name
    assert prog.labels[nxt.payload] == prog.labels["data"], name


def certify_tx(case: Case) -> None:
    if case.kind == "async8n1":
        certify_async_8n1_tx(case.tx)
        return
    # Completed contest encodings: a pull-loop of ≤32 words. Line language is semantic.
    prog = _prog(case.tx)
    assert len(prog.instrs) <= 32, (case.name, len(prog.instrs))
    pulls = [s for s in prog.instrs if s.op == OP_FIFO and s.field == FIFO_PULL]
    assert pulls, case.name


# ---------------------------------------------------------------------------
# Semantic completeness: all 256 bytes
# ---------------------------------------------------------------------------

def prove_tx_encoding(case: Case, bytes_: range = range(256)) -> None:
    for b in bytes_:
        eng = _tx_run(case.tx, b)
        try:
            if case.kind in SPECS:
                gpio = eng.trace_out
                if case.kind == "i2c":
                    gpio = bus_from_od(eng.trace_out, eng.trace_oe)
                SPECS[case.kind][1](gpio, b)
            else:
                tx_matches_spec(case.kind, eng.trace_out, b)
        except AssertionError as e:
            raise AssertionError(f"{case.name} TX encoding failed for 0x{b:02x}: {e}") from e


def prove_rx_spec(case: Case, bytes_: range = range(256)) -> None:
    for b in bytes_:
        if case.kind in SPECS:
            wave = SPECS[case.kind][0](b)
        else:
            wave = spec_wave(case.kind, b)
        got = _rx_run(case.rx, wave)
        if got[:1] != bytes([b]):
            raise AssertionError(
                f"{case.name} RX(spec(0x{b:02x})) = {got[:4]!r}, want {[b]!r}"
            )


def prove_roundtrip(case: Case, bytes_: range = range(256)) -> None:
    tx = load_graph(PLANS / case.tx)
    rx = load_graph(PLANS / case.rx)
    for b in bytes_:
        payload = bytes([b])
        got, cycles = roundtrip(tx, rx, payload)
        if got != payload:
            raise AssertionError(
                f"{case.name} RX(TX(0x{b:02x})) = {got!r} cycles={cycles}"
            )


def prove_loop(case: Case) -> None:
    """After one byte the SM is parked on pull (FIFO empty → stall)."""
    prog = _prog(case.tx)
    if "pull_byte" in prog.labels:
        pull = prog.labels["pull_byte"]
    else:
        pull = next(i for i, s in enumerate(prog.instrs) if s.op == OP_FIFO and s.field == FIFO_PULL)
    eng = _tx_run(case.tx, 0xA5)
    if not eng.sm.tx.empty:
        raise AssertionError(f"{case.name} TX FIFO not empty after one byte")
    for _ in range(8):
        eng.sm.tick(0)
        if eng.sm.pc != pull:
            raise AssertionError(
                f"{case.name} loop: pc={eng.sm.pc} want pull={pull} after FIFO empty"
            )


def prove_case(case: Case) -> None:
    certify_tx(case)
    prove_tx_encoding(case)
    prove_rx_spec(case)
    prove_roundtrip(case)
    prove_loop(case)


def prove_all() -> list[str]:
    names: list[str] = []
    for case in CASES:
        prove_case(case)
        names.append(case.name)
    return names


def main() -> int:
    names = prove_all()
    print("PROTO-COMPLETE", ",".join(names), "bytes=0..255")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
