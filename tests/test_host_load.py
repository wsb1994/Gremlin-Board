"""Host load: imem write while run=0, TX push, then run.

Tests the GraphEngine ports the Tiny Tapeout wrapper (emit.py WRAPPER)
is supposed to drive, plus a cycle-accurate model of that wrapper's
two-phase pin protocol.
"""

from amaranth.sim import Simulator

from loom.isa import (
    FIFO_DEPTH,
    FIFO_PULL,
    JMP_ALWAYS,
    OP_FIFO,
    OP_JMP,
    OP_SET,
    SET_PINS,
    encode,
)
from loom.rtl import GraphEngine

# SET pins=0x15 → 0xC015 (low 0x15, high 0xC0). JMP always to 1 → 0x0001.
WORD_SET = encode(OP_SET, field=SET_PINS, payload=0x15)
WORD_JMP1 = encode(OP_JMP, field=JMP_ALWAYS, payload=1)
WORD_PULL = encode(OP_FIFO, field=FIFO_PULL)
TX_BYTE = 0x48  # 'H'


def _run(dut, tb) -> None:
    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()


def test_engine_load_imem_word_then_run():
    """Direct GraphEngine ports: write one 16-bit word, set run."""
    dut = GraphEngine()
    gpio = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, WORD_SET)
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.imem_waddr, 1)
        ctx.set(dut.imem_wdata, WORD_JMP1)
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.run, 1)
        await ctx.tick()
        gpio.append(ctx.get(dut.gpio_out) & 0x1F)
        assert ctx.get(dut.pc) == 1

    _run(dut, tb)
    assert gpio == [0x15]


def test_engine_push_tx_byte_then_run():
    """Direct ports: push a TX byte while halted, then PULL consumes it."""
    dut = GraphEngine()
    full_after_push = []
    full_after_pull = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        ctx.set(dut.imem_waddr, 0)
        ctx.set(dut.imem_wdata, WORD_PULL)
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.imem_waddr, 1)
        ctx.set(dut.imem_wdata, WORD_JMP1)
        ctx.set(dut.imem_we, 1)
        await ctx.tick()
        ctx.set(dut.imem_we, 0)
        ctx.set(dut.tx_data, TX_BYTE)
        ctx.set(dut.tx_we, 1)
        await ctx.tick()
        ctx.set(dut.tx_we, 0)
        full_after_push.append(ctx.get(dut.tx_full))
        ctx.set(dut.run, 1)
        await ctx.tick()
        full_after_pull.append(ctx.get(dut.tx_full))
        assert ctx.get(dut.pc) == 1

    _run(dut, tb)
    assert full_after_push == [0]
    assert full_after_pull == [0]


def test_engine_tx_full_after_depth_pushes():
    dut = GraphEngine()
    flags = []

    async def tb(ctx):
        ctx.set(dut.run, 0)
        for i in range(FIFO_DEPTH):
            ctx.set(dut.tx_data, i)
            ctx.set(dut.tx_we, 1)
            await ctx.tick()
            flags.append(ctx.get(dut.tx_full))
        ctx.set(dut.tx_we, 0)

    _run(dut, tb)
    assert flags[-1] == 1
    assert flags[:-1] == [0] * (FIFO_DEPTH - 1)


class _Wrap:
    """Cycle-accurate model of emit.py WRAPPER around GraphEngine ports."""

    def __init__(self):
        self.we_d = 0
        self.tx_d = 0
        self.hi = 0
        self.addr = 0
        self.lo = 0
        self.nib_hi = 0
        self.nib_lo = 0

    async def cycle(self, ctx, dut, ui_in: int, uio_in: int) -> None:
        run = ui_in & 1
        we = ((ui_in >> 1) & 1) and not run
        fifo_stb = (ui_in >> 7) & 1
        dir_rx = (ui_in >> 2) & 1
        imem_we = we and (not self.we_d) and self.hi and not fifo_stb
        tx_we_halt = fifo_stb and (not self.tx_d) and (not we) and (not dir_rx) and (not run)
        tx_we_run = fifo_stb and (not self.tx_d) and (not dir_rx) and run and self.nib_hi
        rx_re = fifo_stb and (not self.tx_d) and dir_rx
        tx_data = (((ui_in >> 3) & 0xF) << 4) | self.nib_lo if run else (uio_in & 0xFF)
        wdata = ((uio_in & 0xFF) << 8) | (self.lo & 0xFF)
        ctx.set(dut.run, run)
        ctx.set(dut.gpio_in, 0 if run else uio_in)
        ctx.set(dut.imem_we, int(imem_we))
        ctx.set(dut.imem_waddr, self.addr)
        ctx.set(dut.imem_wdata, wdata)
        ctx.set(dut.tx_we, int(tx_we_halt or tx_we_run))
        ctx.set(dut.tx_data, tx_data)
        ctx.set(dut.rx_re, int(rx_re))
        await ctx.tick()
        if run:
            self.hi = 0
            if fifo_stb and (not self.tx_d) and (not dir_rx):
                if not self.nib_hi:
                    self.nib_lo = (ui_in >> 3) & 0xF
                    self.nib_hi = 1
                else:
                    self.nib_hi = 0
        else:
            self.nib_hi = 0
            if we and not self.we_d:
                if fifo_stb:
                    pass
                elif not self.hi:
                    self.addr = (ui_in >> 2) & 0x1F
                    self.lo = uio_in & 0xFF
                    self.hi = 1
                else:
                    self.hi = 0
        self.we_d = we
        self.tx_d = fifo_stb


def _ui(run=0, we=0, addr=0, tx=0) -> int:
    return (run & 1) | ((we & 1) << 1) | ((addr & 0x1F) << 2) | ((tx & 1) << 7)


async def _pulse_we(ctx, dut, w: _Wrap, addr: int, data: int) -> None:
    await w.cycle(ctx, dut, _ui(we=1, addr=addr), data & 0xFF)
    await w.cycle(ctx, dut, _ui(we=0, addr=addr), data & 0xFF)


async def _pulse_tx(ctx, dut, w: _Wrap, data: int) -> None:
    await w.cycle(ctx, dut, _ui(tx=1), data & 0xFF)
    await w.cycle(ctx, dut, _ui(tx=0), data & 0xFF)


async def _load_word(ctx, dut, w: _Wrap, addr: int, word: int) -> None:
    await _pulse_we(ctx, dut, w, addr, word & 0xFF)
    await _pulse_we(ctx, dut, w, addr, (word >> 8) & 0xFF)


def test_wrapper_two_phase_imem_tx_then_run():
    """Byte-accurate wrapper sequence: load W, push TX byte, set run."""
    dut = GraphEngine()
    w = _Wrap()
    saw = {}

    async def tb(ctx):
        await w.cycle(ctx, dut, _ui(), 0)
        await _load_word(ctx, dut, w, 0, WORD_SET)
        await _load_word(ctx, dut, w, 1, WORD_JMP1)
        await _pulse_tx(ctx, dut, w, TX_BYTE)
        saw["tx_full"] = ctx.get(dut.tx_full)
        await w.cycle(ctx, dut, _ui(run=1), 0)
        saw["gpio"] = ctx.get(dut.gpio_out) & 0x1F
        saw["pc"] = ctx.get(dut.pc)
        saw["hi_cleared"] = w.hi

    _run(dut, tb)
    assert WORD_SET == 0xC015
    assert (WORD_SET & 0xFF) == 0x15
    assert (WORD_SET >> 8) == 0xC0
    assert saw == {"tx_full": 0, "gpio": 0x15, "pc": 1, "hi_cleared": 0}


def test_wrapper_one_strobe_does_not_commit():
    dut = GraphEngine()
    w = _Wrap()
    gpio = []

    async def tb(ctx):
        await w.cycle(ctx, dut, _ui(), 0)
        await _pulse_we(ctx, dut, w, 0, WORD_SET & 0xFF)
        await w.cycle(ctx, dut, _ui(run=1), 0)
        gpio.append(ctx.get(dut.gpio_out) & 0x1F)

    _run(dut, tb)
    assert gpio == [0]


def test_wrapper_live_nibble_tx_while_running():
    """While run=1, two nibbles on ui_in[6:3] fill TX without releasing GPIO."""
    dut = GraphEngine()
    w = _Wrap()
    osr = []

    async def tb(ctx):
        await w.cycle(ctx, dut, _ui(), 0)
        await _load_word(ctx, dut, w, 0, WORD_PULL)
        await _load_word(ctx, dut, w, 1, encode(OP_JMP, field=JMP_ALWAYS, payload=1))
        await w.cycle(ctx, dut, _ui(run=1), 0)
        lo, hi = TX_BYTE & 0xF, (TX_BYTE >> 4) & 0xF
        await w.cycle(ctx, dut, 1 | (lo << 3) | 0x80, 0)
        await w.cycle(ctx, dut, 1 | (lo << 3), 0)
        await w.cycle(ctx, dut, 1 | (hi << 3) | 0x80, 0)
        await w.cycle(ctx, dut, 1 | (hi << 3), 0)
        await w.cycle(ctx, dut, _ui(run=1), 0)
        osr.append(ctx.get(dut.dbg["osr"][0]))

    _run(dut, tb)
    assert osr[-1] == TX_BYTE
