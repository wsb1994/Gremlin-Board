"""Contest protocol graphs: UART/SPI/I2C/JTAG/SWD/PS2 plus USB/Ethernet/CAN bit-layer subsets."""

from pathlib import Path

import pytest

from loom.stream import load_graph, roundtrip

PLANS = Path(__file__).resolve().parents[1] / "plans"
HI = b"Hi"

# Contest list: UART, SPI, I2C, JTAG, SWD, PS/2, plus CAN/USB/Ethernet line codecs.
PAIRS = (
    ("uart", "uart_tx.toml", "uart_rx.toml"),
    ("uart_8n1", "uart_8n1_tx.toml", "uart_8n1_rx.toml"),
    ("spi", "spi_tx.toml", "spi_rx.toml"),
    ("i2c", "i2c_od_tx.toml", "i2c_od_rx.toml"),
    ("jtag", "jtag_tx.toml", "jtag_shift.toml"),
    ("swd", "swd_tx.toml", "swd_rx.toml"),
    ("ps2", "ps2_tx.toml", "ps2_rx.toml"),
    ("can", "can_tx.toml", "can_rx.toml"),
    ("usb", "usb_tx.toml", "usb_rx.toml"),
    ("eth", "eth_tx.toml", "eth_rx.toml"),
)


@pytest.mark.parametrize("name,tx,rx", PAIRS, ids=[p[0] for p in PAIRS])
def test_protocol_roundtrip_hi(name, tx, rx):
    tw = load_graph(PLANS / tx)
    rw = load_graph(PLANS / rx)
    got, cycles = roundtrip(tw, rw, HI)
    assert got == HI, (name, got, cycles)
    assert cycles > 0
