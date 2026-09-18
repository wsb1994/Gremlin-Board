"""Desk-infra tests in simulation (T1–T8). No FPGA, no analog PHY."""

from pathlib import Path

from loom.baud import clkdiv
from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.isa import N_SLOTS
from loom.stream import load_graph, roundtrip

PLANS = Path(__file__).resolve().parents[1] / "plans"


def _cfg(eng: Engine, name: str, sm: int = 0, slot: int | None = None) -> None:
    plan = Plan.from_toml(PLANS / name)
    words = compile_plan(plan).assemble()
    eng.load(words, sm=sm, slot=slot)
    smobj = eng.sms[sm]
    smobj.wrap_bottom = plan.wrap_bottom
    smobj.wrap_top = plan.wrap_top
    smobj.sideset_count = plan.sideset_count
    smobj.side_base = plan.side_base


def test_t1_uart_8n1_115200_hi():
    i, f = clkdiv(50_000_000, 115200, 8)
    tx = load_graph(PLANS / "uart_8n1_tx.toml")
    rx = load_graph(PLANS / "uart_8n1_rx.toml")
    got, _ = roundtrip(tx, rx, b"Hi")
    assert got == b"Hi"
    sm = 50_000_000 / (i + f / 256)
    baud = sm / 8
    assert abs(baud - 115200) / 115200 < 0.001


def test_t2_spi_jedec_0x9f():
    got, _ = roundtrip(
        load_graph(PLANS / "spi_burst_tx.toml"),
        load_graph(PLANS / "spi_burst_rx.toml"),
        bytes.fromhex("9fef4016"),
    )
    assert got == bytes.fromhex("9fef4016")


def test_t3_i2c_eeprom_16_bytes():
    # 0xA0 = 7-bit addr 0x50 write; then 16 payload bytes through the 1-byte OD pipe.
    payload = bytes([0xA0]) + bytes(range(16))
    got, _ = roundtrip(
        load_graph(PLANS / "i2c_od_tx.toml"),
        load_graph(PLANS / "i2c_od_rx.toml"),
        payload,
        max_cycles=64 + len(payload) * 400,
    )
    assert got == payload


def test_t4_jtag_32bit_idcode():
    idcode = b"\x12\x34\x56\x78"
    got, _ = roundtrip(
        load_graph(PLANS / "jtag_tx.toml"),
        load_graph(PLANS / "jtag_shift.toml"),
        idcode,
    )
    assert got == idcode


def test_t5_swd_dpidr_32bit():
    dpidr = b"\x77\x14\x27\x1b"
    got, _ = roundtrip(
        load_graph(PLANS / "swd_tx.toml"),
        load_graph(PLANS / "swd_rx.toml"),
        dpidr,
    )
    assert got == dpidr


def test_t6_uart_bit_width_within_2pct():
    eng = Engine()
    _cfg(eng, "uart_8n1_tx.toml")
    eng.sm.tx.push(0x00)
    eng.run_cycles(80)
    pin = [t & 1 for t in eng.trace_out]
    start = pin.index(0)
    # start + 8 zero data bits should be 9 bit-times of 0 at 8 SM-cycles/bit
    zeros = 0
    for b in pin[start:]:
        if b:
            break
        zeros += 1
    assert abs(zeros - 9 * 8) / (9 * 8) < 0.02


def test_t7_dual_sm_uart_and_spi():
    eng = Engine(n_sm=2, n_slots=N_SLOTS)
    _cfg(eng, "uart_8n1_tx.toml", sm=0, slot=0)
    _cfg(eng, "spi_tx_p345.toml", sm=1, slot=1)
    eng.sms[0].tx.push(ord("H"))
    eng.sms[1].tx.push(0x9F)
    eng.run_cycles(200)
    uart = [t & 1 for t in eng.trace_out]
    cs = [(t >> 5) & 1 for t in eng.trace_out]
    sck = [(t >> 4) & 1 for t in eng.trace_out]
    assert 0 in uart
    assert 0 in cs
    assert 1 in sck
    oe = 0
    for e in eng.trace_oe:
        oe |= e
    assert oe & 1
    assert oe & (1 << 5)


def test_t8_reprogram_in_place():
    eng = Engine()
    _cfg(eng, "uart_tx.toml")
    eng.sm.tx.push(ord("H"))
    eng.run_cycles(40)
    _cfg(eng, "spi_tx.toml")
    eng.sm.tx.push(0xA5)
    eng.run_cycles(80)
    cs = [(t >> 2) & 1 for t in eng.trace_out]
    assert 0 in cs
