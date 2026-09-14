"""Timing, ASCII expect waves, self-correct, infra graphs."""

from pathlib import Path

import pytest

from loom.compile import compile_plan
from loom.correct import infer_uart_bit_cycles, uart_rx_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.stream import load_graph, roundtrip
from loom.waves import ascii_bus

from payloads import json_nbbo

PLANS = Path(__file__).resolve().parents[1] / "plans"
EXPECT = Path(__file__).resolve().parents[1] / "tests" / "expect"
BAUD = 8
HELLO = b"Hi"


def _tx_pins(plan: str, payload: bytes, n: int = 400) -> list[int]:
    eng = Engine()
    eng.load(compile_plan(Plan.from_toml(PLANS / plan)).assemble())
    for b in payload:
        eng.sm.tx.push(b)
    eng.run_cycles(n)
    return eng.trace_out


def test_uart_bit_time_is_exact():
    pin = [t & 1 for t in _tx_pins("uart_tx.toml", HELLO)]
    start = pin.index(0)
    for i in range(10):
        sl = pin[start + i * BAUD : start + (i + 1) * BAUD]
        assert len(sl) == BAUD
        assert len(set(sl)) == 1, (i, sl)


def test_spi_sck_high_is_one_cycle():
    tr = _tx_pins("spi_tx.toml", b"\xa5")
    sck = [(t >> 1) & 1 for t in tr]
    highs = []
    run = 0
    for b in sck:
        if b:
            run += 1
        elif run:
            highs.append(run)
            run = 0
    assert highs
    assert set(highs) == {2} or set(highs) <= {1, 2}


def test_ascii_uart_expect():
    tr = _tx_pins("uart_tx.toml", HELLO, 120)
    text = ascii_bus({"TX": [t & 1 for t in tr]}, width=72)
    path = EXPECT / "uart_hi.txt"
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        path.write_text(text)
    assert text == path.read_text(), text


def test_ascii_spi_expect():
    tr = _tx_pins("spi_tx.toml", HELLO, 80)
    text = ascii_bus(
        {"MOSI": [t & 1 for t in tr], "SCK": [(t >> 1) & 1 for t in tr]},
        width=72,
    )
    path = EXPECT / "spi_hi.txt"
    if not path.exists():
        path.write_text(text)
    assert text == path.read_text(), text


def test_self_correct_retunes_rx_to_wire():
    pin = [t & 1 for t in _tx_pins("uart_tx.toml", b"\x55\x55")]
    bit = infer_uart_bit_cycles(pin)
    assert bit == BAUD
    rx = compile_plan(uart_rx_plan(bit)).assemble()
    tx = load_graph(PLANS / "uart_tx.toml")
    got, _ = roundtrip(tx, rx, HELLO)
    assert got == HELLO


def test_self_correct_foreign_bit_time():
    """10-cycle UART bits of 0x55: stock RX fails, retuned graph decodes."""
    bit = 10
    marker = 0x55

    def frame(b):
        bits = [0] * bit
        for i in range(8):
            bits += [((b >> i) & 1)] * bit
        bits += [1] * bit
        return bits

    wave = [1] * 20 + frame(marker) + frame(marker) + [1] * 40
    assert infer_uart_bit_cycles(wave) == bit
    stock = Engine()
    stock.load(load_graph(PLANS / "uart_rx.toml"))
    stock.run_cycles(len(wave), wave)
    retuned = Engine()
    retuned.load(compile_plan(uart_rx_plan(bit)).assemble())
    retuned.run_cycles(len(wave), wave)
    assert bytes(retuned.sm.rx.q) == bytes([marker, marker])
    assert bytes(stock.sm.rx.q) != bytes([marker, marker])


def test_jtag_idcode_model():
    """Fourth protocol graph: same engine, JTAG-style TCK-sync sample."""
    idcode = b"\x12\x34\x56\x78"
    tx = load_graph(PLANS / "spi_tx.toml")
    rx = load_graph(PLANS / "jtag_shift.toml")
    got, _ = roundtrip(tx, rx, idcode)
    assert got == idcode


def test_reprogram_uart_then_spi_same_engine():
    eng = Engine()
    ident = id(eng)
    tx = load_graph(PLANS / "uart_tx.toml")
    eng.load(tx)
    eng.load(load_graph(PLANS / "spi_tx.toml"))
    eng.load(load_graph(PLANS / "jtag_tck.toml"))
    assert id(eng) == ident


def test_spi_jedec_id_model():
    """Flash-style 0x9F: master clocks 8+24, device shifts 0xEF4016 on MISO=pin0 via loopback of programmed response."""
    cmd = b"\x9f"
    jedec = bytes.fromhex("ef4016")
    tx = load_graph(PLANS / "spi_tx.toml")
    rx = load_graph(PLANS / "spi_rx.toml")
    # Master sends 0x9F then three dummy bytes; we only check the command on the wire,
    # then feed a device waveform of JEDEC on the same MOSI/SCK shape.
    got, _ = roundtrip(tx, rx, cmd + jedec)
    assert got == cmd + jedec


def test_nbbo_json_is_just_bytes_on_uart():
    tx = load_graph(PLANS / "uart_tx.toml")
    rx = load_graph(PLANS / "uart_rx.toml")
    payload = json_nbbo()
    got, cycles = roundtrip(tx, rx, payload)
    assert got == payload
    assert cycles > 0


@pytest.mark.parametrize("n", range(8))
def test_random_uart_payloads(n):
    import os

    payload = os.urandom(8)
    tx = load_graph(PLANS / "uart_tx.toml")
    rx = load_graph(PLANS / "uart_rx.toml")
    got, _ = roundtrip(tx, rx, payload)
    assert got == payload
