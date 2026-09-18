`timescale 1ns/1ps
module tb;
  reg clk = 0, rst = 1;
  always #10 clk = ~clk;

  reg tx_run=0, rx_run=0;
  reg tx_we=0, rx_re=0, tx_imem_we=0, rx_imem_we=0, tx_csr_we=0, rx_csr_we=0;
  reg [4:0] tx_waddr=0, rx_waddr=0, tx_csr_addr=0, rx_csr_addr=0;
  reg [15:0] tx_wdata=0, rx_wdata=0;
  reg [7:0] tx_byte=0, tx_csr_wdata=0, rx_csr_wdata=0;
  wire [7:0] tx_out, tx_oe, rx_out, rx_oe, tx_rxdata, rx_rxdata;
  wire tx_full, rx_full, tx_empty, rx_empty;
  wire [4:0] tx_pc, rx_pc;
  // Wired-AND pad with pull-up: drive-0 wins, undriven bits are 1. Matches
  // open-drain I2C/SWD and push-pull UART/SPI (OE+out=1 → pad 1).
  wire [7:0] bus = ~((tx_oe & ~tx_out) | (rx_oe & ~rx_out));

  loom_engine tx (
    .clk(clk), .rst(rst), .run(tx_run),
    .gpio_in(bus), .gpio_out(tx_out), .gpio_oe(tx_oe),
    .imem_we(tx_imem_we), .imem_waddr(tx_waddr), .imem_wdata(tx_wdata),
    .imem_slot(2'b00), .sm_sel(1'b0), .csr_we(tx_csr_we), .csr_addr(tx_csr_addr), .csr_wdata(tx_csr_wdata),
    .tx_we(tx_we), .tx_data(tx_byte), .tx_full(tx_full),
    .rx_re(1'b0), .rx_data(tx_rxdata), .rx_empty(tx_empty), .pc(tx_pc)
  );
  loom_engine rx (
    .clk(clk), .rst(rst), .run(rx_run),
    .gpio_in(bus), .gpio_out(rx_out), .gpio_oe(rx_oe),
    .imem_we(rx_imem_we), .imem_waddr(rx_waddr), .imem_wdata(rx_wdata),
    .imem_slot(2'b00), .sm_sel(1'b0), .csr_we(rx_csr_we), .csr_addr(rx_csr_addr), .csr_wdata(rx_csr_wdata),
    .tx_we(1'b0), .tx_data(8'h00), .tx_full(rx_full),
    .rx_re(rx_re), .rx_data(rx_rxdata), .rx_empty(rx_empty), .pc(rx_pc)
  );

  reg [15:0] TXW [0:31];
  initial begin
    TXW[0] = 16'hc000;
    TXW[1] = 16'hc023;
    TXW[2] = 16'h8020;
    TXW[3] = 16'hc066;
    TXW[4] = 16'hc043;
    TXW[5] = 16'hc0a0;
    TXW[6] = 16'hc081;
    TXW[7] = 16'hc0a1;
    TXW[8] = 16'hc080;
    TXW[9] = 16'hc081;
    TXW[10] = 16'hc0a1;
    TXW[11] = 16'h0065;
    TXW[12] = 16'h0084;
    TXW[13] = 16'hc080;
    TXW[14] = 16'hc081;
    TXW[15] = 16'hc1a1;
    TXW[16] = 16'hc081;
    TXW[17] = 16'hc1a1;
    TXW[18] = 16'hc042;
    TXW[19] = 16'hc0a0;
    TXW[20] = 16'hc081;
    TXW[21] = 16'hc0a1;
    TXW[22] = 16'hc080;
    TXW[23] = 16'hc081;
    TXW[24] = 16'hc0a1;
    TXW[25] = 16'h0073;
    TXW[26] = 16'hc047;
    TXW[27] = 16'h6021;
    TXW[28] = 16'hc081;
    TXW[29] = 16'hc0a1;
    TXW[30] = 16'h007b;
    TXW[31] = 16'h0002;
  end

  reg [15:0] RXW [0:12];
  initial begin
    RXW[0] = 16'hc067;
    RXW[1] = 16'hc047;
    RXW[2] = 16'h2011;
    RXW[3] = 16'h2001;
    RXW[4] = 16'h0062;
    RXW[5] = 16'h0081;
    RXW[6] = 16'hc047;
    RXW[7] = 16'h2011;
    RXW[8] = 16'h4021;
    RXW[9] = 16'h2001;
    RXW[10] = 16'h0067;
    RXW[11] = 16'h8000;
    RXW[12] = 16'h0000;
  end

  reg [7:0] PAY [0:1];
  initial begin
    PAY[0] = 8'h48;
    PAY[1] = 8'h69;
  end

  integer i, ngot, src, idle, pop, lim;
  reg [7:0] got [0:2];
  initial begin
    lim = 256 + 2 * 400;
    ngot = 0; src = 0; idle = 0; pop = 0;
    repeat (4) @(posedge clk);
    rst = 0;
    for (i = 0; i < 32; i = i + 1) begin
      @(posedge clk);
      tx_imem_we = 1; tx_waddr = i[4:0]; tx_wdata = TXW[i];
    end
    @(posedge clk); tx_imem_we = 0;
    for (i = 0; i < 13; i = i + 1) begin
      @(posedge clk);
      rx_imem_we = 1; rx_waddr = i[4:0]; rx_wdata = RXW[i];
    end
    @(posedge clk); rx_imem_we = 0;
    @(posedge clk); tx_csr_we = 1; tx_csr_addr = 6; tx_csr_wdata = 8'h00;
    @(posedge clk); tx_csr_addr = 7; tx_csr_wdata = 8'h1f;
    @(posedge clk); tx_csr_addr = 8; tx_csr_wdata = 8'h00;
    @(posedge clk); tx_csr_we = 0;
    @(posedge clk); rx_csr_we = 1; rx_csr_addr = 6; rx_csr_wdata = 8'h00;
    @(posedge clk); rx_csr_addr = 7; rx_csr_wdata = 8'h1f;
    @(posedge clk); rx_csr_addr = 8; rx_csr_wdata = 8'h00;
    @(posedge clk); rx_csr_we = 0;
    tx_run = 1; rx_run = 1;
    for (i = 0; i < lim; i = i + 1) begin
      @(negedge clk);
      tx_we = 0;
      rx_re = 0;
      if (src < 2 && !tx_full) begin
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
      if (src >= 2 && ngot >= 2 && idle > 64) i = lim;
    end
    if (ngot !== 2) begin
      $display("FAIL ngot=%0d want=2", ngot);
      $fatal;
    end
    for (i = 0; i < 2; i = i + 1) begin
      if (got[i] !== PAY[i]) begin
        $display("FAIL idx=%0d got=%02x want=%02x", i, got[i], PAY[i]);
        $fatal;
      end
    end
    $display("PASS 2 bytes");
    $finish;
  end
endmodule
