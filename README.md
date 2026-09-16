# Loom

A reprogrammable pin/time engine for the [Jane Street protocol-emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/), targeting Tiny Tapeout on IHP CMOS5L (6×4 tiles, 50 MHz).

The silicon implements one small ISA: `pin`, `wait`, `delay`, `shift`, `fifo`, `jump`, `mov`. Protocols are not hardwired blocks. They are graphs (`plans/*.toml`) compiled to 32-word programs and written into instruction memory over the Tiny Tapeout pins after tapeout. The die holds four 32-word graph slots and two state machines.

Everything below is stated as tested, simulated, synthesised, or not done. Nothing here has run on silicon or on an FPGA.

## Status at a glance

| Item | State |
|---|---|
| GDS on CMOS5L, 6×4, current source (`loom_chip`, 2 SM, 4 slots) | Closed in CI at commit `f552ddc`: 23,057 std cells, 36% utilisation, Magic DRC 0, LVS clean, antenna 0. Tiny Tapeout precheck and gate-level test pass. |
| Timing at 50 MHz | Setup worst slack **+0.18 ns** at the slow corner (1.08 V, 125 °C), +7.47 ns typical, +10.2 ns fast. Hold +0.13 ns. 77 max-slew and 179 max-fanout warnings at the slow corner. The margin is thin. |
| Protocol graphs | UART (hello + 8N1), SPI mode 0 + CS, I2C open-drain, JTAG TMS TAP, SWD, PS/2, CAN, USB low-speed, Ethernet framing. All fit in 32 words. |
| Exhaustive protocol check | Every byte 0..255 on all 10 TX/RX pairs, on the Python interpreter, against independent spec languages (`loom formal-proto`). |
| ISA formal | k-induction (yosys `sat -tempinduct`, 12 steps) over 54 named assertions on the 1-SM `loom_engine` RTL. Passes. |
| Interpreter vs generated Verilog | All 2048 ISA encodings × 7 stimuli under iverilog. Passes. |
| Gate-level | Tiny Tapeout `gl_test` on the CI netlist checks reset and idle status only. No protocol traffic is simulated at gate level. |
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
- **ISA k-induction (RTL):** one-step semantics of all 8 opcodes plus FIFO occupancy, halt freezes the SM, run blocks imem writes. Harness is `loom_engine` with default CSRs (1 SM, clkdiv 1, wrap 0..31, no sideset). MOV payloads 7–11 (the CRC helper) are not constrained by the proof. `generator/loom/formal.py`, log in `test/gen/formal.log`.
- **Interpreter ≡ Verilog:** every ISA encoding, golden from the interpreter, checked on `src/loom_engine.v` under iverilog. `tests/test_verilog_isa_exhaustive.py`.
- **Interpreter ≡ Amaranth RTL:** UART/SPI/I2C hello traces and opcode tests. `tests/test_rtl.py`, `tests/test_rtl_stream.py`, `tests/test_prod_engine.py`, `tests/test_dual_sm.py`.
- **Verilog protocol round-trips:** every pair sends `Hi` through the generated Verilog under iverilog; UART/SPI/I2C also carry three longer payloads. `tests/test_verilog_sim.py`.
- **Constrained random (interpreter):** UART baud error, edge jitter, gaps, glitches, runt starts, bad stop bits; SPI clock asymmetry. `tests/test_random_jitter.py`, `tests/test_uart10.py`, `tests/test_random_pins.py`.
- **Binary payload streaming (interpreter):** a 152,721-byte PNG (`tests/fixtures/big_chungus.png`) is streamed byte-by-byte through each of the 10 TX/RX pairs and compared byte-for-byte to the input. `tests/test_png_sha256.py`. This exercises back-to-back bytes, FIFO backpressure and long runs of identical bits (stuffing on CAN and USB). It is the same interpreter as the 256-byte exhaustive check, not the RTL. These ten cases take about 12 minutes of `make test`.
- **Host load:** two-phase imem write, TX push, run, on the engine ports and a cycle model of the wrapper. `tests/test_host_load.py`.
- **ASCII waveform expect tests:** `tests/test_timing_infra.py`, `tests/expect/`.

Not verified: any protocol waveform on the gate-level netlist, any transfer against a real peer device, the 2-SM `loom_chip` under k-induction (the proof covers the 1-SM engine it instantiates).

## Area and timing

Numbers from the CI GDS run on commit `f552ddc` (`tt_submission` artifact, `stats/metrics.csv`):

| Metric | Value |
|---|---|
| Std cells | 23,057 |
| Std cell area | 325,609 µm² of 902,417 µm² core (36%) |
| Setup slack, slow / typ / fast | +0.18 / +7.47 / +10.2 ns |
| Hold slack, worst | +0.13 ns |
| Magic DRC / LVS / antenna | 0 / clean / 0 |

`estimates/synth.txt` is a generic Yosys estimate from an earlier revision and is not the number above. Instruction memory is standard-cell flip-flops; an SRAM plan is in `docs/SRAM-IMEM-PLAN.md` and is not implemented.

## Install and run

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

```
make check            # engine core names no protocol
make test             # 390 interpreter + Amaranth tests, all passing at f552ddc (~15 min)
make emit             # regenerate src/loom_engine.v + src/project.v
make test-verilog     # iverilog round-trips on generated RTL
make test-exhaustive  # all ISA encodings, interpreter vs Verilog
make formal           # k-induction on the ISA (yosys sat)
make formal-proto     # all 256 bytes x every protocol pair
make verify           # test-verilog + test-exhaustive + formal
```

iverilog and a full yosys are taken from the LibreLane image `ghcr.io/librelane/librelane:3.1.0.dev3` through Docker when they are not on PATH.

CI (`.github/workflows`): `loom.yml` runs `loom check`, the interpreter suite, the exhaustive ISA golden and the k-induction proof. `gds.yaml` hardens on CMOS5L and runs precheck and the gate-level test. `test.yaml` runs the cocotb wrapper test.

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
- Protocol traffic on the gate-level netlist.
- Any test against real hardware.
- Timing margin at the slow corner is 0.18 ns; no retiming or clock-period relaxation has been attempted.

License: Apache-2.0.
