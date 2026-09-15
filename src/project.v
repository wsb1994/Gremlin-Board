/* Generated wrapper. Graph programs load at runtime. */

`default_nettype none

// Host protocol. clk sampled; rst_n active-low (engine rst = ~rst_n).
//   ui_in[0]     run
//   ui_in[1]     strobe A (imem two-phase, or CSR if ui_in[7] also high)
//   ui_in[6:2]   imem/CSR address (latched on imem low-byte strobe)
//   ui_in[7]     strobe B: TX push / RX pop, or CSR qualifier with strobe A
//   ui_in[2]     during strobe B: 0 = TX push, 1 = RX pop (peek rx_data on uo)
//   uio_in[7:0]  data byte while run=0; GPIO in while run=1
//   uo_out         run=1: {pc, rx_empty, tx_full, run}
//                  run=0 and ui_in[2]=1: rx_data (FIFO head)
//                  run=0 and ui_in[2]=0: {pc, rx_empty, tx_full, 1'b0}
// Load 16-bit word W at address A into the current write-slot (run=0; ui_in[7]=0):
//   1. uio_in=W[7:0],  ui_in[6:2]=A, pulse ui_in[1]
//   2. uio_in=W[15:8], pulse ui_in[1] again
// CSR write (run=0): hold ui_in[7]=1, uio_in=data, ui_in[6:2]=csr_addr, pulse ui_in[1]
//   csr 0 = write-slot (0..3); 1/2 = SM0/SM1 execute-slot; 3-5 = SM0 clkdiv
// Push TX: uio_in=B, ui_in[2]=0, pulse ui_in[7]
// Pop RX:  ui_in[2]=1, read uo_out as data, pulse ui_in[7]
// Run: ui_in[0]=1 (uio becomes GPIO; inputs are 2FF-synchronised)
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
  wire [15:0] imem_wdata = {uio_in, lo};

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
  assign uo_out  = run ? {pc, rx_empty, tx_full, run} :
                   (ui_in[2] ? rx_data : {pc, rx_empty, tx_full, 1'b0});
  wire _unused = &{ena, 1'b0};
endmodule
