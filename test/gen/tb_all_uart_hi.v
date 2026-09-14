`timescale 1ns/1ps
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
    .tx_we(tx_we), .tx_data(tx_byte), .tx_full(tx_full),
    .rx_re(1'b0), .rx_data(tx_rxdata), .rx_empty(tx_empty), .pc(tx_pc)
  );
  loom_engine rx (
    .clk(clk), .rst(rst), .run(rx_run),
    .gpio_in(tx_out), .gpio_out(rx_out), .gpio_oe(rx_oe),
    .imem_we(rx_imem_we), .imem_waddr(rx_waddr), .imem_wdata(rx_wdata),
    .tx_we(1'b0), .tx_data(8'h00), .tx_full(rx_full),
    .rx_re(rx_re), .rx_data(rx_rxdata), .rx_empty(rx_empty), .pc(rx_pc)
  );

  reg [15:0] TXW [0:8];
  initial begin
    TXW[0] = 16'hc001;
    TXW[1] = 16'hc021;
    TXW[2] = 16'h8020;
    TXW[3] = 16'hc047;
    TXW[4] = 16'hc700;
    TXW[5] = 16'h6601;
    TXW[6] = 16'h0065;
    TXW[7] = 16'hc701;
    TXW[8] = 16'h0002;
  end

  reg [15:0] RXW [0:6];
  initial begin
    RXW[0] = 16'h2000;
    RXW[1] = 16'hea00;
    RXW[2] = 16'hc047;
    RXW[3] = 16'h4601;
    RXW[4] = 16'h0063;
    RXW[5] = 16'h8000;
    RXW[6] = 16'h0000;
  end

  reg [7:0] PAY [0:1];
  initial begin
    PAY[0] = 8'h48;
    PAY[1] = 8'h69;
  end

  integer i, ngot, src, idle, pop, lim;
  reg [7:0] got [0:2];
  initial begin
    lim = 64 + 2 * 120;
    ngot = 0; src = 0; idle = 0; pop = 0;
    repeat (4) @(posedge clk);
    rst = 0;
    for (i = 0; i < 9; i = i + 1) begin
      @(posedge clk);
      tx_imem_we = 1; tx_waddr = i[4:0]; tx_wdata = TXW[i];
    end
    @(posedge clk); tx_imem_we = 0;
    for (i = 0; i < 7; i = i + 1) begin
      @(posedge clk);
      rx_imem_we = 1; rx_waddr = i[4:0]; rx_wdata = RXW[i];
    end
    @(posedge clk); rx_imem_we = 0;
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
