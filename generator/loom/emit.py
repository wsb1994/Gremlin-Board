"""Emit Tiny Tapeout Verilog from the graph engine."""

from __future__ import annotations

from pathlib import Path

from amaranth.back import verilog

from loom.criteria import assert_engine_has_no_protocol_names, assert_pin_and_time_primitives
from loom.isa import N_SLOTS, N_SM_CHIP
from loom.rtl import GraphEngine

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
TOP = "tt_um_loom_gpe"


def _ports(dut: GraphEngine) -> list:
    p = [
        dut.run,
        dut.gpio_in,
        dut.gpio_out,
        dut.gpio_oe,
        dut.imem_we,
        dut.imem_waddr,
        dut.imem_wdata,
        dut.imem_slot,
        dut.sm_sel,
        dut.csr_we,
        dut.csr_addr,
        dut.csr_wdata,
        dut.tx_we,
        dut.tx_data,
        dut.tx_full,
        dut.rx_re,
        dut.rx_data,
        dut.rx_empty,
        dut.pc,
    ]
    if dut.n_sm > 1:
        p.append(dut.imem_sel)
    return p


def engine_verilog() -> str:
    # 1 SM / 1 slot: interp golden, iverilog ISA sweep, protocol Hi tests.
    core = GraphEngine()
    a = verilog.convert(core, name="loom_engine", ports=_ports(core))
    # Die: 2 SMs, 4 resident graphs.
    chip = GraphEngine(n_sm=N_SM_CHIP, n_slots=N_SLOTS)
    b = verilog.convert(chip, name="loom_chip", ports=_ports(chip))
    return a + "\n" + b


WRAPPER = f"""
`default_nettype none

// Host protocol. clk sampled; rst_n active-low (engine rst = ~rst_n).
//   ui_in[0]     run
//   ui_in[1]     strobe A (imem two-phase, or CSR if ui_in[7] also high)
//   ui_in[6:2]   imem/CSR address (latched on imem low-byte strobe)
//   ui_in[7]     strobe B: TX push / RX pop, or CSR qualifier with strobe A
//   ui_in[2]     during strobe B: 0 = TX push, 1 = RX pop (peek rx_data on uo)
//   uio_in[7:0]  data byte while run=0; GPIO in while run=1
//   uo_out         run=1: {{pc, rx_empty, tx_full, run}}
//                  run=0 and ui_in[2]=1: rx_data (FIFO head)
//                  run=0 and ui_in[2]=0: {{pc, rx_empty, tx_full, 1'b0}}
// Load 16-bit word W at address A into the current write-slot (run=0; ui_in[7]=0):
//   1. uio_in=W[7:0],  ui_in[6:2]=A, pulse ui_in[1]
//   2. uio_in=W[15:8], pulse ui_in[1] again
// CSR write (run=0): hold ui_in[7]=1, uio_in=data, ui_in[6:2]=csr_addr, pulse ui_in[1]
//   csr 0 = write-slot (0..3); 1/2 = SM0/SM1 execute-slot; 3-5 = SM0 clkdiv
// Push TX: uio_in=B, ui_in[2]=0, pulse ui_in[7]
// Pop RX:  ui_in[2]=1, read uo_out as data, pulse ui_in[7]
// Run: ui_in[0]=1 (uio becomes GPIO; inputs are 2FF-synchronised)
module {TOP} (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);
  wire rst = ~rst_n;
  wire run = ui_in[0];
  wire we  = ui_in[1] & ~run;
  wire txp = ui_in[7] & ~run;

  reg we_d, tx_d, hi;
  reg [4:0] addr;
  reg [7:0] lo;
  reg [1:0] wr_slot;
  reg [7:0] sync0, sync1;
  always @(posedge clk) begin
    if (rst) begin
      we_d <= 0;
      tx_d <= 0;
      hi <= 0;
      addr <= 0;
      lo <= 0;
      wr_slot <= 0;
      sync0 <= 0;
      sync1 <= 0;
    end else begin
      we_d <= we;
      tx_d <= txp;
      sync0 <= uio_in;
      sync1 <= sync0;
      if (run) begin
        hi <= 0;
      end else if (we & ~we_d) begin
        if (txp) begin
          if (ui_in[6:2] == 5'd0)
            wr_slot <= uio_in[1:0];
        end else if (!hi) begin
          addr <= ui_in[6:2];
          lo <= uio_in;
          hi <= 1;
        end else begin
          hi <= 0;
        end
      end
    end
  end

  wire csr_we  = we & ~we_d & txp;
  wire imem_we = we & ~we_d & hi & ~txp;
  wire tx_we   = txp & ~tx_d & ~we & ~ui_in[2];
  wire rx_re   = txp & ~tx_d & ~we &  ui_in[2];
  wire [15:0] imem_wdata = {{uio_in, lo}};

  wire [7:0] gpio_out, gpio_oe, rx_data;
  wire tx_full, rx_empty;
  wire [4:0] pc;

  loom_chip engine (
    .clk(clk),
    .rst(rst),
    .run(run),
    .gpio_in(run ? sync1 : uio_in),
    .gpio_out(gpio_out),
    .gpio_oe(gpio_oe),
    .imem_we(imem_we),
    .imem_waddr(addr),
    .imem_wdata(imem_wdata),
    .imem_slot(wr_slot),
    .imem_sel(wr_slot[0]),
    .sm_sel(1'b0),
    .csr_we(csr_we),
    .csr_addr(ui_in[6:2]),
    .csr_wdata(uio_in),
    .tx_we(tx_we),
    .tx_data(uio_in),
    .tx_full(tx_full),
    .rx_re(rx_re),
    .rx_data(rx_data),
    .rx_empty(rx_empty),
    .pc(pc)
  );

  assign uio_out = gpio_out;
  assign uio_oe  = run ? gpio_oe : 8'h00;
  assign uo_out  = run ? {{pc, rx_empty, tx_full, run}} :
                   (ui_in[2] ? rx_data : {{pc, rx_empty, tx_full, 1'b0}});
  wire _unused = &{{ena, 1'b0}};
endmodule
"""


# Verilator -Wall style categories that Amaranth/Yosys-generated Verilog trips
# by construction. None is a functional issue; the engine is checked by the
# exhaustive ISA golden (every encoding, interp vs this file under iverilog)
# and by k-induction (loom formal). Scoped to this generated file only.
#   WIDTHTRUNC/WIDTHEXPAND  yosys writes `x == 0` as `!x`, `sig >> n` into 1-bit nets
#   PROCASSINIT             every flop has an `init` value *and* a sync reset
#   UNUSEDSIGNAL            carry/overflow bits of widened adders, unused SM handles
#   CASEINCOMPLETE          Array element writes are `casez` without default
LINT_OFF = ("WIDTHTRUNC", "WIDTHEXPAND", "PROCASSINIT", "UNUSEDSIGNAL", "CASEINCOMPLETE")
LINT_HEADER = (
    "/* Generated by loom.emit — do not edit. */\n"
    "/* verilator lint_off " + " */\n/* verilator lint_off ".join(LINT_OFF) + " */\n"
)
LINT_FOOTER = "/* verilator lint_on " + " */\n/* verilator lint_on ".join(LINT_OFF) + " */\n"


def emit() -> Path:
    assert_engine_has_no_protocol_names()
    assert_pin_and_time_primitives()
    engine = engine_verilog()
    (SRC / "loom_engine.v").write_text(LINT_HEADER + engine + LINT_FOOTER)
    (SRC / "project.v").write_text(
        "/* Generated wrapper. Graph programs load at runtime. */\n" + WRAPPER
    )
    return SRC / "project.v"


def main() -> None:
    print(emit())
    print(SRC / "loom_engine.v")


if __name__ == "__main__":
    main()
