# Loom

Agent-programmable pin/time engine for the Jane Street protocol-emulator ASIC contest (Tiny Tapeout CMOS5L, 8×4 tiles).

Protocols are graphs in `plans/`. The silicon is one ISA: pin, wait, delay, shift, fifo, jump. Load a new graph after tapeout; do not resynth.

This is a contest tapeout candidate, not a trading NIC. USB/Ethernet/CAN graphs are bit-layer subsets (see plan descriptions). 50 MHz is a target, not a closed STA result.

## Install

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Use

```
make check          # engine core names no protocol
make test           # interpreter + Amaranth (skip iverilog)
make emit           # src/loom_engine.v + src/project.v
make synth          # generic Yosys area → estimates/synth.txt
make test-verilog   # iverilog on generated RTL (Docker if needed)
```

Or: `.venv/bin/python -m loom emit|check|plans|synth`

Load a graph onto the chip: `docs/info.md` (two-phase imem write, TX push, run).

## What is proven

- UART, SPI, I2C, JTAG, SWD, PS/2, CAN, USB, eth: `Hi` round-trip in interpreter and iverilog
- Open-drain I2C + ACK + stretch: `tests/test_i2c_opendrain.py`
- Interp ≡ Amaranth RTL for UART/SPI/I2C traces and ISA opcodes
- Host load sequence tested
- Generic synth ~2.3k cells (under 8×4 budget). No CMOS5L P&R/GDS in this tree.

## Layout

```
plans/           graphs (the “firmware”)
generator/loom/  IR, ISA, compiler, interpreter, Amaranth, emit
src/             generated Verilog + TT wrapper
tests/           product tests
docs/info.md     datasheet / host protocol
docs/CRITERIA.md contest gaps
```

## Not done

LibreLane + IHP PDK, closed timing, FPGA smoke, public repo / contest sign-up.
