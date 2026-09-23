# Loom

A reprogrammable pin/time engine for the [Jane Street protocol-emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/), targeting Tiny Tapeout on IHP CMOS5L (6×4 tiles, 50 MHz).

The silicon implements one small ISA: `pin`, `wait`, `delay`, `shift`, `fifo`, `jump`, `mov`. Protocols are not hardwired blocks. They are graphs (`plans/*.toml`) compiled to 32-word programs and written into instruction memory over the Tiny Tapeout pins after tapeout. The die holds four 32-word graph slots and two state machines, each with its own FIFO. Host can refill TX / pop RX while GPIO is live (nibble path on `ui_in`).

Everything below is stated as tested, simulated, synthesised, or not done. Nothing here has run on silicon or on an FPGA.

## Status at a glance

| Item | State |
|---|---|
| GDS on CMOS5L, 6×4 | Closed **2-SM / 4-slot** GDS (`tt_submission`, CI run on `d69796a`): 5,086 std cells + IHP `RM_IHPSG13_2P_256x16_c2_bm_bist` SRAM macro, 14.3% util, Magic DRC 0, LVS clean, antenna 0, slow setup **+7.46 ns**. This is the current `src/project.v` (`loom_chip`). Python tests keep a 1-cycle Array model of the SRAM. |
| Timing at 50 MHz | Closed 2-SM part: setup slack slow/typ/fast +7.46 / +10.14 / +10.69 ns, worst hold +0.11 ns. 2-SM fetch is registered (`next_pc` ADDR). `clkdiv=0` is a 65536-cycle period. |
| Protocol graphs | UART (hello + 8N1), SPI mode 0 + CS, I2C open-drain, JTAG TMS TAP, SWD, PS/2, CAN, USB low-speed, Ethernet framing. All fit in 32 words. |
| Exhaustive protocol check | Every byte 0..255 on all 10 TX/RX pairs, on the Python interpreter, against independent spec languages (`loom formal-proto`). |
| ISA formal | k-induction (yosys `sat -tempinduct`, 12 steps) on 1-SM ISA + CRC MOV 7–11 + host CSR writes; ClockedImem contract; 2-SM fetch + SM0/SM1 CSR writes. Passes. |
| Interpreter vs generated Verilog | All 2048 ISA encodings × 7 stimuli under iverilog. Passes. |
| Gate-level | Tiny Tapeout `gl_test` on the hardened netlist runs `test/test.py`: reset/idle status, SET_BIT, and a full UART round-trip. SM0 encodes `Hi` on pin0 from the UART TX graph, the bench loops pin0 back with a pull-up, SM1 decodes it with the UART RX graph in slot 1, and the host pops `Hi` from SM1's RX FIFO. The bench also decodes the pin0 waveform as 8N1 independently. Passes on the `d69796a` netlist. |
| FPGA / hardware | Not done. |
| Contest sign-up and submission | Not done. Deadline 2027-01-18. |

## What the protocol graphs are, and are not

Each graph is a byte-level line codec, not a full standard. USB, CAN and Ethernet are digital line codecs driven from a helper clock on a GPIO pin, not analog PHYs.

| Protocol | Graph does | Does not |
|---|---|---|
| UART | 8N1, LSB first. Production RX centre-samples, verifies start, checks stop, flags framing error. | — |
| SPI | Mode 0, MOSI/SCK/CS active-low, MSB first. | Other modes, MISO read-back |
| I2C | Open-drain via OE, START, 8 bits, ACK, STOP, clock stretch on `wait_pin`. Golden slave that NACKs and stretches. | Multi-byte transfers, addressing, arbitration |
| JTAG | ≥5 TMS=1 to Test-Logic-Reset, Shift-DR, 8 TDI bits, Update-DR. | IDCODE read, IR scan |
| SWD | ≥50-clock line reset then 8 bits on SWCLK. | DPIDR, packet/ACK/turnaround |
| PS/2 | Host-clocked byte with odd parity, stop, ACK. | Keyboard host state machine |
| CAN | SOF, 8 data bits, bit stuffing across CRC-15 (0x4599), ACK slot. RX destuffs. | Arbitration, IDs, full frame, error handling |
| USB LS | NRZI, stuff after six 1s, SYNC, EOP SE0 on D+/D−. | Analog PHY, packets, CRC-5/16 |
| Ethernet | Seven 0x55 preamble, 0xD5 SFD, payload on clock+data. | 10BASE-T magnetics, MAC CRC |

## What is verified, and where

- **Protocol completeness (interpreter):** for each of the 10 pairs and every byte `b`: TX(`b`) is in the spec language, RX(spec(`b`)) = `b`, RX(TX(`b`)) = `b`, and the state machine returns to its pull. `generator/loom/formal_proto.py`, `tests/test_formal_proto.py`. This is exhaustive model checking of a finite alphabet on the interpreter. It is not a proof about the RTL.
- **ISA k-induction (RTL):** one-step semantics of all 8 opcodes plus FIFO occupancy, halt freezes the SM, run blocks imem writes, CRC MOV 7–11, host CSR writes (`csr_we` is a free input). Separate harnesses prove ClockedImem DOUT and 2-SM `next_pc` fetch plus SM0/SM1 CSR writes. `generator/loom/formal.py`, log in `test/gen/formal.log`.
- **Interpreter ≡ Verilog:** every ISA encoding, golden from the interpreter, checked on `src/loom_engine.v` under iverilog. `tests/test_verilog_isa_exhaustive.py`.
- **Interpreter ≡ Amaranth RTL:** UART/SPI/I2C hello traces and opcode tests. `tests/test_rtl.py`, `tests/test_rtl_stream.py`, `tests/test_prod_engine.py`, `tests/test_dual_sm.py`.
- **Verilog protocol round-trips:** every pair sends `Hi` through the generated Verilog under iverilog; UART/SPI/I2C also carry three longer payloads. `tests/test_verilog_sim.py`.
- **Constrained random (interpreter):** UART baud error, edge jitter, gaps, glitches, runt starts, bad stop bits; SPI clock asymmetry. `tests/test_random_jitter.py`, `tests/test_uart10.py`, `tests/test_random_pins.py`.
- **Binary payload streaming (interpreter):** a 152,721-byte PNG (`tests/fixtures/big_chungus.png`) is streamed byte-by-byte through each of the 10 TX/RX pairs and compared byte-for-byte to the input. `tests/test_png_sha256.py`. This exercises back-to-back bytes, FIFO backpressure and long runs of identical bits (stuffing on CAN and USB). It is the same interpreter as the 256-byte exhaustive check, not the RTL. These ten cases take about 12 minutes of `make test`.
- **Host load:** two-phase imem write, TX push, run, on the engine ports and a cycle model of the wrapper. `tests/test_host_load.py`.
- **ASCII waveform expect tests:** `tests/test_timing_infra.py`, `tests/expect/`.

Not verified: any transfer against a real peer device, FPGA bring-up. Gate-level protocol traffic is UART only (`test/test.py`); the other graphs are checked on RTL under iverilog.

## Area and timing

Numbers from the CI GDS run on commit `d69796a` (`tt_submission` artifact, `stats/metrics.csv`, 2 SM / 4 slots / IHP SRAM):

| Metric | Value |
|---|---|
| Std cells | 5,086 (+ 1 SRAM macro) |
| Std cell area | 71,469 µm²; macro 57,521 µm²; 14.3% of the 6×4 core |
| Setup slack, slow / typ / fast | +7.46 / +10.14 / +10.69 ns |
| Hold slack, worst | +0.11 ns (fast corner) |
| Magic DRC / LVS / antenna / route DRC | 0 / clean / 0 / 0 |
| Slew / fanout / cap violations (slow corner) | 10 / 41 / 8 (non-blocking; precheck passes) |

`estimates/synth.txt` is a generic Yosys estimate from an earlier revision and is not a P&R number. `loom_chip` instantiates IHP `RM_IHPSG13_2P_256x16_c2_bm_bist` (`src/macros/`, `docs/SRAM-IMEM-PLAN.md`); the PDN straps the macro on Metal4 (`src/pdn_cfg.tcl`). The earlier 1-SM GDS (3,499 cells, +8.99 ns) is superseded.

## Install and run

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

```
make check            # engine core names no protocol
make test             # 390 interpreter + Amaranth tests (~15 min)
make emit             # regenerate src/loom_engine.v + src/project.v
make test-verilog     # iverilog round-trips on generated RTL
make test-exhaustive  # all ISA encodings, interpreter vs Verilog
make formal           # k-induction on the ISA (yosys sat)
make formal-proto     # all 256 bytes x every protocol pair
make verify           # test-verilog + test-exhaustive + formal
```

iverilog and a full yosys are taken from the LibreLane image `ghcr.io/librelane/librelane:3.1.0.dev3` through Docker when they are not on PATH.

CI (`.github/workflows`): `loom.yml` runs `loom check`, the interpreter suite, the exhaustive ISA golden and the k-induction proof. `gds.yaml` hardens on CMOS5L and runs precheck and the gate-level test. `test.yaml` runs the cocotb wrapper test on RTL.

Gate-level locally: copy `tt_submission/tt_um_loom_gpe.v` to `test/gate_level_netlist.v`, then `GATES=yes PDK_ROOT=<pdk> python3 test/run_cocotb.py` (or `make -B GATES=yes` in `test/`). `run_cocotb.py` needs no `make`, so it runs inside the LibreLane image.

Loading a graph onto the chip: `docs/info.md` (pinout, two-phase imem write, TX push, RX pop, CSRs).

## Layout

```
plans/             protocol graphs (TOML)
generator/loom/    IR, ISA, compiler, interpreter, Amaranth RTL, emit, formal
src/               generated Verilog + Tiny Tapeout wrapper
tests/             pytest suite
test/              Tiny Tapeout cocotb wrapper test
docs/info.md       datasheet and host protocol
docs/EXECUTIVE-SUMMARY.md  criteria mapping
docs/CRITERIA.md   contest checklist
```

## Not done

- Contest sign-up form and submission.
- FPGA smoke test.
- Gate-level traffic for protocols other than UART.
- Any test against real hardware.

License: Apache-2.0.
