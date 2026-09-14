"""Amaranth graph-node executor. Same cycle semantics as loom.interp.SM."""

from __future__ import annotations

from amaranth import Array, Cat, Elaboratable, Module, Mux, Signal

from loom.isa import (
    CLR_BIT,
    FIFO_DEPTH,
    FIFO_PULL,
    IMEM_WORDS,
    JMP_ALWAYS,
    JMP_PIN,
    JMP_X_DEC,
    JMP_X_EQ0,
    JMP_Y_DEC,
    OP_FIFO,
    OP_IN,
    OP_JMP,
    OP_NOP,
    OP_OUT,
    OP_SET,
    OP_WAIT,
    SET_BIT,
    SET_INPIN,
    SET_OUTPIN,
    SET_PINDIRS,
    SET_PINS,
    SET_X,
    SET_Y,
    SHIFT_LSB,
)


class GraphEngine(Elaboratable):
    def __init__(self, n_sm: int = 1) -> None:
        if n_sm not in (1, 2):
            raise ValueError("n_sm must be 1 or 2")
        self.n_sm = n_sm
        self.run = Signal()
        self.gpio_in = Signal(8)
        self.gpio_out = Signal(8)
        self.gpio_oe = Signal(8)
        self.imem_we = Signal()
        self.imem_waddr = Signal(5)
        self.imem_wdata = Signal(16)
        self.tx_we = Signal()
        self.tx_data = Signal(8)
        self.tx_full = Signal()
        self.rx_re = Signal()
        self.rx_data = Signal(8)
        self.rx_empty = Signal(reset=1)
        self.pc = Signal(5)
        if n_sm > 1:
            self.imem_sel = Signal(1)

    def elaborate(self, platform) -> Module:
        m = Module()
        n = self.n_sm

        pcs = [self.pc]
        xs = [Signal(8, name="x")]
        ys = [Signal(8, name="y")]
        osrs = [Signal(8, name="osr")]
        isrs = [Signal(8, name="isr")]
        delay_ctrs = [Signal(5, name="delay_ctr")]
        out_pins = [Signal(3, name="out_pin")]
        in_pins = [Signal(3, name="in_pin")]
        imems = [Array(Signal(16, name=f"iw{i}") for i in range(IMEM_WORDS))]
        instrs = [Signal(16, name="instr")]
        # n_sm=1: gpio ports *are* the SM registers (emit.py / 1-SM tests).
        if n == 1:
            out_regs = [self.gpio_out]
            oe_regs = [self.gpio_oe]
        else:
            out_regs = [Signal(8, name=f"out{s}") for s in range(n)]
            oe_regs = [Signal(8, name=f"oe{s}") for s in range(n)]
        for s in range(1, n):
            pcs.append(Signal(5, name=f"pc{s}"))
            xs.append(Signal(8, name=f"x{s}"))
            ys.append(Signal(8, name=f"y{s}"))
            osrs.append(Signal(8, name=f"osr{s}"))
            isrs.append(Signal(8, name=f"isr{s}"))
            delay_ctrs.append(Signal(5, name=f"delay_ctr{s}"))
            out_pins.append(Signal(3, name=f"out_pin{s}"))
            in_pins.append(Signal(3, name=f"in_pin{s}"))
            imems.append(
                Array(Signal(16, name=f"iw{s}_{i}") for i in range(IMEM_WORDS))
            )
            instrs.append(Signal(16, name=f"instr{s}"))

        if n > 1:
            m.d.comb += [
                self.gpio_out.eq(out_regs[0] | out_regs[1]),
                self.gpio_oe.eq(oe_regs[0] | oe_regs[1]),
            ]

        for s in range(n):
            m.d.comb += instrs[s].eq(imems[s][pcs[s]])

        with m.If(self.imem_we & ~self.run):
            if n == 1:
                m.d.sync += imems[0][self.imem_waddr].eq(self.imem_wdata)
            else:
                with m.If(self.imem_sel == 0):
                    m.d.sync += imems[0][self.imem_waddr].eq(self.imem_wdata)
                with m.Else():
                    m.d.sync += imems[1][self.imem_waddr].eq(self.imem_wdata)

        tx_mem = Array(Signal(8, name=f"tx{i}") for i in range(FIFO_DEPTH))
        rx_mem = Array(Signal(8, name=f"rx{i}") for i in range(FIFO_DEPTH))
        tx_r = Signal(2)
        tx_w = Signal(2)
        tx_n = Signal(3)
        rx_r = Signal(2)
        rx_w = Signal(2)
        rx_n = Signal(3)
        m.d.comb += [
            self.tx_full.eq(tx_n == FIFO_DEPTH),
            self.rx_empty.eq(rx_n == 0),
            self.rx_data.eq(rx_mem[rx_r]),
        ]
        do_pulls = [Signal(name=f"do_pull{s}") for s in range(n)]
        do_pushs = [Signal(name=f"do_push{s}") for s in range(n)]
        do_pull = Signal()
        do_push = Signal()
        pull_or = do_pulls[0]
        push_or = do_pushs[0]
        for s in range(1, n):
            pull_or = pull_or | do_pulls[s]
            push_or = push_or | do_pushs[s]
        m.d.comb += [do_pull.eq(pull_or), do_push.eq(push_or)]
        host_tx = Signal()
        host_rx = Signal()
        m.d.comb += [
            host_tx.eq(self.tx_we & (tx_n != FIFO_DEPTH)),
            host_rx.eq(self.rx_re & (rx_n != 0)),
        ]
        with m.If(host_tx):
            m.d.sync += [
                tx_mem[tx_w].eq(self.tx_data),
                tx_w.eq(tx_w + 1),
            ]
        with m.If(host_tx & ~do_pull):
            m.d.sync += tx_n.eq(tx_n + 1)
        with m.Elif(~host_tx & do_pull):
            m.d.sync += tx_n.eq(tx_n - 1)
        with m.If(do_pull):
            m.d.sync += tx_r.eq(tx_r + 1)
        with m.If(host_rx):
            m.d.sync += rx_r.eq(rx_r + 1)
        with m.If(host_rx & ~do_push):
            m.d.sync += rx_n.eq(rx_n - 1)
        with m.Elif(~host_rx & do_push):
            m.d.sync += rx_n.eq(rx_n + 1)
        with m.If(do_push):
            m.d.sync += rx_w.eq(rx_w + 1)

        eff = Signal(8)
        for i in range(8):
            m.d.comb += eff[i].eq(Mux(self.gpio_oe[i], self.gpio_out[i], self.gpio_in[i]))

        # Internal state handles for formal harnesses / debug (not ports).
        self.dbg = dict(
            x=xs, y=ys, osr=osrs, isr=isrs, delay_ctr=delay_ctrs, out_pin=out_pins,
            in_pin=in_pins, imem=imems, instr=instrs, tx_mem=tx_mem, rx_mem=rx_mem,
            tx_r=tx_r, tx_w=tx_w, tx_n=tx_n, rx_r=rx_r, rx_w=rx_w, rx_n=rx_n,
            do_pull=do_pull, do_push=do_push, eff=eff, pcs=pcs,
            out_regs=out_regs, oe_regs=oe_regs,
        )

        with m.If(self.run):
            for s in range(n):
                self._elab_sm(
                    m,
                    s,
                    pc=pcs[s],
                    x=xs[s],
                    y=ys[s],
                    osr=osrs[s],
                    isr=isrs[s],
                    delay_ctr=delay_ctrs[s],
                    out_pin=out_pins[s],
                    in_pin=in_pins[s],
                    out_reg=out_regs[s],
                    oe_reg=oe_regs[s],
                    instr=instrs[s],
                    eff=eff,
                    do_pull=do_pulls[s],
                    do_push=do_pushs[s],
                    tx_n=tx_n,
                    rx_n=rx_n,
                    tx_mem=tx_mem,
                    rx_mem=rx_mem,
                    tx_r=tx_r,
                    rx_w=rx_w,
                )
        return m

    def _elab_sm(
        self,
        m: Module,
        s: int,
        *,
        pc,
        x,
        y,
        osr,
        isr,
        delay_ctr,
        out_pin,
        in_pin,
        out_reg,
        oe_reg,
        instr,
        eff,
        do_pull,
        do_push,
        tx_n,
        rx_n,
        tx_mem,
        rx_mem,
        tx_r,
        rx_w,
    ) -> None:
        op = instr[13:16]
        delay = instr[8:13]
        field = instr[5:8]
        payload = instr[0:5]
        stall = Signal(name=f"stall{s}")
        next_pc = Signal(5, name=f"next_pc{s}")
        with m.If(delay_ctr != 0):
            m.d.sync += delay_ctr.eq(delay_ctr - 1)
        with m.Else():
            m.d.comb += stall.eq(0)
            m.d.comb += next_pc.eq(pc + 1)
            with m.Switch(op):
                with m.Case(OP_JMP):
                    with m.Switch(field):
                        with m.Case(JMP_ALWAYS):
                            m.d.comb += next_pc.eq(payload)
                        with m.Case(JMP_X_EQ0):
                            with m.If(x == 0):
                                m.d.comb += next_pc.eq(payload)
                        with m.Case(JMP_X_DEC):
                            with m.If(x != 0):
                                m.d.sync += x.eq(x - 1)
                                m.d.comb += next_pc.eq(payload)
                        with m.Case(JMP_Y_DEC):
                            with m.If(y != 0):
                                m.d.sync += y.eq(y - 1)
                                m.d.comb += next_pc.eq(payload)
                        with m.Case(JMP_PIN):
                            with m.If(eff.bit_select(in_pin, 1)):
                                m.d.comb += next_pc.eq(payload)
                with m.Case(OP_WAIT):
                    pin = payload[0:4]
                    pol = payload[4]
                    with m.If(eff.bit_select(pin, 1) != pol):
                        m.d.comb += stall.eq(1)
                with m.Case(OP_OUT):
                    bit = Mux(field == SHIFT_LSB, osr[0], osr[7])
                    mask = Signal(8, name=f"mask{s}")
                    m.d.comb += mask.eq(1 << out_pin)
                    m.d.sync += out_reg.eq(Mux(bit, out_reg | mask, out_reg & ~mask))
                    with m.If(field == SHIFT_LSB):
                        m.d.sync += osr.eq(osr >> 1)
                    with m.Else():
                        m.d.sync += osr.eq(osr << 1)
                with m.Case(OP_IN):
                    sample = eff.bit_select(in_pin, 1)
                    with m.If(field == SHIFT_LSB):
                        m.d.sync += isr.eq(Cat(isr[1:8], sample))
                    with m.Else():
                        m.d.sync += isr.eq(Cat(sample, isr[0:7]))
                with m.Case(OP_FIFO):
                    with m.If(field == FIFO_PULL):
                        with m.If(tx_n == 0):
                            m.d.comb += stall.eq(1)
                        with m.Else():
                            m.d.comb += do_pull.eq(1)
                            m.d.sync += osr.eq(tx_mem[tx_r])
                    with m.Else():
                        with m.If(rx_n == FIFO_DEPTH):
                            m.d.comb += stall.eq(1)
                        with m.Else():
                            m.d.comb += do_push.eq(1)
                            m.d.sync += rx_mem[rx_w].eq(isr)
                with m.Case(OP_SET):
                    with m.Switch(field):
                        with m.Case(SET_PINS):
                            m.d.sync += out_reg[:5].eq(payload)
                        with m.Case(SET_PINDIRS):
                            m.d.sync += oe_reg[:5].eq(payload)
                        with m.Case(SET_X):
                            m.d.sync += x.eq(payload)
                        with m.Case(SET_Y):
                            m.d.sync += y.eq(payload)
                        with m.Case(SET_BIT):
                            m.d.sync += out_reg.eq(out_reg | (1 << payload[0:3]))
                        with m.Case(CLR_BIT):
                            m.d.sync += out_reg.eq(out_reg & ~(1 << payload[0:3]))
                        with m.Case(SET_OUTPIN):
                            m.d.sync += out_pin.eq(payload[0:3])
                        with m.Case(SET_INPIN):
                            m.d.sync += in_pin.eq(payload[0:3])
                with m.Case(OP_NOP):
                    pass
            with m.If(~stall):
                m.d.sync += [
                    pc.eq(next_pc),
                    delay_ctr.eq(delay),
                ]
