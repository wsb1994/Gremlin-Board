"""RTL must match the interpreter on the same graph and payload."""

from pathlib import Path

from amaranth.sim import Simulator

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.rtl import GraphEngine

PLANS = Path(__file__).resolve().parents[1] / "plans"
HELLO = b"Hi"
CYCLES = 200


def _words(name: str) -> list[int]:
    return compile_plan(Plan.from_toml(PLANS / name)).assemble()


def _interp_tx(name: str, payload: bytes, n: int) -> list[int]:
    eng = Engine()
    eng.load(_words(name))
    for b in payload:
        eng.sm.tx.push(b)
    eng.run_cycles(n)
    return eng.trace_out


def _rtl_tx(name: str, payload: bytes, n: int) -> list[int]:
    dut = GraphEngine()
    words = _words(name)
    trace: list[int] = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        for i, w in enumerate(words):
            ctx.set(dut.imem_waddr, i)
            ctx.set(dut.imem_wdata, w)
            ctx.set(dut.imem_we, 1)
            await ctx.tick()
        ctx.set(dut.imem_we, 0)
        for b in payload:
            ctx.set(dut.tx_data, b)
            ctx.set(dut.tx_we, 1)
            await ctx.tick()
        ctx.set(dut.tx_we, 0)
        ctx.set(dut.run, 1)
        for _ in range(n):
            await ctx.tick()
            trace.append(ctx.get(dut.gpio_out))

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    return trace


def _interp_rx(name: str, gpio: list[int]) -> bytes:
    eng = Engine()
    eng.load(_words(name))
    eng.run_cycles(len(gpio), gpio)
    return bytes(eng.sm.rx.q)


def _rtl_rx(name: str, gpio: list[int]) -> bytes:
    dut = GraphEngine()
    words = _words(name)
    got: list[int] = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        for i, w in enumerate(words):
            ctx.set(dut.imem_waddr, i)
            ctx.set(dut.imem_wdata, w)
            ctx.set(dut.imem_we, 1)
            await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        for gin in gpio:
            ctx.set(dut.gpio_in, gin)
            await ctx.tick()
        ctx.set(dut.run, 0)
        while ctx.get(dut.rx_empty) == 0:
            got.append(ctx.get(dut.rx_data))
            ctx.set(dut.rx_re, 1)
            await ctx.tick()
            ctx.set(dut.rx_re, 0)
            await ctx.tick()

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    return bytes(got)


def test_rtl_uart_tx_matches_interp():
    gold = _interp_tx("uart_tx.toml", HELLO, CYCLES)
    got = _rtl_tx("uart_tx.toml", HELLO, CYCLES)
    assert got == gold


def test_rtl_spi_tx_matches_interp():
    assert _rtl_tx("spi_tx.toml", HELLO, CYCLES) == _interp_tx("spi_tx.toml", HELLO, CYCLES)


def test_rtl_i2c_tx_matches_interp():
    assert _rtl_tx("i2c_tx.toml", HELLO, CYCLES) == _interp_tx("i2c_tx.toml", HELLO, CYCLES)


def test_rtl_uart_rx_decodes_hi():
    pins = _interp_tx("uart_tx.toml", HELLO, 400)
    assert _rtl_rx("uart_rx.toml", pins) == HELLO
    assert _rtl_rx("uart_rx.toml", pins) == _interp_rx("uart_rx.toml", pins)


def test_rtl_spi_rx_decodes_hi():
    pins = _interp_tx("spi_tx.toml", HELLO, 400)
    assert _rtl_rx("spi_rx.toml", pins) == HELLO


def test_rtl_i2c_rx_decodes_hi():
    pins = _interp_tx("i2c_tx.toml", HELLO, 400)
    assert _rtl_rx("i2c_rx.toml", pins) == HELLO
