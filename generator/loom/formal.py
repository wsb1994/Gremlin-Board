"""Formal properties of the graph engine, proven by k-induction.

Two families, both checked for *every* reachable state (not a test vector):

  Structural invariants
    FIFO occupancy bounds, full/empty flags, pointer/occupancy consistency,
    writes dropped when full, halt freezes the SM, no imem load while running.

  ISA one-step semantics
    For each opcode: given the previous cycle's state and the instruction at
    pc, the current state is exactly what the ISA says (pc, delay counter,
    x, y, osr, isr, pins, FIFO side effects, stalls). This is the interpreter's
    step function written as assertions, independent of rtl.py's structure.

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

from amaranth import Cat, Elaboratable, Module, Mux, Signal
from amaranth.back import rtlil
from amaranth.hdl import Assert

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
    JMP_Y_EQ0,
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
        d = dut.dbg
        x, y, osr, isr = d["x"][0], d["y"][0], d["osr"][0], d["isr"][0]
        delay_ctr, out_pin, in_pin = d["delay_ctr"][0], d["out_pin"][0], d["in_pin"][0]
        imem, instr = d["imem"][0], d["instr"][0]
        tx_mem, rx_mem = d["tx_mem"], d["rx_mem"]
        tx_r, tx_w, tx_n = d["tx_r"], d["tx_w"], d["tx_n"]
        rx_r, rx_w, rx_n = d["rx_r"], d["rx_w"], d["rx_n"]
        eff = d["eff"]
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
            instr=past(instr, "instr"), eff=past(eff, "eff"),
            tx_r=past(tx_r, "txr"), tx_w=past(tx_w, "txw"), tx_n=past(tx_n, "txn"),
            rx_r=past(rx_r, "rxr"), rx_w=past(rx_w, "rxw"), rx_n=past(rx_n, "rxn"),
            tx_we=past(dut.tx_we, "txwe"), tx_data=past(dut.tx_data, "txd"),
            rx_re=past(dut.rx_re, "rxre"), imem_we=past(dut.imem_we, "imwe"),
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
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"])
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

        # ---- ISA one-step semantics ----------------------------------
        pi = p["instr"]
        op, delay, field, payload = pi[13:16], pi[8:13], pi[5:8], pi[0:5]
        step = p["run"] & (p["delay_ctr"] == 0)      # an instruction executed
        pc1 = (p["pc"] + 1)[0:5]
        adv = (pc == pc1) & (delay_ctr == delay)     # normal advance
        jmp_to = (pc == payload) & (delay_ctr == delay)
        stalled = (pc == p["pc"]) & (delay_ctr == 0)
        same_regs = (x == p["x"]) & (y == p["y"])
        same_shift = (osr == p["osr"]) & (isr == p["isr"])
        same_pins = (out == p["out"]) & (oe == p["oe"]) & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"])
        no_pull = tx_r == p["tx_r"]
        no_push = rx_w == p["rx_w"]
        untouched = same_regs & same_shift & same_pins & no_pull & no_push

        # delay counter ticking
        HA("delay_counts_down", ~(p["run"] & (p["delay_ctr"] != 0)) |
           ((delay_ctr == (p["delay_ctr"] - 1)[0:5]) & (pc == p["pc"]) & untouched))

        def when(cond):
            return ~(step & cond)

        # NOP
        HA("nop", when(op == OP_NOP) | (adv & untouched))
        # JMP
        pin_bit = (p["eff"] >> p["in_pin"])[0]
        HA("jmp_always", when((op == OP_JMP) & (field == JMP_ALWAYS)) | (jmp_to & untouched))
        HA("jmp_x_eq0", when((op == OP_JMP) & (field == JMP_X_EQ0)) |
           (Mux(p["x"] == 0, jmp_to, adv) & untouched))
        HA("jmp_y_eq0_is_fallthrough", when((op == OP_JMP) & (field == JMP_Y_EQ0)) | (adv & untouched))
        HA("jmp_x_dec", when((op == OP_JMP) & (field == JMP_X_DEC)) |
           Mux(p["x"] != 0, jmp_to & (x == (p["x"] - 1)[0:8]) & (y == p["y"]), adv & same_regs)
           & same_shift & same_pins & no_pull & no_push)
        HA("jmp_y_dec", when((op == OP_JMP) & (field == JMP_Y_DEC)) |
           Mux(p["y"] != 0, jmp_to & (y == (p["y"] - 1)[0:8]) & (x == p["x"]), adv & same_regs)
           & same_shift & same_pins & no_pull & no_push)
        HA("jmp_pin", when((op == OP_JMP) & (field == JMP_PIN)) | (Mux(pin_bit, jmp_to, adv) & untouched))
        HA("jmp_undefined_fields", when((op == OP_JMP) & (field > JMP_PIN)) | (adv & untouched))
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
           (adv & (out == out_exp) & (osr == osr_exp) & (isr == p["isr"]) & (oe == p["oe"])
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
           (adv & (out[0:5] == payload) & (out[5:8] == p["out"][5:8]) & (oe == p["oe"])
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("set_pindirs", set_is(SET_PINDIRS) |
           (adv & (oe[0:5] == payload) & (oe[5:8] == p["oe"][5:8]) & (out == p["out"])
            & (out_pin == p["out_pin"]) & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("set_x", set_is(SET_X) | (adv & (x == payload) & (y == p["y"]) & same_shift & same_pins & no_pull & no_push))
        HA("set_y", set_is(SET_Y) | (adv & (y == payload) & (x == p["x"]) & same_shift & same_pins & no_pull & no_push))
        bmask = (1 << payload[0:3])[0:8]
        HA("set_bit", set_is(SET_BIT) |
           (adv & (out == (p["out"] | bmask)) & (oe == p["oe"]) & (out_pin == p["out_pin"])
            & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("clr_bit", set_is(CLR_BIT) |
           (adv & (out == (p["out"] & ~bmask)) & (oe == p["oe"]) & (out_pin == p["out_pin"])
            & (in_pin == p["in_pin"]) & same_regs & same_shift & no_pull & no_push))
        HA("set_outpin", set_is(SET_OUTPIN) |
           (adv & (out_pin == payload[0:3]) & (in_pin == p["in_pin"]) & (out == p["out"]) & (oe == p["oe"])
            & same_regs & same_shift & no_pull & no_push))
        HA("set_inpin", set_is(SET_INPIN) |
           (adv & (in_pin == payload[0:3]) & (out_pin == p["out_pin"]) & (out == p["out"]) & (oe == p["oe"])
            & same_regs & same_shift & no_pull & no_push))

        for name, cond in asserts:
            m.d.comb += Assert(cond, message=name)
        with m.If(valid):
            for name, cond in H:
                m.d.comb += Assert(cond, message=name)
        self.names = [n for n, _ in asserts] + [n for n, _ in H]
        return m


YS = """read_rtlil {il}
hierarchy -top top
proc
chformal -lower
flatten
opt_clean
sat -tempinduct -prove-asserts -set rst 0 -maxsteps {steps} -verify -dump_vcd {vcd}
"""


def prove(steps: int = 12, verbose: bool = False) -> tuple[bool, str]:
    BUILD.mkdir(parents=True, exist_ok=True)
    h = Harness()
    d = h.dut
    ports = [d.run, d.gpio_in, d.imem_we, d.imem_waddr, d.imem_wdata, d.tx_we, d.tx_data, d.rx_re,
             d.gpio_out, d.gpio_oe, d.tx_full, d.rx_data, d.rx_empty, d.pc]
    (BUILD / "formal.il").write_text(rtlil.convert(h, name="top", ports=ports))
    d._MustUse__used = True  # elaborated by hand inside Harness
    (BUILD / "formal.ys").write_text(YS.format(il="formal.il", steps=steps, vcd="formal_cex.vcd"))
    (BUILD / "formal.log").unlink(missing_ok=True)
    cmd = "yosys -q -l formal.log -s formal.ys"
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
    log = (BUILD / "formal.log").read_text() if (BUILD / "formal.log").exists() else r.stdout + r.stderr
    ok = r.returncode == 0 and "Induction step proven: SUCCESS!" in log
    if verbose:
        print(log[-4000:])
    return ok, log


def main() -> int:
    ok, log = prove(verbose=True)
    print("FORMAL", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
