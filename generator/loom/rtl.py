"""Amaranth graph-node executor. Same cycle semantics as loom.interp.SM."""

from __future__ import annotations

from amaranth import Array, Cat, Elaboratable, Module, Mux, Signal

from loom.imem import ClockedImem
from loom.isa import (
    CLR_BIT,
    CSR_FIFO_SEL,
    CSR_SM0_CLKDIV_FRAC,
    CSR_SM0_CLKDIV_HI,
    CSR_SM0_CLKDIV_LO,
    CSR_SM0_SIDE,
    CSR_SM0_SLOT,
    CSR_SM0_WRAP_BOT,
    CSR_SM0_WRAP_TOP,
    CSR_SM1_CLKDIV_FRAC,
    CSR_SM1_CLKDIV_HI,
    CSR_SM1_CLKDIV_LO,
    CSR_SM1_SIDE,
    CSR_SM1_SLOT,
    CSR_SM1_WRAP_BOT,
    CSR_SM1_WRAP_TOP,
    CSR_WRITE_SLOT,
    FIFO_DEPTH,
    FIFO_PULL,
    IMEM_WORDS,
    JMP_ALWAYS,
    JMP_PIN,
    JMP_TX_EQ0,
    JMP_TX_NE,
    JMP_X_DEC,
    JMP_X_EQ0,
    JMP_Y_DEC,
    JMP_Y_EQ0,
    N_SLOTS,
    OP_FIFO,
    OP_IN,
    OP_JMP,
    OP_MOV,
    OP_OUT,
    OP_SET,
    OP_WAIT,
    REG_ISR,
    REG_OSR,
    REG_PINDIRS,
    REG_PINS,
    REG_X,
    REG_XOR_Y,
    REG_CRC_CLR,
    REG_CRC_FEED,
    REG_CRC_HI,
    REG_CRC_LO,
    REG_CRC_OUT,
    CRC15_POLY,
    REG_Y,
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
    def __init__(self, n_sm: int = 1, n_slots: int = 1, *, sram_macro: bool = False) -> None:
        if n_sm not in (1, 2):
            raise ValueError("n_sm must be 1 or 2")
        if n_slots not in (1, N_SLOTS):
            raise ValueError("n_slots must be 1 or 4")
        self.n_sm = n_sm
        self.n_slots = n_slots
        self.sram_macro = sram_macro and n_slots == N_SLOTS
        self.run = Signal()
        self.gpio_in = Signal(8)
        self.gpio_out = Signal(8)
        self.gpio_oe = Signal(8)
        self.imem_we = Signal()
        self.imem_waddr = Signal(5)
        self.imem_wdata = Signal(16)
        self.imem_slot = Signal(2)
        self.sm_sel = Signal(1)
        self.csr_we = Signal()
        self.csr_addr = Signal(5)
        self.csr_wdata = Signal(8)
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
        n_slots = self.n_slots

        pcs = [self.pc]
        xs = [Signal(8, name="x")]
        ys = [Signal(8, name="y")]
        osrs = [Signal(8, name="osr")]
        isrs = [Signal(8, name="isr")]
        delay_ctrs = [Signal(5, name="delay_ctr")]
        out_pins = [Signal(3, name="out_pin")]
        in_pins = [Signal(3, name="in_pin")]
        instrs = [Signal(16, name="instr")]
        sm_slots = [Signal(2, name="sm_slot", reset=0)]
        clkdiv_ints = [Signal(16, name="clkdiv_int", reset=1)]
        clkdiv_fracs = [Signal(8, name="clkdiv_frac")]
        div_downs = [Signal(16, name="div_down")]
        frac_accs = [Signal(8, name="frac_acc")]
        wrap_bots = [Signal(5, name="wrap_bot")]
        wrap_tops = [Signal(5, name="wrap_top", reset=31)]
        side_counts = [Signal(1, name="side_count")]
        side_bases = [Signal(3, name="side_base")]
        side_latcheds = [Signal(1, name="side_latched")]
        clk_ens = [Signal(name="clk_en")]
        crcs = [Signal(15, name="crc")]
        fetch_pcs = [Signal(5, name="fetch_pc")]

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
            instrs.append(Signal(16, name=f"instr{s}"))
            sm_slots.append(Signal(2, name=f"sm_slot{s}", reset=1 if n_slots > 1 else 0))
            clkdiv_ints.append(Signal(16, name=f"clkdiv_int{s}", reset=1))
            clkdiv_fracs.append(Signal(8, name=f"clkdiv_frac{s}"))
            div_downs.append(Signal(16, name=f"div_down{s}"))
            frac_accs.append(Signal(8, name=f"frac_acc{s}"))
            wrap_bots.append(Signal(5, name=f"wrap_bot{s}"))
            wrap_tops.append(Signal(5, name=f"wrap_top{s}", reset=31))
            side_counts.append(Signal(1, name=f"side_count{s}"))
            side_bases.append(Signal(3, name=f"side_base{s}"))
            side_latcheds.append(Signal(1, name=f"side_latched{s}"))
            clk_ens.append(Signal(name=f"clk_en{s}"))
            crcs.append(Signal(15, name=f"crc{s}"))
            fetch_pcs.append(Signal(5, name=f"fetch_pc{s}"))

        if n > 1:
            for i in range(8):
                d0 = oe_regs[0][i] & ~out_regs[0][i]
                d1 = oe_regs[1][i] & ~out_regs[1][i]
                h0 = oe_regs[0][i] & out_regs[0][i]
                h1 = oe_regs[1][i] & out_regs[1][i]
                oe_i = oe_regs[0][i] | oe_regs[1][i]
                driven = (h0 | h1) & ~(d0 | d1)
                m.d.comb += self.gpio_oe[i].eq(oe_i)
                m.d.comb += self.gpio_out[i].eq(Mux(oe_i, driven, out_regs[0][i] | out_regs[1][i]))

        if n_slots == 1:
            banks = [Array(Signal(16, name=f"iw{s}_{i}" if s else f"iw{i}") for i in range(IMEM_WORDS)) for s in range(n)]
            for s in range(n):
                m.d.comb += instrs[s].eq(banks[s][pcs[s]])
            with m.If(self.imem_we & ~self.run):
                if n == 1:
                    m.d.sync += banks[0][self.imem_waddr].eq(self.imem_wdata)
                else:
                    with m.If(self.imem_sel == 0):
                        m.d.sync += banks[0][self.imem_waddr].eq(self.imem_wdata)
                    with m.Else():
                        m.d.sync += banks[1][self.imem_waddr].eq(self.imem_wdata)
            imems_dbg = banks
        else:
            imem = ClockedImem(use_macro=self.sram_macro)
            m.submodules.imem = imem
            m.d.comb += [
                imem.w_en.eq(self.imem_we & ~self.run),
                imem.w_addr.eq(Cat(self.imem_waddr, self.imem_slot)),
                imem.w_data.eq(self.imem_wdata),
                imem.a_addr.eq(Cat(fetch_pcs[0], sm_slots[0])),
                instrs[0].eq(imem.a_data),
            ]
            if n > 1:
                m.d.comb += [
                    imem.b_addr.eq(Cat(fetch_pcs[1], sm_slots[1])),
                    instrs[1].eq(imem.b_data),
                ]
            else:
                m.d.comb += imem.b_addr.eq(0)
            imems_dbg = [imem]

        write_slot = Signal(2, name="write_slot")
        fifo_sel = Signal(1, name="fifo_sel")
        with m.If(self.csr_we & ~self.run):
            with m.Switch(self.csr_addr):
                with m.Case(CSR_WRITE_SLOT):
                    m.d.sync += write_slot.eq(self.csr_wdata[0:2])
                with m.Case(CSR_SM0_SLOT):
                    m.d.sync += sm_slots[0].eq(self.csr_wdata[0:2])
                with m.Case(CSR_SM0_CLKDIV_LO):
                    m.d.sync += clkdiv_ints[0][0:8].eq(self.csr_wdata)
                with m.Case(CSR_SM0_CLKDIV_HI):
                    m.d.sync += clkdiv_ints[0][8:16].eq(self.csr_wdata)
                with m.Case(CSR_SM0_CLKDIV_FRAC):
                    m.d.sync += clkdiv_fracs[0].eq(self.csr_wdata)
                with m.Case(CSR_SM0_WRAP_BOT):
                    m.d.sync += wrap_bots[0].eq(self.csr_wdata[0:5])
                with m.Case(CSR_SM0_WRAP_TOP):
                    m.d.sync += wrap_tops[0].eq(self.csr_wdata[0:5])
                with m.Case(CSR_SM0_SIDE):
                    m.d.sync += [
                        side_bases[0].eq(self.csr_wdata[0:3]),
                        side_counts[0].eq(self.csr_wdata[4]),
                    ]
                with m.Case(CSR_FIFO_SEL):
                    m.d.sync += fifo_sel.eq(self.csr_wdata[0])
                if n > 1:
                    with m.Case(CSR_SM1_SLOT):
                        m.d.sync += sm_slots[1].eq(self.csr_wdata[0:2])
                    with m.Case(CSR_SM1_CLKDIV_LO):
                        m.d.sync += clkdiv_ints[1][0:8].eq(self.csr_wdata)
                    with m.Case(CSR_SM1_CLKDIV_HI):
                        m.d.sync += clkdiv_ints[1][8:16].eq(self.csr_wdata)
                    with m.Case(CSR_SM1_CLKDIV_FRAC):
                        m.d.sync += clkdiv_fracs[1].eq(self.csr_wdata)
                    with m.Case(CSR_SM1_WRAP_BOT):
                        m.d.sync += wrap_bots[1].eq(self.csr_wdata[0:5])
                    with m.Case(CSR_SM1_WRAP_TOP):
                        m.d.sync += wrap_tops[1].eq(self.csr_wdata[0:5])
                    with m.Case(CSR_SM1_SIDE):
                        m.d.sync += [
                            side_bases[1].eq(self.csr_wdata[0:3]),
                            side_counts[1].eq(self.csr_wdata[4]),
                        ]

        tx_mems = [Array(Signal(8, name=f"tx{s}_{i}") for i in range(FIFO_DEPTH)) for s in range(n)]
        rx_mems = [Array(Signal(8, name=f"rx{s}_{i}") for i in range(FIFO_DEPTH)) for s in range(n)]
        tx_rs = [Signal(2, name=f"tx_r{s}" if s else "tx_r") for s in range(n)]
        tx_ws = [Signal(2, name=f"tx_w{s}" if s else "tx_w") for s in range(n)]
        tx_ns = [Signal(3, name=f"tx_n{s}" if s else "tx_n") for s in range(n)]
        rx_rs = [Signal(2, name=f"rx_r{s}" if s else "rx_r") for s in range(n)]
        rx_ws = [Signal(2, name=f"rx_w{s}" if s else "rx_w") for s in range(n)]
        rx_ns = [Signal(3, name=f"rx_n{s}" if s else "rx_n") for s in range(n)]
        do_pulls = [Signal(name=f"do_pull{s}") for s in range(n)]
        do_pushs = [Signal(name=f"do_push{s}") for s in range(n)]

        if n == 1:
            m.d.comb += [
                self.tx_full.eq(tx_ns[0] == FIFO_DEPTH),
                self.rx_empty.eq(rx_ns[0] == 0),
                self.rx_data.eq(rx_mems[0][rx_rs[0]]),
            ]
        else:
            m.d.comb += [
                self.tx_full.eq(Mux(fifo_sel, tx_ns[1] == FIFO_DEPTH, tx_ns[0] == FIFO_DEPTH)),
                self.rx_empty.eq(Mux(fifo_sel, rx_ns[1] == 0, rx_ns[0] == 0)),
                self.rx_data.eq(Mux(fifo_sel, rx_mems[1][rx_rs[1]], rx_mems[0][rx_rs[0]])),
            ]

        for s in range(n):
            host_tx_s = Signal(name=f"host_tx{s}")
            host_rx_s = Signal(name=f"host_rx{s}")
            sel = 1 if n == 1 else (fifo_sel == s)
            m.d.comb += [
                host_tx_s.eq(self.tx_we & sel & (tx_ns[s] != FIFO_DEPTH)),
                host_rx_s.eq(self.rx_re & sel & (rx_ns[s] != 0)),
            ]
            with m.If(host_tx_s):
                m.d.sync += [
                    tx_mems[s][tx_ws[s]].eq(self.tx_data),
                    tx_ws[s].eq(tx_ws[s] + 1),
                ]
            with m.If(host_tx_s & ~do_pulls[s]):
                m.d.sync += tx_ns[s].eq(tx_ns[s] + 1)
            with m.Elif(~host_tx_s & do_pulls[s]):
                m.d.sync += tx_ns[s].eq(tx_ns[s] - 1)
            with m.If(do_pulls[s]):
                m.d.sync += tx_rs[s].eq(tx_rs[s] + 1)
            with m.If(host_rx_s):
                m.d.sync += rx_rs[s].eq(rx_rs[s] + 1)
            with m.If(host_rx_s & ~do_pushs[s]):
                m.d.sync += rx_ns[s].eq(rx_ns[s] - 1)
            with m.Elif(~host_rx_s & do_pushs[s]):
                m.d.sync += rx_ns[s].eq(rx_ns[s] + 1)
            with m.If(do_pushs[s]):
                m.d.sync += rx_ws[s].eq(rx_ws[s] + 1)

        # Pad view: driven pins pulldown-win; undriven bits follow gpio_in.
        pad = Signal(8, name="pad")
        if n == 1:
            for i in range(8):
                m.d.comb += pad[i].eq(Mux(oe_regs[0][i], out_regs[0][i], self.gpio_in[i]))
        else:
            for i in range(8):
                d0 = oe_regs[0][i] & ~out_regs[0][i]
                d1 = oe_regs[1][i] & ~out_regs[1][i]
                h0 = oe_regs[0][i] & out_regs[0][i]
                h1 = oe_regs[1][i] & out_regs[1][i]
                oe_i = oe_regs[0][i] | oe_regs[1][i]
                driven = (h0 | h1) & ~(d0 | d1)
                m.d.comb += pad[i].eq(Mux(oe_i, driven, self.gpio_in[i]))
        eff = pad

        self.dbg = dict(
            x=xs, y=ys, osr=osrs, isr=isrs, delay_ctr=delay_ctrs, out_pin=out_pins,
            in_pin=in_pins, imem=imems_dbg, instr=instrs, tx_mem=tx_mems[0], rx_mem=rx_mems[0],
            tx_r=tx_rs[0], tx_w=tx_ws[0], tx_n=tx_ns[0], rx_r=rx_rs[0], rx_w=rx_ws[0], rx_n=rx_ns[0],
            do_pull=do_pulls[0], do_push=do_pushs[0], eff=eff, pcs=pcs,
            out_regs=out_regs, oe_regs=oe_regs, clk_en=clk_ens,
            wrap_bot=wrap_bots, wrap_top=wrap_tops,
            clkdiv_int=clkdiv_ints, clkdiv_frac=clkdiv_fracs, div_down=div_downs,
            frac_acc=frac_accs, side_count=side_counts, side_base=side_bases,
            side_latched=side_latcheds, crc=crcs, fetch_pc=fetch_pcs, sm_slot=sm_slots,
            tx_n_all=tx_ns, rx_n_all=rx_ns, write_slot=write_slot, fifo_sel=fifo_sel,
        )

        for s in range(n):
            # clkdiv_int=0 is a 65536-cycle period (reload 0xFFFF), matching interp.
            with m.If(self.run):
                with m.If(div_downs[s] != 0):
                    m.d.sync += div_downs[s].eq(div_downs[s] - 1)
                    m.d.comb += clk_ens[s].eq(0)
                with m.Else():
                    m.d.comb += clk_ens[s].eq(1)
                    with m.If(clkdiv_ints[s] == 0):
                        m.d.sync += div_downs[s].eq(0xFFFF)
                    with m.Else():
                        frac_sum = frac_accs[s] + clkdiv_fracs[s]
                        extra = frac_sum[8]
                        m.d.sync += frac_accs[s].eq(frac_sum[0:8])
                        m.d.sync += div_downs[s].eq(clkdiv_ints[s] + extra - 1)
            with m.Else():
                m.d.comb += clk_ens[s].eq(0)

            with m.If(self.run & clk_ens[s]):
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
                    tx_n=tx_ns[s],
                    rx_n=rx_ns[s],
                    tx_mem=tx_mems[s],
                    rx_mem=rx_mems[s],
                    tx_r=tx_rs[s],
                    rx_w=rx_ws[s],
                    wrap_bot=wrap_bots[s],
                    wrap_top=wrap_tops[s],
                    side_count=side_counts[s],
                    side_base=side_bases[s],
                    side_latched=side_latcheds[s],
                    crc=crcs[s],
                    fetch_pc=fetch_pcs[s],
                    clk_en=clk_ens[s],
                )
            with m.Else():
                m.d.comb += fetch_pcs[s].eq(pcs[s])
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
        wrap_bot,
        wrap_top,
        side_count,
        side_base,
        side_latched,
        crc,
        fetch_pc,
        clk_en,
    ) -> None:
        op = instr[13:16]
        delay_field = instr[8:13]
        field = instr[5:8]
        payload = instr[0:5]
        delay = Mux(side_count, delay_field[0:4], delay_field)
        side_now = Mux(side_count, delay_field[4], 0)
        stall = Signal(name=f"stall{s}")
        next_pc = Signal(5, name=f"next_pc{s}")
        taken = Signal(name=f"taken{s}")
        pin_we = Signal(name=f"pin_we{s}")
        pin_wd = Signal(8, name=f"pin_wd{s}")
        oe_we = Signal(name=f"oe_we{s}")
        oe_wd = Signal(8, name=f"oe_wd{s}")
        ss_mask = Signal(8, name=f"ss_mask{s}")
        m.d.comb += ss_mask.eq(Mux(side_count, (1 << side_base)[0:8], 0))

        def commit_out(bit):
            core = Mux(pin_we, pin_wd, out_reg)
            return (core & ~ss_mask) | Mux(bit, ss_mask, 0)

        with m.If(delay_ctr != 0):
            m.d.comb += fetch_pc.eq(pc)
            m.d.sync += delay_ctr.eq(delay_ctr - 1)
            m.d.sync += out_reg.eq(commit_out(side_latched))
        with m.Else():
            m.d.comb += stall.eq(0)
            m.d.comb += next_pc.eq(pc + 1)
            m.d.comb += taken.eq(0)
            with m.Switch(op):
                with m.Case(OP_JMP):
                    with m.Switch(field):
                        with m.Case(JMP_ALWAYS):
                            m.d.comb += next_pc.eq(payload)
                            m.d.comb += taken.eq(1)
                        with m.Case(JMP_X_EQ0):
                            with m.If(x == 0):
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Case(JMP_Y_EQ0):
                            with m.If(y == 0):
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Case(JMP_X_DEC):
                            with m.If(x != 0):
                                m.d.sync += x.eq(x - 1)
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Case(JMP_Y_DEC):
                            with m.If(y != 0):
                                m.d.sync += y.eq(y - 1)
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Case(JMP_PIN):
                            with m.If(eff.bit_select(in_pin, 1)):
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Case(JMP_TX_NE):
                            with m.If(tx_n != 0):
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Case(JMP_TX_EQ0):
                            with m.If(tx_n == 0):
                                m.d.comb += next_pc.eq(payload)
                                m.d.comb += taken.eq(1)
                        with m.Default():
                            pass
                with m.Case(OP_WAIT):
                    pin = payload[0:4]
                    pol = payload[4]
                    with m.If(eff.bit_select(pin, 1) != pol):
                        m.d.comb += stall.eq(1)
                with m.Case(OP_OUT):
                    bit = Mux(field == SHIFT_LSB, osr[0], osr[7])
                    mask = Signal(8, name=f"mask{s}")
                    m.d.comb += mask.eq(1 << out_pin)
                    m.d.comb += pin_we.eq(1)
                    m.d.comb += pin_wd.eq(Mux(bit, out_reg | mask, out_reg & ~mask))
                    m.d.comb += oe_we.eq(1)
                    m.d.comb += oe_wd.eq(oe_reg | mask)
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
                with m.Case(OP_MOV):
                    srcv = Signal(8, name=f"movsrc{s}")
                    dest_cur = Signal(8, name=f"movcur{s}")
                    with m.Switch(field):
                        with m.Case(REG_X):
                            m.d.comb += dest_cur.eq(x)
                        with m.Case(REG_Y):
                            m.d.comb += dest_cur.eq(y)
                        with m.Case(REG_OSR):
                            m.d.comb += dest_cur.eq(osr)
                        with m.Case(REG_ISR):
                            m.d.comb += dest_cur.eq(isr)
                        with m.Case(REG_PINS):
                            m.d.comb += dest_cur.eq(out_reg)
                        with m.Default():
                            m.d.comb += dest_cur.eq(0)
                    with m.Switch(payload):
                        with m.Case(REG_X):
                            m.d.comb += srcv.eq(x)
                        with m.Case(REG_Y):
                            m.d.comb += srcv.eq(y)
                        with m.Case(REG_OSR):
                            m.d.comb += srcv.eq(osr)
                        with m.Case(REG_ISR):
                            m.d.comb += srcv.eq(isr)
                        with m.Case(REG_PINS):
                            m.d.comb += srcv.eq(eff)
                        with m.Case(REG_XOR_Y):
                            m.d.comb += srcv.eq(dest_cur ^ y)
                        with m.Case(REG_CRC_LO):
                            m.d.comb += srcv.eq(crc[0:8])
                        with m.Case(REG_CRC_HI):
                            m.d.comb += srcv.eq(crc[8:15])
                        with m.Case(REG_CRC_OUT):
                            m.d.comb += srcv.eq(crc[14])
                        with m.Default():
                            m.d.comb += srcv.eq(0)
                    with m.If(payload == REG_CRC_FEED):
                        msb = crc[14]
                        shifted = Cat(0, crc[0:14])
                        with m.If(msb ^ osr[0]):
                            m.d.sync += crc.eq(shifted ^ CRC15_POLY)
                        with m.Else():
                            m.d.sync += crc.eq(shifted)
                    with m.Elif(payload == REG_CRC_CLR):
                        m.d.sync += crc.eq(0)
                    with m.Elif(payload == REG_CRC_OUT):
                        m.d.sync += crc.eq(Cat(0, crc[0:14]))
                        with m.Switch(field):
                            with m.Case(REG_X):
                                m.d.sync += x.eq(srcv)
                            with m.Case(REG_Y):
                                m.d.sync += y.eq(srcv)
                            with m.Case(REG_OSR):
                                m.d.sync += osr.eq(srcv)
                            with m.Case(REG_ISR):
                                m.d.sync += isr.eq(srcv)
                            with m.Case(REG_PINS):
                                m.d.comb += pin_we.eq(1)
                                m.d.comb += pin_wd.eq(srcv)
                            with m.Case(REG_PINDIRS):
                                m.d.comb += oe_we.eq(1)
                                m.d.comb += oe_wd.eq(srcv)
                    with m.Elif((payload != REG_CRC_FEED) & (payload != REG_CRC_CLR)):
                        with m.Switch(field):
                            with m.Case(REG_X):
                                m.d.sync += x.eq(srcv)
                            with m.Case(REG_Y):
                                m.d.sync += y.eq(srcv)
                            with m.Case(REG_OSR):
                                m.d.sync += osr.eq(srcv)
                            with m.Case(REG_ISR):
                                m.d.sync += isr.eq(srcv)
                            with m.Case(REG_PINS):
                                m.d.comb += pin_we.eq(1)
                                m.d.comb += pin_wd.eq(srcv)
                            with m.Case(REG_PINDIRS):
                                m.d.comb += oe_we.eq(1)
                                m.d.comb += oe_wd.eq(srcv)
                with m.Case(OP_SET):
                    with m.Switch(field):
                        with m.Case(SET_PINS):
                            m.d.comb += pin_we.eq(1)
                            m.d.comb += pin_wd.eq(Cat(payload, out_reg[5:8]))
                        with m.Case(SET_PINDIRS):
                            m.d.comb += oe_we.eq(1)
                            m.d.comb += oe_wd.eq(Cat(payload, oe_reg[5:8]))
                        with m.Case(SET_X):
                            m.d.sync += x.eq(payload)
                        with m.Case(SET_Y):
                            m.d.sync += y.eq(payload)
                        with m.Case(SET_BIT):
                            bmask = (1 << payload[0:3])[0:8]
                            m.d.comb += pin_we.eq(1)
                            m.d.comb += pin_wd.eq(out_reg | bmask)
                            m.d.comb += oe_we.eq(1)
                            m.d.comb += oe_wd.eq(oe_reg | bmask)
                        with m.Case(CLR_BIT):
                            m.d.comb += pin_we.eq(1)
                            m.d.comb += pin_wd.eq(out_reg & ~((1 << payload[0:3])[0:8]))
                        with m.Case(SET_OUTPIN):
                            m.d.sync += out_pin.eq(payload[0:3])
                        with m.Case(SET_INPIN):
                            m.d.sync += in_pin.eq(payload[0:3])
                        with m.Default():
                            pass
                with m.Default():
                    pass
            m.d.sync += out_reg.eq(commit_out(side_now))
            with m.If(oe_we):
                m.d.sync += oe_reg.eq(oe_wd)
            m.d.sync += side_latched.eq(side_now)
            with m.If(~stall):
                with m.If(taken):
                    m.d.sync += pc.eq(next_pc)
                with m.Elif(pc == wrap_top):
                    m.d.sync += pc.eq(wrap_bot)
                with m.Else():
                    m.d.sync += pc.eq(next_pc)
                m.d.sync += delay_ctr.eq(delay)
            adv_pc = Mux(taken, next_pc, Mux(pc == wrap_top, wrap_bot, (pc + 1)[0:5]))
            m.d.comb += fetch_pc.eq(Mux(stall, pc, adv_pc))
