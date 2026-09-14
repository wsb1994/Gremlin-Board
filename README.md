# Loom

Agent-programmable pin/time engine for the Jane Street protocol-emulator ASIC contest (Tiny Tapeout CMOS5L, 6×4 tiles).

Protocols are graphs in `plans/`. The silicon is one ISA: pin, wait, delay, shift, fifo, jump. Load a new graph after tapeout; do not resynth.

This is a contest tapeout candidate, not a trading NIC. USB/Ethernet/CAN graphs are bit-layer subsets (see plan descriptions). 50 MHz closes on CMOS5L (LibreLane, slow corner setup slack +9.0 ns).

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
make test-exhaustive # all 2048 ISA encodings x 7 stimuli: interp vs emitted Verilog
make formal         # k-induction proof: ISA step semantics + FIFO/halt invariants
make verify         # the three above
```

Or: `.venv/bin/python -m loom emit|check|plans|synth`

Load a graph onto the chip: `docs/info.md` (two-phase imem write, TX push, run).

## What is proven

- UART, SPI, I2C, JTAG, SWD, PS/2, CAN, USB, eth: `Hi` round-trip in interpreter and iverilog
- Open-drain I2C + ACK + stretch: `tests/test_i2c_opendrain.py`
- Constrained-random pins (baud error, edge jitter, gaps, glitches, SPI clock asymmetry): `tests/test_random_jitter.py`; `plans/uart_rx_frame.toml` rejects runt starts and flags bad stop bits on pin1
- Exhaustive ISA golden, interp vs emitted Verilog, every encoding: `tests/test_verilog_isa_exhaustive.py`
- Formal (k-induction, yosys `sat`): 129 assertions, one-step semantics of all 8 opcodes plus FIFO/halt/imem invariants: `generator/loom/formal.py`
- Interp ≡ Amaranth RTL for UART/SPI/I2C traces and ISA opcodes
- Host load sequence tested
- Generic synth ~2.3k cells (under 6×4 budget). No CMOS5L P&R/GDS in this tree.

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

FPGA smoke, contest sign-up, 8x4 tile once Tiny Tapeout's CMOS5L tooling defines it (6x4 today).
