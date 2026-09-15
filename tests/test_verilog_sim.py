"""Compile generated Verilog and round-trip a payload with iverilog."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from loom.emit import emit
from loom.stream import load_graph

from payloads import PAYLOADS, PROTOCOLS
from test_all_protocols import PAIRS, HI as PROTO_HI

ROOT = Path(__file__).resolve().parents[1]
PLANS = ROOT / "plans"
GEN = ROOT / "test" / "gen"


def _tb(tx_words, rx_words, payload: bytes) -> str:
    def arr16(name, words):
        body = ", ".join(f"16'h{w:04x}" for w in words)
        return f"  reg [15:0] {name} [0:{len(words)-1}];\n  initial begin\n" + "".join(
            f"    {name}[{i}] = 16'h{w:04x};\n" for i, w in enumerate(words)
        ) + "  end\n"

    def arr8(name, data):
        return f"  reg [7:0] {name} [0:{len(data)-1}];\n  initial begin\n" + "".join(
            f"    {name}[{i}] = 8'h{b:02x};\n" for i, b in enumerate(data)
        ) + "  end\n"

    ntx, nrx, n = len(tx_words), len(rx_words), len(payload)
    return f"""`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1;
  always #10 clk = ~clk;

  reg tx_run=0, rx_run=0;
  reg tx_we=0, rx_re=0, tx_imem_we=0, rx_imem_we=0;
  reg [4:0] tx_waddr=0, rx_waddr=0;
  reg [15:0] tx_wdata=0, rx_wdata=0;
  reg [7:0] tx_byte=0;
  wire [7:0] tx_out, tx_oe, rx_out, rx_oe, tx_rxdata, rx_rxdata;
  wire tx_full, rx_full, tx_empty, rx_empty;
  wire [4:0] tx_pc, rx_pc;

  loom_engine tx (
    .clk(clk), .rst(rst), .run(tx_run),
    .gpio_in(8'h00), .gpio_out(tx_out), .gpio_oe(tx_oe),
    .imem_we(tx_imem_we), .imem_waddr(tx_waddr), .imem_wdata(tx_wdata),
    .imem_slot(2'b00), .sm_sel(1'b0), .csr_we(1'b0), .csr_addr(5'b0), .csr_wdata(8'h00),
    .tx_we(tx_we), .tx_data(tx_byte), .tx_full(tx_full),
    .rx_re(1'b0), .rx_data(tx_rxdata), .rx_empty(tx_empty), .pc(tx_pc)
  );
  loom_engine rx (
    .clk(clk), .rst(rst), .run(rx_run),
    .gpio_in(tx_out), .gpio_out(rx_out), .gpio_oe(rx_oe),
    .imem_we(rx_imem_we), .imem_waddr(rx_waddr), .imem_wdata(rx_wdata),
    .imem_slot(2'b00), .sm_sel(1'b0), .csr_we(1'b0), .csr_addr(5'b0), .csr_wdata(8'h00),
    .tx_we(1'b0), .tx_data(8'h00), .tx_full(rx_full),
    .rx_re(rx_re), .rx_data(rx_rxdata), .rx_empty(rx_empty), .pc(rx_pc)
  );

{arr16("TXW", tx_words)}
{arr16("RXW", rx_words)}
{arr8("PAY", payload)}
  integer i, ngot, src, idle, pop, lim;
  reg [7:0] got [0:{n}];
  initial begin
    lim = 64 + {n} * 120;
    ngot = 0; src = 0; idle = 0; pop = 0;
    repeat (4) @(posedge clk);
    rst = 0;
    for (i = 0; i < {ntx}; i = i + 1) begin
      @(posedge clk);
      tx_imem_we = 1; tx_waddr = i[4:0]; tx_wdata = TXW[i];
    end
    @(posedge clk); tx_imem_we = 0;
    for (i = 0; i < {nrx}; i = i + 1) begin
      @(posedge clk);
      rx_imem_we = 1; rx_waddr = i[4:0]; rx_wdata = RXW[i];
    end
    @(posedge clk); rx_imem_we = 0;
    tx_run = 1; rx_run = 1;
    for (i = 0; i < lim; i = i + 1) begin
      @(negedge clk);
      tx_we = 0;
      rx_re = 0;
      if (src < {n} && !tx_full) begin
        tx_byte = PAY[src];
        tx_we = 1;
        src = src + 1;
      end
      if (!rx_empty) begin
        got[ngot] = rx_rxdata;
        ngot = ngot + 1;
        rx_re = 1;
        idle = 0;
      end else idle = idle + 1;
      if (src >= {n} && ngot >= {n} && idle > 64) i = lim;
    end
    if (ngot !== {n}) begin
      $display("FAIL ngot=%0d want={n}", ngot);
      $fatal;
    end
    for (i = 0; i < {n}; i = i + 1) begin
      if (got[i] !== PAY[i]) begin
        $display("FAIL idx=%0d got=%02x want=%02x", i, got[i], PAY[i]);
        $fatal;
      end
    end
    $display("PASS {n} bytes");
    $finish;
  end
endmodule
"""


def _run_vvp(tb_path: Path) -> str:
    engine = ROOT / "src" / "loom_engine.v"
    out = tb_path.with_suffix(".out")
    if shutil.which("iverilog"):
        cmd = [
            "iverilog",
            "-g2012",
            "-o",
            str(out),
            str(engine),
            str(tb_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        r = subprocess.run(["vvp", str(out)], check=True, capture_output=True, text=True)
        return r.stdout
    # CMOS5L CI image not required; use debian iverilog
    work = "/work"
    script = (
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update -qq && apt-get install -y -qq iverilog >/tmp/apt.log && "
        f"iverilog -g2012 -o /tmp/sim {work}/src/loom_engine.v {work}/{tb_path.relative_to(ROOT)} && "
        "vvp /tmp/sim"
    )
    r = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{ROOT}:{work}",
            "-w",
            work,
            "debian:bookworm-slim",
            "bash",
            "-lc",
            script,
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return r.stdout


@pytest.mark.parametrize("proto", PROTOCOLS)
@pytest.mark.parametrize("name", ("hello", "json_fill", "packed_tick"))
def test_verilog_roundtrip(proto: str, name: str):
    emit()
    payload = PAYLOADS[name]
    tx = load_graph(PLANS / f"{proto}_tx.toml")
    rx = load_graph(PLANS / f"{proto}_rx.toml")
    GEN.mkdir(parents=True, exist_ok=True)
    tb = GEN / f"tb_{proto}_{name}.v"
    tb.write_text(_tb(tx, rx, payload))
    log = _run_vvp(tb)
    assert "PASS" in log, log
    assert "FAIL" not in log, log


@pytest.mark.parametrize("name,txf,rxf", PAIRS, ids=[p[0] for p in PAIRS])
def test_verilog_every_protocol_hi(name, txf, rxf):
    emit()
    tx = load_graph(PLANS / txf)
    rx = load_graph(PLANS / rxf)
    GEN.mkdir(parents=True, exist_ok=True)
    tb = GEN / f"tb_all_{name}_hi.v"
    tb.write_text(_tb(tx, rx, PROTO_HI))
    log = _run_vvp(tb)
    assert "PASS" in log, log
    assert "FAIL" not in log, log
