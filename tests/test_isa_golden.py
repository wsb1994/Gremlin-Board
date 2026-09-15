"""Interp vs RTL golden snapshots for every ISA opcode."""

from amaranth import Signal
from amaranth.sim import Simulator
import pytest

from loom.isa import (
    CLR_BIT,
    FIFO_PULL,
    FIFO_PUSH,
    JMP_ALWAYS,
    JMP_PIN,
    JMP_X_DEC,
    JMP_X_EQ0,
    JMP_Y_DEC,
    JMP_Y_EQ0,
    OP_FIFO,
    OP_IN,
    OP_JMP,
    OP_MOV,
    OP_NOP,
    OP_OUT,
    OP_SET,
    OP_WAIT,
    REG_OSR,
    REG_X,
    SET_BIT,
    SET_INPIN,
    SET_OUTPIN,
    SET_PINDIRS,
    SET_PINS,
    SET_X,
    SET_Y,
    SHIFT_LSB,
    SHIFT_MSB,
    encode,
)
from loom.interp import SM
from loom.rtl import GraphEngine


def _rtl_regs(sim):
    found = {}
    seen = set()

    def walk(obj, depth=0):
        oid = id(obj)
        if oid in seen or depth > 25:
            return
        seen.add(oid)
        if isinstance(obj, Signal):
            if obj.name in ("x", "y", "osr", "isr"):
                found[obj.name] = obj
            return
        if isinstance(obj, (str, bytes, bytearray, int, float, bool, type(None), type)):
            return
        if isinstance(obj, dict):
            for v in obj.values():
                walk(v, depth + 1)
            return
        if isinstance(obj, (list, tuple, set, frozenset)):
            for v in obj:
                walk(v, depth + 1)
            return
        d = getattr(obj, "__dict__", None)
        if d:
            for v in list(d.values()):
                walk(v, depth + 1)

    walk(sim._design.fragment.statements)
    return found


def _snap(sm: SM) -> dict[str, int]:
    return {
        "pc": sm.pc,
        "x": sm.x,
        "y": sm.y,
        "osr": sm.osr,
        "isr": sm.isr,
        "gpio_out": sm.out_reg,
    }


def _run_interp(words, cycles, gpio_in=0, tx=()):
    sm = SM()
    sm.load(words)
    sm.run = True
    for b in tx:
        sm.tx.push(b)
    gin = gpio_in if isinstance(gpio_in, (list, tuple)) else None
    for i in range(cycles):
        sm.tick(gin[i] if gin is not None else gpio_in)
    return _snap(sm)


def _run_rtl(words, cycles, gpio_in=0, tx=()):
    dut = GraphEngine()
    gin = gpio_in if isinstance(gpio_in, (list, tuple)) else None
    got = {}

    async def tb(ctx):
        ctx.set(dut.run, 0)
        for i, w in enumerate(words):
            ctx.set(dut.imem_waddr, i)
            ctx.set(dut.imem_wdata, w)
            ctx.set(dut.imem_we, 1)
            await ctx.tick()
        ctx.set(dut.imem_we, 0)
        for b in tx:
            ctx.set(dut.tx_data, b)
            ctx.set(dut.tx_we, 1)
            await ctx.tick()
        ctx.set(dut.tx_we, 0)
        regs = _rtl_regs(sim)
        ctx.set(dut.run, 1)
        for i in range(cycles):
            ctx.set(dut.gpio_in, gin[i] if gin is not None else gpio_in)
            await ctx.tick()
        got.update(
            pc=ctx.get(dut.pc),
            x=ctx.get(regs["x"]),
            y=ctx.get(regs["y"]),
            osr=ctx.get(regs["osr"]),
            isr=ctx.get(regs["isr"]),
            gpio_out=ctx.get(dut.gpio_out),
        )

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    return got


def _case(name, words, cycles, gpio_in: int | list[int] = 0, tx=()):
    return (name, words, cycles, gpio_in, tuple(tx))


CASES = [
    _case("nop", [encode(OP_NOP)], 2),
    _case("nop_delay", [encode(OP_NOP, delay=2), encode(OP_SET, field=SET_X, payload=5)], 5),
    _case("jmp_always", [encode(OP_JMP, field=JMP_ALWAYS, payload=0), encode(OP_SET, field=SET_X, payload=1)], 4),
    _case("jmp_x_eq0_taken", [encode(OP_JMP, field=JMP_X_EQ0, payload=0)], 3),
    _case(
        "jmp_x_eq0_not",
        [encode(OP_SET, field=SET_X, payload=1), encode(OP_JMP, field=JMP_X_EQ0, payload=0)],
        2,
    ),
    _case(
        "jmp_x_dec",
        [encode(OP_SET, field=SET_X, payload=2), encode(OP_JMP, field=JMP_X_DEC, payload=1)],
        6,
    ),
    _case(
        "jmp_y_dec",
        [encode(OP_SET, field=SET_Y, payload=2), encode(OP_JMP, field=JMP_Y_DEC, payload=1)],
        6,
    ),
    _case("jmp_pin_taken", [encode(OP_JMP, field=JMP_PIN, payload=0), encode(OP_SET, field=SET_X, payload=1)], 3, 1),
    _case("jmp_pin_not", [encode(OP_JMP, field=JMP_PIN, payload=0), encode(OP_SET, field=SET_X, payload=1)], 3, 0),
    _case(
        "wait_true",
        [encode(OP_WAIT, payload=0x10), encode(OP_SET, field=SET_X, payload=9)],
        3,
        1,
    ),
    _case(
        "wait_stall_then_go",
        [encode(OP_WAIT, payload=0x10), encode(OP_SET, field=SET_X, payload=9)],
        5,
        [0, 0, 0, 1, 1],
    ),
    _case(
        "wait_pol0",
        [encode(OP_WAIT, payload=0x00), encode(OP_SET, field=SET_Y, payload=4)],
        4,
        [1, 1, 0, 0],
    ),
    _case("in_lsb", [encode(OP_IN, field=SHIFT_LSB, payload=1), encode(OP_NOP)], 2, 1),
    _case("in_msb", [encode(OP_IN, field=SHIFT_MSB, payload=1), encode(OP_NOP)], 2, 1),
    _case(
        "in_lsb_bits",
        [encode(OP_IN, field=SHIFT_LSB, payload=1)] * 3 + [encode(OP_NOP)],
        4,
        [1, 0, 1, 0],
    ),
    _case(
        "out_lsb",
        [
            encode(OP_FIFO, field=FIFO_PULL),
            encode(OP_SET, field=SET_PINDIRS, payload=1),
            encode(OP_OUT, field=SHIFT_LSB, payload=1),
            encode(OP_NOP),
        ],
        4,
        tx=(0b00000101,),
    ),
    _case(
        "out_msb",
        [
            encode(OP_FIFO, field=FIFO_PULL),
            encode(OP_SET, field=SET_PINDIRS, payload=1),
            encode(OP_OUT, field=SHIFT_MSB, payload=1),
            encode(OP_NOP),
        ],
        4,
        tx=(0b10000000,),
    ),
    _case(
        "out_pin2",
        [
            encode(OP_SET, field=SET_OUTPIN, payload=2),
            encode(OP_FIFO, field=FIFO_PULL),
            encode(OP_OUT, field=SHIFT_LSB, payload=1),
        ],
        3,
        tx=(0x01,),
    ),
    _case("fifo_pull", [encode(OP_FIFO, field=FIFO_PULL), encode(OP_NOP)], 2, tx=(0xA5,)),
    _case(
        "fifo_push",
        [encode(OP_IN, field=SHIFT_MSB, payload=1), encode(OP_FIFO, field=FIFO_PUSH), encode(OP_NOP)],
        3,
        1,
    ),
    _case(
        "fifo_pull_stall",
        [encode(OP_FIFO, field=FIFO_PULL), encode(OP_SET, field=SET_X, payload=1)],
        4,
    ),
    _case("set_pins", [encode(OP_SET, field=SET_PINS, payload=0x15)], 1),
    _case("set_pindirs", [encode(OP_SET, field=SET_PINDIRS, payload=0x0F)], 1),
    _case("set_x", [encode(OP_SET, field=SET_X, payload=7)], 1),
    _case("set_y", [encode(OP_SET, field=SET_Y, payload=3), encode(OP_NOP)], 2),
    _case("set_bit", [encode(OP_SET, field=SET_BIT, payload=3)], 1),
    _case(
        "clr_bit",
        [encode(OP_SET, field=SET_PINS, payload=0x1F), encode(OP_SET, field=CLR_BIT, payload=2)],
        2,
    ),
    _case(
        "set_bit_then_clr",
        [
            encode(OP_SET, field=SET_BIT, payload=0),
            encode(OP_SET, field=SET_BIT, payload=7),
            encode(OP_SET, field=CLR_BIT, payload=0),
        ],
        3,
    ),
    _case(
        "set_outpin_inpin",
        [
            encode(OP_SET, field=SET_OUTPIN, payload=3),
            encode(OP_SET, field=SET_INPIN, payload=2),
            encode(OP_SET, field=SET_BIT, payload=3),
        ],
        3,
    ),
    _case(
        "set_inpin_then_in",
        [
            encode(OP_SET, field=SET_INPIN, payload=2),
            encode(OP_IN, field=SHIFT_MSB, payload=1),
            encode(OP_NOP),
        ],
        3,
        0b00000100,
    ),
    _case("mov_x_from_osr", [encode(OP_FIFO, field=FIFO_PULL), encode(OP_MOV, field=REG_X, payload=REG_OSR)], 3, tx=(0xA5,)),
    _case("jmp_y_eq0_taken", [encode(OP_JMP, field=JMP_Y_EQ0, payload=0)], 3),
    _case(
        "jmp_y_eq0_not",
        [encode(OP_SET, field=SET_Y, payload=1), encode(OP_JMP, field=JMP_Y_EQ0, payload=0)],
        2,
    ),
    _case(
        "set_delay_then_nop",
        [encode(OP_SET, delay=3, field=SET_Y, payload=11), encode(OP_SET, field=SET_X, payload=1)],
        6,
    ),
]


@pytest.mark.parametrize(
    "name,words,cycles,gpio_in,tx",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_isa_golden(name, words, cycles, gpio_in, tx):
    gold = _run_interp(words, cycles, gpio_in=gpio_in, tx=tx)
    got = _run_rtl(words, cycles, gpio_in=gpio_in, tx=tx)
    assert got == gold, (name, gold, got)
