"""Optional second state machine: independent pins, default remains one SM."""

from amaranth.sim import Simulator

from loom.isa import OP_SET, SET_BIT, encode
from loom.interp import Engine
from loom.rtl import GraphEngine


def _set_bit(pin: int) -> list[int]:
    return [encode(OP_SET, 0, SET_BIT, pin)]


def test_n_sm_default_is_one():
    assert Engine().n_sm == 1


def test_interp_sm0_pin0_sm1_idle():
    eng = Engine(n_sm=2)
    eng.load(_set_bit(0), sm=0)
    eng.run_cycles(4)
    assert eng.trace_out[-1] & 1
    assert (eng.trace_out[-1] & 0b10) == 0
    assert eng.sms[1].out_reg == 0


def test_interp_two_sms_independent_set_bit():
    eng = Engine(n_sm=2)
    eng.load(_set_bit(0), sm=0)
    eng.load(_set_bit(1), sm=1)
    eng.run_cycles(4)
    assert eng.trace_out[-1] & 0b11 == 0b11
    assert eng.sms[0].out_reg & 1
    assert eng.sms[1].out_reg & 2
    assert (eng.sms[0].out_reg & 2) == 0
    assert (eng.sms[1].out_reg & 1) == 0


def _rtl_gpio(n_sm: int, progs: list[list[int]], cycles: int = 8) -> list[int]:
    dut = GraphEngine(n_sm=n_sm)
    trace: list[int] = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        for sel, words in enumerate(progs):
            if n_sm > 1:
                ctx.set(dut.imem_sel, sel)
            for i, w in enumerate(words):
                ctx.set(dut.imem_waddr, i)
                ctx.set(dut.imem_wdata, w)
                ctx.set(dut.imem_we, 1)
                await ctx.tick()
        ctx.set(dut.imem_we, 0)
        if n_sm > 1:
            ctx.set(dut.imem_sel, 0)
        ctx.set(dut.run, 1)
        for _ in range(cycles):
            await ctx.tick()
            trace.append(ctx.get(dut.gpio_out))

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    return trace


def test_rtl_sm0_pin0_sm1_idle():
    got = _rtl_gpio(2, [_set_bit(0)])
    assert got[-1] & 1
    assert (got[-1] & 0b10) == 0


def test_rtl_two_sms_independent_set_bit():
    gold = Engine(n_sm=2)
    gold.load(_set_bit(0), sm=0)
    gold.load(_set_bit(1), sm=1)
    gold.run_cycles(8)
    got = _rtl_gpio(2, [_set_bit(0), _set_bit(1)])
    assert got == gold.trace_out
    assert got[-1] & 0b11 == 0b11
