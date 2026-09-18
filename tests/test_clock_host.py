"""Clock divider, live FIFO, per-SM FIFOs, clocked imem, CS-hold jump."""

from amaranth.sim import Simulator

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.isa import (
    CSR_FIFO_SEL,
    CSR_SM0_CLKDIV_LO,
    FIFO_PULL,
    JMP_TX_NE,
    N_SLOTS,
    OP_FIFO,
    OP_JMP,
    OP_NOP,
    OP_SET,
    SET_BIT,
    SET_X,
    encode,
)
from loom.rtl import GraphEngine
from loom.stream import load_graph, roundtrip
from pathlib import Path

PLANS = Path(__file__).resolve().parents[1] / "plans"


def _run(dut, tb) -> None:
    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()


def test_rtl_clkdiv_zero_skips_next_cycle():
    dut = GraphEngine()
    xs = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        ctx.set(dut.csr_addr, CSR_SM0_CLKDIV_LO)
        ctx.set(dut.csr_wdata, 0)
        ctx.set(dut.csr_we, 1)
        await ctx.tick()
        ctx.set(dut.csr_we, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, encode(OP_SET, field=SET_X, payload=7))
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        for _ in range(3):
            await ctx.tick()
            xs.append(ctx.get(dut.dbg["x"][0]))

    _run(dut, tb)
    assert xs[0] == 7
    assert xs[1] == 7
    assert xs[2] == 7


def test_engine_tx_while_running():
    """Host may fill TX while GPIO is live (wrapper live path uses this)."""
    dut = GraphEngine()
    osr = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, encode(OP_FIFO, field=FIFO_PULL))
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_waddr, 1)
        ctx.set(dut.imem_wdata, encode(OP_NOP))
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        await ctx.tick()  # stall on empty
        ctx.set(dut.tx_data, 0xA5)
        ctx.set(dut.tx_we, 1)
        await ctx.tick()
        ctx.set(dut.tx_we, 0)
        await ctx.tick()
        osr.append(ctx.get(dut.dbg["osr"][0]))

    _run(dut, tb)
    assert osr[-1] == 0xA5


def test_per_sm_fifos_do_not_steal():
    dut = GraphEngine(n_sm=2)
    got = {}

    async def tb(ctx):
        ctx.set(dut.run, 0)
        ctx.set(dut.imem_sel, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, encode(OP_FIFO, field=FIFO_PULL))
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_sel, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.tx_data, 0x11)
        ctx.set(dut.tx_we, 1)
        await ctx.tick()
        ctx.set(dut.csr_addr, CSR_FIFO_SEL)
        ctx.set(dut.csr_wdata, 1)
        ctx.set(dut.csr_we, 1)
        ctx.set(dut.tx_we, 0)
        await ctx.tick()
        ctx.set(dut.csr_we, 0)
        ctx.set(dut.tx_data, 0x22)
        ctx.set(dut.tx_we, 1)
        await ctx.tick()
        ctx.set(dut.tx_we, 0)
        ctx.set(dut.run, 1)
        await ctx.tick()
        got["osr0"] = ctx.get(dut.dbg["osr"][0])
        got["osr1"] = ctx.get(dut.dbg["osr"][1]) if len(dut.dbg["osr"]) > 1 else None

    _run(dut, tb)
    assert got["osr0"] == 0x11
    assert got["osr1"] == 0x22


def test_clocked_imem_four_slot_preload():
    dut = GraphEngine(n_sm=2, n_slots=N_SLOTS)
    trace = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        ctx.set(dut.imem_slot, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, encode(OP_SET, field=SET_BIT, payload=0))
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_slot, 1)
        ctx.set(dut.imem_wdata, encode(OP_SET, field=SET_BIT, payload=1))
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        await ctx.tick()
        ctx.set(dut.run, 1)
        for _ in range(3):
            await ctx.tick()
            trace.append(ctx.get(dut.gpio_out))

    _run(dut, tb)
    assert trace[-1] & 0b11 == 0b11


def test_set_bit_drives_oe():
    eng = Engine()
    eng.sm.imem[0] = encode(OP_SET, field=SET_BIT, payload=5)
    eng.sm.run = True
    eng.sm.tick(0)
    assert eng.sm.out_reg & (1 << 5)
    assert eng.sm.oe_reg & (1 << 5)


def test_jmp_tx_ne_holds_cs_across_bytes():
    tx = load_graph(PLANS / "spi_burst_tx.toml")
    rx = load_graph(PLANS / "spi_burst_rx.toml")
    payload = bytes.fromhex("9fef4016")
    got, _ = roundtrip(tx, rx, payload)
    assert got == payload


def test_uart_fullduplex_pins():
    tx = load_graph(PLANS / "uart_8n1_tx.toml")
    rx = load_graph(PLANS / "uart_8n1_rx_p3.toml")
    # RX listens on pin3: feed TX pin0 onto pin3.
    eng = Engine()
    eng.load(tx)
    for b in b"Hi":
        eng.sm.tx.push(b)
    eng.run_cycles(400)
    wave = [((t & 1) << 3) | 0x01 for t in eng.trace_out]
    dec = Engine()
    dec.load(rx)
    dec.run_cycles(len(wave), wave)
    assert bytes(dec.sm.rx.q) == b"Hi"


def test_interp_jmp_tx_ne():
    sm = Engine().sm
    sm.imem[0] = encode(OP_JMP, field=JMP_TX_NE, payload=5)
    sm.imem[1] = encode(OP_NOP)
    sm.run = True
    sm.tick(0)
    assert sm.pc == 1
    sm.pc = 0
    sm.tx.push(1)
    sm.tick(0)
    assert sm.pc == 5
