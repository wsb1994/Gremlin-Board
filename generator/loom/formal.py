"""Formal properties of the graph engine, proven by k-induction.

Families, each checked for *every* reachable state (not a test vector):

  Structural invariants (1-SM combo IMEM)
    FIFO occupancy bounds, full/empty flags, pointer/occupancy consistency,
    writes dropped when full, halt freezes the SM, no imem load while running.

  ISA one-step semantics (1-SM combo IMEM)
    For each opcode: given the previous cycle's state and the instruction at
    pc, the current state is exactly what the ISA says (pc, delay counter,
    x, y, osr, isr, pins, FIFO side effects, stalls, CRC MOV 7–11).
    Host CSR writes (csr_we free): halt+csr_we commits csr_wdata to the
    addressed register; run or ~csr_we holds. clkdiv 0 still reloads 0xFFFF.

  Clocked IMEM / 2-SM (loom_chip path)
    After 1-cycle history, each SM's instr equals mem[{fetch_pc, slot}] from
    last cycle and pc follows last cycle's fetch_pc (next-pc addressing that
    matches combo ISA timing after a 1-cycle preload).

Solver: the Yosys `sat` engine (MiniSat, built into Yosys). No SMT solver
needed. amaranth-yosys (WASM) omits `sat`, so a native `yosys` is used when
on PATH, else the LibreLane container the GDS flow already uses.

    python -m loom.formal            # prove, exit 1 on failure
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal
from amaranth.back import rtlil
from amaranth.hdl import Assert

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
    N_SM_CHIP,
    OP_FIFO,
    OP_IN,
    OP_JMP,
    OP_MOV,
    OP_NOP,
    OP_OUT,
    OP_SET,
    OP_WAIT,
    REG_CRC_CLR,
    REG_CRC_FEED,
    REG_CRC_HI,
    REG_CRC_LO,
    REG_CRC_OUT,
    SET_BIT,
    SET_INPIN,
    SET_OUTPIN,
    SET_PINDIRS,
    SET_PINS,
    SET_X,
    SET_Y,
    SHIFT_LSB,
)
from loom.imem import ClockedImem
from loom.rtl import GraphEngine

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "test" / "gen"
IMAGE = "ghcr.io/librelane/librelane:3.1.0.dev3"


class Harness(Elaboratable):
    """GraphEngine plus one cycle of history and the assertions."""

    def __init__(self) -> None:
        self.dut = GraphEngine()

    def elaborate(self, platform) -> Module:
        m = Module()
        dut = self.dut
        m.submodules.dut = dut.elaborate(platform)  # populates dut.dbg
        m.d.comb += [
            dut.imem_slot.eq(0),
            dut.sm_sel.eq(0),
        ]
        d = dut.dbg
        x, y, osr, isr = d["x"][0], d["y"][0], d["osr"][0], d["isr"][0]
        delay_ctr, out_pin, in_pin = d["delay_ctr"][0], d["out_pin"][0], d["in_pin"][0]
        imem, instr = d["imem"][0], d["instr"][0]
        tx_mem, rx_mem = d["tx_mem"], d["rx_mem"]
        tx_r, tx_w, tx_n = d["tx_r"], d["tx_w"], d["tx_n"]
        rx_r, rx_w, rx_n = d["rx_r"], d["rx_w"], d["rx_n"]
        eff = d["eff"]
        clk_en = d["clk_en"][0]
        wrap_bot, wrap_top = d["wrap_bot"][0], d["wrap_top"][0]
        crc = d["crc"][0]
        clkdiv_int, clkdiv_frac = d["clkdiv_int"][0], d["clkdiv_frac"][0]
        div_down, frac_acc = d["div_down"][0], d["frac_acc"][0]
        side_count, side_base, side_latched = d["side_count"][0], d["side_base"][0], d["side_latched"][0]
        sm_slot, write_slot, fifo_sel = d["sm_slot"][0], d["write_slot"], d["fifo_sel"]
        pc, out, oe = dut.pc, dut.gpio_out, dut.gpio_oe

        # ---- one cycle of history -------------------------------------
        valid = Signal()
        m.d.sync += valid.eq(1)

        def past(sig, name):
            p = Signal.like(sig, name=f"p_{name}")
            m.d.sync += p.eq(sig)
            return p

        P = dict(
            run=past(dut.run, "run"), pc=past(pc, "pc"), x=past(x, "x"), y=past(y, "y"),
            osr=past(osr, "osr"), isr=past(isr, "isr"), out=past(out, "out"), oe=past(oe, "oe"),
            delay_ctr=past(delay_ctr, "dc"), out_pin=past(out_pin, "op"), in_pin=past(in_pin, "ip"),
            instr=past(instr, "instr"), eff=past(eff, "eff"), clk_en=past(clk_en, "clken"),
            wrap_bot=past(wrap_bot, "wbot"), wrap_top=past(wrap_top, "wtop"),
            tx_r=past(tx_r, "txr"), tx_w=past(tx_w, "txw"), tx_n=past(tx_n, "txn"),
            rx_r=past(rx_r, "rxr"), rx_w=past(rx_w, "rxw"), rx_n=past(rx_n, "rxn"),
            tx_we=past(dut.tx_we, "txwe"), tx_data=past(dut.tx_data, "txd"),
            rx_re=past(dut.rx_re, "rxre"), imem_we=past(dut.imem_we, "imwe"),
            crc=past(crc, "crc"),
            clkdiv_int=past(clkdiv_int, "cdiv"), clkdiv_frac=past(clkdiv_frac, "cfrac"),
            div_down=past(div_down, "ddn"), frac_acc=past(frac_acc, "facc"),
            side_count=past(side_count, "scnt"), side_base=past(side_base, "sbase"),
            side_latched=past(side_latched, "slat"),
            csr_we=past(dut.csr_we, "csrwe"), csr_addr=past(dut.csr_addr, "csraddr"),
            csr_wdata=past(dut.csr_wdata, "csrw"),
            sm_slot=past(sm_slot, "slot"), write_slot=past(write_slot, "wslot"),
            fifo_sel=past(fifo_sel, "fsel"),
        )
        p_tx = [past(tx_mem[i], f"txm{i}") for i in range(FIFO_DEPTH)]
        p_rx = [past(rx_mem[i], f"rxm{i}") for i in range(FIFO_DEPTH)]
        p_imem = [past(imem[i], f"iw{i}") for i in range(IMEM_WORDS)]

        def sel(mem, idx):
            v = mem[0]
            for i in range(1, len(mem)):
                v = Mux(idx == i, mem[i], v)
            return v

        asserts: list[tuple[str, object]] = []

        def A(name, cond):
            asserts.append((name, cond))

        # ---- structural invariants (hold in every cycle) -------------
        A("tx_n_bound", tx_n <= FIFO_DEPTH)
        A("rx_n_bound", rx_n <= FIFO_DEPTH)
        A("tx_full_flag", dut.tx_full == (tx_n == FIFO_DEPTH))
        A("rx_empty_flag", dut.rx_empty == (rx_n == 0))
        A("tx_ptr_consistent", ((tx_w - tx_r) & 3) == (tx_n & 3))
        A("rx_ptr_consistent", ((rx_w - rx_r) & 3) == (rx_n & 3))
        A("rx_data_is_head", dut.rx_data == sel(rx_mem, rx_r))
        # csr_we is a free input: writes only while halted (see history asserts).
        A("clk_en_is_run_and_zero_div", clk_en == (dut.run & (div_down == 0)))

        # ---- history-based properties --------------------------------
        p = P
        p_full = p["tx_n"] == FIFO_DEPTH
        p_empty = p["rx_n"] == 0
        host_tx = p["tx_we"] & ~p_full          # accepted host write last cycle
        host_rx = p["rx_re"] & ~p_empty         # accepted host read last cycle

        H: list[tuple[str, object]] = []

        def HA(name, cond):
            H.append((name, cond))

        # host FIFO side
        HA("tx_write_when_full_dropped", ~(p["tx_we"] & p_full) | (tx_w == p["tx_w"]))
        HA("tx_write_stored", ~host_tx | ((sel(tx_mem, p["tx_w"]) == p["tx_data"]) & (tx_w == (p["tx_w"] + 1)[0:2])))
        HA("tx_no_write_keeps_wptr", host_tx | (tx_w == p["tx_w"]))
        HA("rx_read_when_empty_ignored", ~(p["rx_re"] & p_empty) | (rx_r == p["rx_r"]))
        HA("rx_read_advances", ~host_rx | (rx_r == (p["rx_r"] + 1)[0:2]))
        HA("rx_no_read_keeps_rptr", host_rx | (rx_r == p["rx_r"]))

        # halt freezes the state machine; run blocks imem loads
        frozen = (
            (pc == p["pc"]) & (x == p["x"]) & (y == p["y"]) & (osr == p["osr"]) & (isr == p["isr"])
            & (out == p["out"]) & (oe == p["oe"]) & (delay_ctr == p["delay_ctr"])
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & (crc == p["crc"])
        )
        HA("halt_freezes_sm", p["run"] | frozen)
        HA("halt_no_fifo_pull", p["run"] | (tx_r == p["tx_r"]))
        HA("halt_no_fifo_push", p["run"] | (rx_w == p["rx_w"]))
        imem_same = Cat(*[imem[i] == p_imem[i] for i in range(IMEM_WORDS)]).all()
        HA("run_blocks_imem_load", ~p["run"] | imem_same)
        # FIFO occupancy bookkeeping whatever the SM did
        pulled = tx_r != p["tx_r"]
        pushed = rx_w != p["rx_w"]
        HA("tx_n_bookkeeping", tx_n == p["tx_n"] + host_tx - pulled)
        HA("rx_n_bookkeeping", rx_n == p["rx_n"] + pushed - host_rx)

        # Host CSR writes (rtl.py: csr_we & ~run). ISA step properties still use
        # past wrap/sideset/clkdiv, which hold while running.
        host_csr = p["csr_we"] & ~p["run"]
        a, w = p["csr_addr"], p["csr_wdata"]

        def csr_wrote(addr):
            return host_csr & (a == addr)

        csr_same = (
            (write_slot == p["write_slot"]) & (sm_slot == p["sm_slot"])
            & (clkdiv_int == p["clkdiv_int"]) & (clkdiv_frac == p["clkdiv_frac"])
            & (wrap_bot == p["wrap_bot"]) & (wrap_top == p["wrap_top"])
            & (side_base == p["side_base"]) & (side_count == p["side_count"])
            & (fifo_sel == p["fifo_sel"])
        )
        HA("csr_hold_run_or_nwe", host_csr | csr_same)
        HA("csr_write_slot", write_slot == Mux(csr_wrote(CSR_WRITE_SLOT), w[0:2], p["write_slot"]))
        HA("csr_sm0_slot", sm_slot == Mux(csr_wrote(CSR_SM0_SLOT), w[0:2], p["sm_slot"]))
        HA("csr_clkdiv_lo", clkdiv_int[0:8] == Mux(csr_wrote(CSR_SM0_CLKDIV_LO), w, p["clkdiv_int"][0:8]))
        HA("csr_clkdiv_hi", clkdiv_int[8:16] == Mux(csr_wrote(CSR_SM0_CLKDIV_HI), w, p["clkdiv_int"][8:16]))
        HA("csr_clkdiv_frac", clkdiv_frac == Mux(csr_wrote(CSR_SM0_CLKDIV_FRAC), w, p["clkdiv_frac"]))
        HA("csr_wrap_bot", wrap_bot == Mux(csr_wrote(CSR_SM0_WRAP_BOT), w[0:5], p["wrap_bot"]))
        HA("csr_wrap_top", wrap_top == Mux(csr_wrote(CSR_SM0_WRAP_TOP), w[0:5], p["wrap_top"]))
        HA("csr_side_base", side_base == Mux(csr_wrote(CSR_SM0_SIDE), w[0:3], p["side_base"]))
        HA("csr_side_count", side_count == Mux(csr_wrote(CSR_SM0_SIDE), w[4], p["side_count"]))
        HA("csr_fifo_sel", fifo_sel == Mux(csr_wrote(CSR_FIFO_SEL), w[0], p["fifo_sel"]))
        HA("div_down_dec", ~(p["run"] & (p["div_down"] != 0)) | (div_down == (p["div_down"] - 1)[0:16]))
        HA("div_frozen_halt", p["run"] | (div_down == p["div_down"]))
        HA("div_reload_max", ~(p["run"] & (p["div_down"] == 0) & (p["clkdiv_int"] == 0)) | (div_down == 0xFFFF))
        p_frac_sum = p["frac_acc"] + p["clkdiv_frac"]
        p_extra = p_frac_sum[8]
        HA("div_reload_int", ~(p["run"] & (p["div_down"] == 0) & (p["clkdiv_int"] != 0)) |
           (div_down == (p["clkdiv_int"] + p_extra - 1)[0:16]))
        HA("frac_reload", ~(p["run"] & (p["div_down"] == 0) & (p["clkdiv_int"] != 0)) |
           (frac_acc == p_frac_sum[0:8]))
        HA("frac_frozen_maxdiv", ~(p["run"] & (p["div_down"] == 0) & (p["clkdiv_int"] == 0)) |
           (frac_acc == p["frac_acc"]))

        # ---- ISA one-step semantics ----------------------------------
        pi = p["instr"]
        op, delay_field, field, payload = pi[13:16], pi[8:13], pi[5:8], pi[0:5]
        delay = Mux(p["side_count"], delay_field[0:4], delay_field)
        side_now = Mux(p["side_count"], delay_field[4], 0)
        ss_mask = Mux(p["side_count"], (1 << p["side_base"])[0:8], 0)

        def overlay(core, bit):
            return (core & ~ss_mask) | Mux(bit, ss_mask, 0)

        step = p["run"] & p["clk_en"] & (p["delay_ctr"] == 0)      # an instruction executed
        pc1 = (p["pc"] + 1)[0:5]
        wrap_pc = Mux(p["pc"] == p["wrap_top"], p["wrap_bot"], pc1)
        adv = (pc == wrap_pc) & (delay_ctr == delay)     # +1, or wrap
        jmp_to = (pc == payload) & (delay_ctr == delay)
        stalled = (pc == p["pc"]) & (delay_ctr == 0)
        same_regs = (x == p["x"]) & (y == p["y"])
        same_shift = (osr == p["osr"]) & (isr == p["isr"])
        same_pins = (out == overlay(p["out"], side_now)) & (oe == p["oe"]) & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"])
        pins_delay = (out == overlay(p["out"], p["side_latched"])) & (oe == p["oe"]) & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"])
        no_pull = tx_r == p["tx_r"]
        no_push = rx_w == p["rx_w"]
        untouched = same_regs & same_shift & same_pins & no_pull & no_push
        untouched_delay = same_regs & same_shift & pins_delay & no_pull & no_push

        # delay counter ticking (sideset uses the latched bit, not the next instr)
        HA("delay_counts_down", ~(p["run"] & p["clk_en"] & (p["delay_ctr"] != 0)) |
           ((delay_ctr == (p["delay_ctr"] - 1)[0:5]) & (pc == p["pc"]) & untouched_delay))
        HA("clk_en_off_freezes_sm", ~(p["run"] & ~p["clk_en"]) | frozen)

        def when(cond):
            return ~(step & cond)

        # NOP
        HA("nop", when(op == OP_NOP) | (adv & untouched))
        # JMP
        pin_bit = (p["eff"] >> p["in_pin"])[0]
        HA("jmp_always", when((op == OP_JMP) & (field == JMP_ALWAYS)) | (jmp_to & untouched))
        HA("jmp_x_eq0", when((op == OP_JMP) & (field == JMP_X_EQ0)) |
           (Mux(p["x"] == 0, jmp_to, adv) & untouched))
        HA("jmp_y_eq0", when((op == OP_JMP) & (field == JMP_Y_EQ0)) |
           (Mux(p["y"] == 0, jmp_to, adv) & untouched))
        HA("jmp_x_dec", when((op == OP_JMP) & (field == JMP_X_DEC)) |
           Mux(p["x"] != 0, jmp_to & (x == (p["x"] - 1)[0:8]) & (y == p["y"]), adv & same_regs)
           & same_shift & same_pins & no_pull & no_push)
        HA("jmp_y_dec", when((op == OP_JMP) & (field == JMP_Y_DEC)) |
           Mux(p["y"] != 0, jmp_to & (y == (p["y"] - 1)[0:8]) & (x == p["x"]), adv & same_regs)
           & same_shift & same_pins & no_pull & no_push)
        HA("jmp_pin", when((op == OP_JMP) & (field == JMP_PIN)) | (Mux(pin_bit, jmp_to, adv) & untouched))
        HA("jmp_tx_ne", when((op == OP_JMP) & (field == JMP_TX_NE)) |
           (Mux(p["tx_n"] != 0, jmp_to, adv) & untouched))
        HA("jmp_tx_eq0", when((op == OP_JMP) & (field == JMP_TX_EQ0)) |
           (Mux(p["tx_n"] == 0, jmp_to, adv) & untouched))
        # WAIT
        wpin, wpol = payload[0:4], payload[4]
        wbit = (p["eff"] >> wpin)[0]
        HA("wait", when(op == OP_WAIT) | (Mux(wbit == wpol, adv, stalled) & untouched))
        # IN
        s = pin_bit
        isr_lsb = Cat(p["isr"][1:8], s)
        isr_msb = Cat(s, p["isr"][0:7])
        HA("in", when(op == OP_IN) |
           (adv & (isr == Mux(field == SHIFT_LSB, isr_lsb, isr_msb)) & (osr == p["osr"])
            & same_regs & same_pins & no_pull & no_push))
        # OUT
        obit = Mux(field == SHIFT_LSB, p["osr"][0], p["osr"][7])
        mask = (1 << p["out_pin"])[0:8]
        out_exp = Mux(obit, p["out"] | mask, p["out"] & ~mask)
        osr_exp = Mux(field == SHIFT_LSB, p["osr"] >> 1, (p["osr"] << 1)[0:8])
        HA("out", when(op == OP_OUT) |
           (adv & (out == overlay(out_exp, side_now)) & (osr == osr_exp) & (isr == p["isr"]) & (oe == (p["oe"] | mask))
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & same_regs & no_pull & no_push))
        # FIFO
        pull = (op == OP_FIFO) & (field == FIFO_PULL)
        push = (op == OP_FIFO) & (field != FIFO_PULL)
        HA("fifo_pull_stall", when(pull & (p["tx_n"] == 0)) | (stalled & untouched))
        HA("fifo_pull", when(pull & (p["tx_n"] != 0)) |
           (adv & (osr == sel(p_tx, p["tx_r"])) & (tx_r == (p["tx_r"] + 1)[0:2]) & (isr == p["isr"])
            & same_regs & same_pins & no_push))
        HA("fifo_push_stall", when(push & (p["rx_n"] == FIFO_DEPTH)) | (stalled & untouched))
        HA("fifo_push", when(push & (p["rx_n"] != FIFO_DEPTH)) |
           (adv & (sel(rx_mem, p["rx_w"]) == p["isr"]) & (rx_w == (p["rx_w"] + 1)[0:2])
            & same_regs & same_shift & same_pins & no_pull))
        # SET
        def set_is(f):
            return when((op == OP_SET) & (field == f))
        HA("set_pins", set_is(SET_PINS) |
           (adv & (out == overlay(Cat(payload, p["out"][5:8]), side_now)) & (oe == p["oe"])
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("set_pindirs", set_is(SET_PINDIRS) |
           (adv & (oe[0:5] == payload) & (oe[5:8] == p["oe"][5:8]) & (out == overlay(p["out"], side_now))
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("set_x", set_is(SET_X) | (adv & (x == payload) & (y == p["y"]) & same_shift & same_pins & no_pull & no_push))
        HA("set_y", set_is(SET_Y) | (adv & (y == payload) & (x == p["x"]) & same_shift & same_pins & no_pull & no_push))
        bmask = (1 << payload[0:3])[0:8]
        HA("set_bit", set_is(SET_BIT) |
           (adv & (out == overlay(p["out"] | bmask, side_now)) & (oe == (p["oe"] | bmask)) & (out_pin == p["out_pin"])
            & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("clr_bit", set_is(CLR_BIT) |
           (adv & (out == overlay(p["out"] & ~bmask, side_now)) & (oe == p["oe"]) & (out_pin == p["out_pin"])
            & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("set_outpin", set_is(SET_OUTPIN) |
           (adv & (out_pin == payload[0:3]) & (in_pin == p["in_pin"]) & (out == overlay(p["out"], side_now)) & (oe == p["oe"])
            & same_regs & same_shift & no_pull & no_push))
        HA("set_inpin", set_is(SET_INPIN) |
           (adv & (in_pin == payload[0:3]) & (out_pin == p["out_pin"]) & (out == overlay(p["out"], side_now)) & (oe == p["oe"])
            & same_regs & same_shift & no_pull & no_push))
        # MOV: dest=field, src=payload. payload 6 = dest ^ Y. Pins dest updates out.
        dest_cur = Mux(field == 0, p["x"],
                    Mux(field == 1, p["y"],
                    Mux(field == 2, p["osr"],
                    Mux(field == 3, p["isr"],
                    Mux(field == 4, p["out"], 0)))))
        mov_src = Mux(payload == 6, dest_cur ^ p["y"],
                   Mux(payload == 0, p["x"],
                   Mux(payload == 1, p["y"],
                   Mux(payload == 2, p["osr"],
                   Mux(payload == 3, p["isr"],
                   Mux(payload == 4, p["eff"], 0))))))
        mov = op == OP_MOV
        ordinary = payload <= 6
        HA("mov_x", when(mov & (field == 0) & ordinary) |
           (adv & (x == mov_src) & (y == p["y"]) & same_shift & same_pins & no_pull & no_push))
        HA("mov_y", when(mov & (field == 1) & ordinary) |
           (adv & (y == mov_src) & (x == p["x"]) & same_shift & same_pins & no_pull & no_push))
        HA("mov_osr", when(mov & (field == 2) & ordinary) |
           (adv & (osr == mov_src) & (isr == p["isr"]) & same_regs & same_pins & no_pull & no_push))
        HA("mov_isr", when(mov & (field == 3) & ordinary) |
           (adv & (isr == mov_src) & (osr == p["osr"]) & same_regs & same_pins & no_pull & no_push))
        HA("mov_pins", when(mov & (field == 4) & ordinary) |
           (adv & (out == overlay(mov_src, side_now)) & (oe == p["oe"]) & same_regs & same_shift
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & no_pull & no_push))
        HA("mov_pindirs", when(mov & (field == 5) & ordinary) |
           (adv & (oe == mov_src) & (out == overlay(p["out"], side_now)) & same_regs & same_shift
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & no_pull & no_push))
        HA("mov_null_dest", when(mov & (field > 5) & ordinary) |
           (adv & untouched))
        # CRC-15 (poly 0x4599). payload 7=feed, 10=clr, 8/9/11 read.
        pcrc = p["crc"]
        feed_msb = pcrc[14] ^ p["osr"][0]
        feed_crc = Mux(feed_msb, Cat(0, pcrc[0:14]) ^ 0x4599, Cat(0, pcrc[0:14]))
        HA("mov_crc_feed", when(mov & (payload == REG_CRC_FEED)) |
           (adv & (crc == feed_crc) & untouched))
        HA("mov_crc_clr", when(mov & (payload == REG_CRC_CLR)) |
           (adv & (crc == 0) & (x == p["x"]) & (y == p["y"]) & same_shift & same_pins & no_pull & no_push))

        def mov_dest_ok(src):
            x_ok = Mux(field == 0, x == src, x == p["x"])
            y_ok = Mux(field == 1, y == src, y == p["y"])
            osr_ok = Mux(field == 2, osr == src, osr == p["osr"])
            isr_ok = Mux(field == 3, isr == src, isr == p["isr"])
            core_out = Mux(field == 4, src, p["out"])
            out_ok = out == overlay(core_out, side_now)
            oe_ok = Mux(field == 5, oe == src, oe == p["oe"])
            pin_sel = (out_pin == p["out_pin"]) & (in_pin == p["in_pin"])
            return adv & x_ok & y_ok & osr_ok & isr_ok & out_ok & oe_ok & pin_sel & no_pull & no_push

        crc_lo = pcrc[0:8]
        crc_hi = Cat(pcrc[8:15], Const(0, 1))
        crc_out_src = Cat(pcrc[14], Const(0, 7))
        crc_out_next = Cat(Const(0, 1), pcrc[0:14])
        HA("mov_crc_lo", when(mov & (payload == REG_CRC_LO)) | (mov_dest_ok(crc_lo) & (crc == pcrc)))
        HA("mov_crc_hi", when(mov & (payload == REG_CRC_HI)) | (mov_dest_ok(crc_hi) & (crc == pcrc)))
        HA("mov_crc_out", when(mov & (payload == REG_CRC_OUT)) | (mov_dest_ok(crc_out_src) & (crc == crc_out_next)))

        for name, cond in asserts:
            m.d.comb += Assert(cond, message=name)
        with m.If(valid):
            for name, cond in H:
                m.d.comb += Assert(cond, message=name)
        self.names = [n for n, _ in asserts] + [n for n, _ in H]
        return m


class ImemHarness(Elaboratable):
    """ClockedImem SRAM contract: registered DOUT is write-through of last-cycle ADDR."""

    def __init__(self) -> None:
        self.dut = ClockedImem()

    def elaborate(self, platform) -> Module:
        m = Module()
        dut = self.dut
        m.submodules.dut = dut.elaborate(platform)
        mem = dut.dbg_mem
        valid = Signal()
        m.d.sync += valid.eq(1)

        def past(sig, name):
            p = Signal.like(sig, name=f"p_{name}")
            m.d.sync += p.eq(sig)
            return p

        p_aa, p_ba = past(dut.a_addr, "aa"), past(dut.b_addr, "ba")
        with m.If(valid):
            m.d.comb += Assert(dut.a_data == mem[p_aa], message="a_rdata_is_fetched")
            m.d.comb += Assert(dut.b_data == mem[p_ba], message="b_rdata_is_fetched")
        return m


class ChipHarness(Elaboratable):
    """2-SM / 4-slot: fetch_pc is next-pc; instr is ClockedImem DOUT; pc follows fetch.

    csr_we/addr/wdata are free SAT inputs (same halt-write / run-hold as 1-SM).
    """

    def __init__(self) -> None:
        self.dut = GraphEngine(n_sm=N_SM_CHIP, n_slots=N_SLOTS)

    def elaborate(self, platform) -> Module:
        m = Module()
        dut = self.dut
        m.submodules.dut = dut.elaborate(platform)
        m.d.comb += dut.sm_sel.eq(0)
        d = dut.dbg
        imem = d["imem"][0]
        valid = Signal()
        m.d.sync += valid.eq(1)

        def past(sig, name):
            p = Signal.like(sig, name=f"p_{name}")
            m.d.sync += p.eq(sig)
            return p

        H: list[tuple[str, object]] = []

        def HA(name, cond):
            H.append((name, cond))

        A_now: list[tuple[str, object]] = []

        def A(name, cond):
            A_now.append((name, cond))

        p_run = past(dut.run, "run")
        p_we = past(dut.csr_we, "csrwe")
        p_addr = past(dut.csr_addr, "csraddr")
        p_w = past(dut.csr_wdata, "csrw")
        host_csr = p_we & ~p_run

        def csr_wrote(addr):
            return host_csr & (p_addr == addr)

        A("sm0_imem_addr", imem.a_addr == Cat(d["fetch_pc"][0], d["sm_slot"][0]))
        A("sm1_imem_addr", imem.b_addr == Cat(d["fetch_pc"][1], d["sm_slot"][1]))
        A("sm0_instr_is_dout", d["instr"][0] == imem.a_data)
        A("sm1_instr_is_dout", d["instr"][1] == imem.b_data)

        write_slot, fifo_sel = d["write_slot"], d["fifo_sel"]
        p_wslot = past(write_slot, "wslot")
        p_fsel = past(fifo_sel, "fsel")
        HA("csr_write_slot", write_slot == Mux(csr_wrote(CSR_WRITE_SLOT), p_w[0:2], p_wslot))
        HA("csr_fifo_sel", fifo_sel == Mux(csr_wrote(CSR_FIFO_SEL), p_w[0], p_fsel))

        sm0 = (
            (CSR_SM0_SLOT, CSR_SM0_CLKDIV_LO, CSR_SM0_CLKDIV_HI, CSR_SM0_CLKDIV_FRAC,
             CSR_SM0_WRAP_BOT, CSR_SM0_WRAP_TOP, CSR_SM0_SIDE),
        )
        sm_csrs = [
            (0, CSR_SM0_SLOT, CSR_SM0_CLKDIV_LO, CSR_SM0_CLKDIV_HI, CSR_SM0_CLKDIV_FRAC,
             CSR_SM0_WRAP_BOT, CSR_SM0_WRAP_TOP, CSR_SM0_SIDE),
            (1, CSR_SM1_SLOT, CSR_SM1_CLKDIV_LO, CSR_SM1_CLKDIV_HI, CSR_SM1_CLKDIV_FRAC,
             CSR_SM1_WRAP_BOT, CSR_SM1_WRAP_TOP, CSR_SM1_SIDE),
        ]
        for s, a_slot, a_lo, a_hi, a_fr, a_bot, a_top, a_side in sm_csrs:
            slot = d["sm_slot"][s]
            cdiv, cfrac = d["clkdiv_int"][s], d["clkdiv_frac"][s]
            wbot, wtop = d["wrap_bot"][s], d["wrap_top"][s]
            sbase, scnt = d["side_base"][s], d["side_count"][s]
            p_slot = past(slot, f"slot{s}")
            p_cdiv = past(cdiv, f"cdiv{s}")
            p_cfrac = past(cfrac, f"cfrac{s}")
            p_bot = past(wbot, f"bot{s}")
            p_top = past(wtop, f"top{s}")
            p_base = past(sbase, f"sbase{s}")
            p_cnt = past(scnt, f"scnt{s}")
            HA(f"sm{s}_slot", slot == Mux(csr_wrote(a_slot), p_w[0:2], p_slot))
            HA(f"sm{s}_clkdiv_lo", cdiv[0:8] == Mux(csr_wrote(a_lo), p_w, p_cdiv[0:8]))
            HA(f"sm{s}_clkdiv_hi", cdiv[8:16] == Mux(csr_wrote(a_hi), p_w, p_cdiv[8:16]))
            HA(f"sm{s}_clkdiv_frac", cfrac == Mux(csr_wrote(a_fr), p_w, p_cfrac))
            HA(f"sm{s}_wrap_bot", wbot == Mux(csr_wrote(a_bot), p_w[0:5], p_bot))
            HA(f"sm{s}_wrap_top", wtop == Mux(csr_wrote(a_top), p_w[0:5], p_top))
            HA(f"sm{s}_side_base", sbase == Mux(csr_wrote(a_side), p_w[0:3], p_base))
            HA(f"sm{s}_side_count", scnt == Mux(csr_wrote(a_side), p_w[4], p_cnt))

        for s in range(N_SM_CHIP):
            pc = d["pcs"][s]
            fetch = d["fetch_pc"][s]
            A(f"sm{s}_tx_n_bound", d["tx_n_all"][s] <= FIFO_DEPTH)
            A(f"sm{s}_rx_n_bound", d["rx_n_all"][s] <= FIFO_DEPTH)
            p_fetch = past(fetch, f"fpc{s}")
            HA(f"sm{s}_pc_follows_fetch", pc == p_fetch)
            HA(f"sm{s}_idle_fetch_is_pc", (d["clk_en"][s] & dut.run) | (fetch == pc))

        for name, cond in A_now:
            m.d.comb += Assert(cond, message=name)
        with m.If(valid):
            for name, cond in H:
                m.d.comb += Assert(cond, message=name)
        self.names = [n for n, _ in A_now] + [n for n, _ in H]
        return m


YS = """read_rtlil {il}
hierarchy -top top
proc
chformal -lower
flatten
opt_clean
sat -tempinduct -prove-asserts -set rst 0 -maxsteps {steps} -verify -dump_vcd {vcd}
"""


def _sat(stem: str, h: Elaboratable, ports: list, steps: int) -> tuple[bool, str]:
    BUILD.mkdir(parents=True, exist_ok=True)
    il, ys, logf, vcd = f"{stem}.il", f"{stem}.ys", f"{stem}.log", f"{stem}_cex.vcd"
    (BUILD / il).write_text(rtlil.convert(h, name="top", ports=ports))
    h.dut._MustUse__used = True  # elaborated by hand inside the harness
    (BUILD / ys).write_text(YS.format(il=il, steps=steps, vcd=vcd))
    (BUILD / logf).unlink(missing_ok=True)
    cmd = f"yosys -q -l {logf} -s {ys}"
    if shutil.which("yosys"):
        r = subprocess.run(cmd.split(), cwd=BUILD, capture_output=True, text=True)
    elif shutil.which("docker"):
        rel = BUILD.relative_to(ROOT).as_posix()
        r = subprocess.run(
            ["docker", "run", "--rm", "-u", f"{os.getuid()}:{os.getgid()}", "-v", f"{ROOT}:/work", "-w", f"/work/{rel}",
             "--entrypoint", "/bin/sh", IMAGE, "-c", cmd],
            capture_output=True, text=True,
        )
    else:
        raise RuntimeError("needs yosys on PATH or docker")
    log = (BUILD / logf).read_text() if (BUILD / logf).exists() else r.stdout + r.stderr
    ok = r.returncode == 0 and "Induction step proven: SUCCESS!" in log
    return ok, log


def prove(steps: int = 12, verbose: bool = False) -> tuple[bool, str]:
    h = Harness()
    d = h.dut
    ports = [d.run, d.gpio_in, d.imem_we, d.imem_waddr, d.imem_wdata, d.csr_we, d.csr_addr,
             d.csr_wdata, d.tx_we, d.tx_data, d.rx_re,
             d.gpio_out, d.gpio_oe, d.tx_full, d.rx_data, d.rx_empty, d.pc]
    ok1, log1 = _sat("formal", h, ports, steps)

    imem_h = ImemHarness()
    im = imem_h.dut
    iports = [im.w_en, im.w_addr, im.w_data, im.a_addr, im.a_data, im.b_addr, im.b_data]
    ok_im, log_im = _sat("formal_imem", imem_h, iports, steps)

    chip = ChipHarness()
    c = chip.dut
    cports = [c.run, c.gpio_in, c.imem_we, c.imem_waddr, c.imem_wdata, c.imem_slot, c.imem_sel,
              c.csr_we, c.csr_addr, c.csr_wdata,
              c.tx_we, c.tx_data, c.rx_re, c.gpio_out, c.gpio_oe, c.tx_full, c.rx_data, c.rx_empty, c.pc]
    ok2, log2 = _sat("formal_chip", chip, cports, steps)

    log = (
        log1
        + "\n===== ClockedImem SRAM =====\n" + log_im
        + "\n===== CHIP 2-SM fetch =====\n" + log2
    )
    (BUILD / "formal.log").write_text(log)
    if verbose:
        print(log[-5000:])
    return ok1 and ok_im and ok2, log


def main() -> int:
    ok, log = prove(verbose=True)
    print("FORMAL", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
