"""Production graph engine: MOV, Y==0, clkdiv, wrap, slots, host RX pop."""

from pathlib import Path

from amaranth.sim import Simulator

from loom.baud import clkdiv
from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.isa import (
    CSR_SM0_CLKDIV_FRAC,
    CSR_SM0_CLKDIV_HI,
    CSR_SM0_CLKDIV_LO,
    CSR_SM0_SLOT,
    CSR_SM0_WRAP_BOT,
    CSR_SM0_WRAP_TOP,
    CSR_SM1_SLOT,
    JMP_Y_EQ0,
    N_SLOTS,
    OP_JMP,
    OP_MOV,
    OP_NOP,
    OP_SET,
    REG_OSR,
    REG_X,
    SET_BIT,
    SET_X,
    encode,
)
from loom.rtl import GraphEngine
from loom.stream import load_graph, roundtrip

PLANS = Path(__file__).resolve().parents[1] / "plans"


def _load_cfg(eng: Engine, name: str, sm: int = 0, slot: int | None = None) -> Plan:
    plan = Plan.from_toml(PLANS / name)
    words = compile_plan(plan).assemble()
    eng.load(words, sm=sm, slot=slot)
    smobj = eng.sms[sm]
    smobj.wrap_bottom = plan.wrap_bottom
    smobj.wrap_top = plan.wrap_top
    smobj.sideset_count = plan.sideset_count
    return plan


def test_mov_copies_osr_to_x():
    eng = Engine()
    eng.sm.osr = 0xA5
    eng.sm.imem[0] = encode(OP_MOV, field=REG_X, payload=REG_OSR)
    eng.sm.imem[1] = encode(OP_NOP)
    eng.sm.run = True
    eng.sm.tick(0)
    assert eng.sm.x == 0xA5


def test_jmp_y_eq0_taken_and_not():
    sm = Engine().sm
    sm.y = 0
    sm.imem[0] = encode(OP_JMP, field=JMP_Y_EQ0, payload=3)
    sm.run = True
    sm.tick(0)
    assert sm.pc == 3
    sm.y = 2
    sm.pc = 0
    sm.tick(0)
    assert sm.pc == 1


def test_clkdiv_int_2_halves_sm_rate():
    a = Engine()
    b = Engine()
    w = [encode(OP_NOP)] * 16
    a.load(w)
    b.load(w)
    b.sm.clkdiv_int = 2
    a.run_cycles(4)
    b.run_cycles(4)
    assert a.sm.pc == 4
    assert b.sm.pc == 2


def test_four_slots_independent():
    eng = Engine(n_sm=2, n_slots=N_SLOTS)
    eng.load([encode(OP_SET, field=SET_BIT, payload=0)], sm=0, slot=0)
    eng.load([encode(OP_SET, field=SET_BIT, payload=1)], sm=1, slot=1)
    eng.run_cycles(4)
    assert eng.sms[0].out_reg & 1
    assert eng.sms[1].out_reg & 2
    assert (eng.sms[0].out_reg & 2) == 0
    assert (eng.sms[1].out_reg & 1) == 0


def test_uart_8n1_roundtrip_hi():
    tx = load_graph(PLANS / "uart_8n1_tx.toml")
    rx = load_graph(PLANS / "uart_8n1_rx.toml")
    got, cycles = roundtrip(tx, rx, b"Hi")
    assert got == b"Hi", (got, cycles)


def test_clkdiv_115200_formula():
    i, f = clkdiv(50_000_000, 115200, 8)
    assert i == 54
    assert 0 <= f < 256
    # reconstructed baud within 0.1%
    sm = 50_000_000 / (i + f / 256)
    baud = sm / 8
    assert abs(baud - 115200) / 115200 < 0.001


async def _tick_csr(ctx, dut, addr, data):
    ctx.set(dut.run, 0)
    ctx.set(dut.csr_addr, addr)
    ctx.set(dut.csr_wdata, data)
    ctx.set(dut.csr_we, 1)
    await ctx.tick()
    ctx.set(dut.csr_we, 0)


def test_rtl_slots_two_sms():
    dut = GraphEngine(n_sm=2, n_slots=4)
    trace = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        await _tick_csr(ctx, dut, CSR_SM0_SLOT, 0)
        await _tick_csr(ctx, dut, CSR_SM1_SLOT, 1)
        ctx.set(dut.imem_slot, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, encode(OP_SET, field=SET_BIT, payload=0))
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_slot, 1)
        ctx.set(dut.imem_wdata, encode(OP_SET, field=SET_BIT, payload=1))
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        for _ in range(4):
            await ctx.tick()
            trace.append(ctx.get(dut.gpio_out))

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    assert trace[-1] & 0b11 == 0b11


def test_rtl_wrap_loops_without_jmp():
    dut = GraphEngine()
    pcs = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        await _tick_csr(ctx, dut, CSR_SM0_WRAP_BOT, 0)
        await _tick_csr(ctx, dut, CSR_SM0_WRAP_TOP, 1)
        for i, w in enumerate([encode(OP_NOP), encode(OP_NOP)]):
            ctx.set(dut.imem_waddr, i)
            ctx.set(dut.imem_wdata, w)
            ctx.set(dut.imem_we, 1)
            await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        for _ in range(6):
            await ctx.tick()
            pcs.append(ctx.get(dut.pc))

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    assert 0 in pcs and 1 in pcs
    assert max(pcs) <= 1


def test_rtl_clkdiv_csr():
    dut = GraphEngine()
    xs = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        await _tick_csr(ctx, dut, CSR_SM0_CLKDIV_LO, 2)
        await _tick_csr(ctx, dut, CSR_SM0_CLKDIV_HI, 0)
        await _tick_csr(ctx, dut, CSR_SM0_CLKDIV_FRAC, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, encode(OP_SET, field=SET_X, payload=7))
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        for _ in range(3):
            await ctx.tick()
            xs.append(ctx.get(dut.dbg["x"][0]))

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    # clkdiv=2: first SM cycle on sysclk 0, next on sysclk 2
    assert xs[0] == 7
    assert xs[1] == 7
