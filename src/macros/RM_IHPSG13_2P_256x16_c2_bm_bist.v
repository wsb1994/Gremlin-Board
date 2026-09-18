// Behavioural 2-port SRAM matching IHP RM_IHPSG13_2P_256x16_c2_bm_bist timing:
// ADDR this posedge, DOUT that word on the next posedge. BIST unused.
// LibreLane synth blackboxes this name and uses the LEF/GDS/LIB views.
`timescale 1ns/10ps
module RM_IHPSG13_2P_256x16_c2_bm_bist (
    input        A_CLK, A_MEN, A_WEN, A_REN,
    input  [7:0] A_ADDR,
    input [15:0] A_DIN,
    input        A_DLY,
    output reg [15:0] A_DOUT,
    input [15:0] A_BM,
    input        A_BIST_CLK, A_BIST_EN, A_BIST_MEN, A_BIST_WEN, A_BIST_REN,
    input  [7:0] A_BIST_ADDR,
    input [15:0] A_BIST_DIN, A_BIST_BM,
    input        B_CLK, B_MEN, B_WEN, B_REN,
    input  [7:0] B_ADDR,
    input [15:0] B_DIN,
    input        B_DLY,
    output reg [15:0] B_DOUT,
    input [15:0] B_BM,
    input        B_BIST_CLK, B_BIST_EN, B_BIST_MEN, B_BIST_WEN, B_BIST_REN,
    input  [7:0] B_BIST_ADDR,
    input [15:0] B_BIST_DIN, B_BIST_BM
);
  reg [15:0] mem [0:255];
  integer i;
  initial begin
    A_DOUT = 16'h0;
    B_DOUT = 16'h0;
    for (i = 0; i < 256; i = i + 1) mem[i] = 16'h0;
  end
  always @(posedge A_CLK) begin
    if (A_MEN && A_WEN)
      mem[A_ADDR] <= (A_DIN & A_BM) | (mem[A_ADDR] & ~A_BM);
    else if (A_MEN && A_REN)
      A_DOUT <= mem[A_ADDR];
  end
  always @(posedge B_CLK) begin
    if (B_MEN && B_WEN)
      mem[B_ADDR] <= (B_DIN & B_BM) | (mem[B_ADDR] & ~B_BM);
    else if (B_MEN && B_REN)
      B_DOUT <= mem[B_ADDR];
  end
endmodule
