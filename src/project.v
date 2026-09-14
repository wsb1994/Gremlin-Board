/* Generated wrapper. Graph programs load at runtime. */

`default_nettype none

// Host protocol. clk sampled; rst_n active-low (engine rst = ~rst_n).
//   ui_in[0]     run
//   ui_in[1]     imem write strobe (rising edge, two-phase)
//   ui_in[6:2]   imem address, latched on the low-byte strobe
//   ui_in[7]     TX FIFO push strobe (rising edge)
//   uio_in[7:0]  data byte while run=0; GPIO in while run=1
//   uo_out[0]    run
//   uo_out[1]    tx_full
//   uo_out[2]    rx_empty
//   uo_out[7:3]  pc
// Load 16-bit word W at address A (run=0; do not pulse tx the same cycle):
//   1. uio_in=W[7:0],  ui_in[6:2]=A, pulse ui_in[1] (0→1 ≥1 clk →0 ≥1 clk)
//   2. uio_in=W[15:8], pulse ui_in[1] again (commits {W[15:8], W[7:0]} to imem[A])
// Push TX byte B (run=0; depth 4; skip if uo_out[1]==1):
//   3. uio_in=B, pulse ui_in[7]
// Run:
//   4. ui_in[0]=1  (uio becomes GPIO; uio_oe follows the graph)
module tt_um_loom_gpe (
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
  always @(posedge clk) begin
    if (rst) begin
      we_d <= 0;
      tx_d <= 0;
      hi <= 0;
      addr <= 0;
      lo <= 0;
    end else begin
      we_d <= we;
      tx_d <= txp;
      if (run) begin
        hi <= 0;
      end else if (we & ~we_d) begin
        if (!hi) begin
          addr <= ui_in[6:2];
          lo <= uio_in;
          hi <= 1;
        end else begin
          hi <= 0;
        end
      end
    end
  end

  wire imem_we = we & ~we_d & hi;
  wire tx_we   = txp & ~tx_d;
  wire [15:0] imem_wdata = {uio_in, lo};

  wire [7:0] gpio_out, gpio_oe, rx_data;
  wire tx_full, rx_empty;
  wire [4:0] pc;

  loom_engine engine (
    .clk(clk),
    .rst(rst),
    .run(run),
    .gpio_in(uio_in),
    .gpio_out(gpio_out),
    .gpio_oe(gpio_oe),
    .imem_we(imem_we),
    .imem_waddr(addr),
    .imem_wdata(imem_wdata),
    .tx_we(tx_we),
    .tx_data(uio_in),
    .tx_full(tx_full),
    .rx_re(1'b0),
    .rx_data(rx_data),
    .rx_empty(rx_empty),
    .pc(pc)
  );

  assign uio_out = gpio_out;
  assign uio_oe  = run ? gpio_oe : 8'h00;
  assign uo_out  = {pc, rx_empty, tx_full, run};
  wire _unused = &{ena, rx_data, 1'b0};
endmodule
