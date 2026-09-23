# Sample testbench for a Tiny Tapeout project

This is a sample testbench for a Tiny Tapeout project. It uses [cocotb](https://docs.cocotb.org/en/stable/) to drive the DUT and check the outputs.
See below to get started or for more information, check the [website](https://tinytapeout.com/hdl/testing/).

## Setting up

1. Edit [Makefile](Makefile) and modify `PROJECT_SOURCES` to point to your Verilog files.
2. Edit [tb.v](tb.v) and replace `tt_um_example` with your module name.

## How to run

To run the RTL simulation:

```sh
make -B
```

To run gatelevel simulation, first harden your project and copy `../tt_submission/tt_um_loom_gpe.v` (CI artifact) or `../runs/wokwi/results/final/verilog/gl/tt_um_loom_gpe.v` to `gate_level_netlist.v`.

Then run:

```sh
make -B GATES=yes
```

Without make (e.g. inside the LibreLane image, which has iverilog but no make):

```sh
pip install cocotb
python3 run_cocotb.py                        # RTL
GATES=yes PDK_ROOT=/path/to/pdk python3 run_cocotb.py   # gate level
```

`test.py` has two tests: `test_project` (reset, ena, SET_BIT, UART start bit) and `test_uart_loopback` (SM0 `uart_tx` → pin0 → SM1 `uart_rx` → host RX pop of `Hi`, plus a bench-side 8N1 decode of pin0).

If you wish to save the waveform in VCD format instead of FST format, edit tb.v to use `$dumpfile("tb.vcd");` and then run:

```sh
make -B FST=
```

This will generate `tb.vcd` instead of `tb.fst`.

## How to view the waveform file

Using GTKWave

```sh
gtkwave tb.fst tb.gtkw
```

Using Surfer

```sh
surfer tb.fst
```
