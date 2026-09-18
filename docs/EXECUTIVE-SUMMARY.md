# Loom — Jane Street protocol-emulator ASIC: criteria status

Printable copy: [`loom-executive-summary.pdf`](loom-executive-summary.pdf).

**Date:** 2026-09-15. **Source:** [protocol-emulator ASIC competition](https://blog.janestreet.com/protocol-emulator-asic-competition/). **Top:** `tt_um_loom_gpe`. **Tiles:** 6×4. **Clock:** 50 MHz. **License:** Apache-2.0.

This note maps the repo to the published contest criteria. It records what was measured, what was formally proven, and what has not been run on a pin.

**Status.** The design is a reprogrammable pin/time ISA, not a hardwired UART/SPI/I2C trio. A 1-state-machine CMOS5L GDS closed at 50 MHz with Magic DRC 0 and a unique LVS match. Current source is 2 SM / 4 slots with IHP 2-port SRAM imem (`RM_IHPSG13_2P_256x16_c2_bm_bist`); that netlist has not closed GDS. Protocol graphs exist for every named contest protocol. On the interpreter, all 10 registered TX/RX pairs are exhaustive codecs for bytes 0..255 against independent spec languages. USB and CAN time bits from a helper clock on pin2. k-induction covers 1-SM ISA + CRC MOV + host CSR writes, ClockedImem, and 2-SM fetch + SM0/SM1 CSR writes. UART/SPI/I2C hello pin traces match Amaranth RTL (push-pull I2C hello graphs still exist; open-drain is the I2C formal case). Cocotb RTL wrapper loads UART TX and checks a start bit. Nothing has been run on an FPGA or a real peer device.

| Closed 1-SM GDS | 54 k-induction assertions | 10 × 256 interp codecs | FPGA / real pin |
|---|---|---|---|
| 50 MHz, DRC 0, LVS match | ISA + FIFO/halt, not protocols | All registered pairs | 0 bring-up runs |

Rebuild the PDF: `PYTHONPATH=generator python scripts/build_exec_summary.py`.

---

## 1. Contest criteria, as published

| Criterion | What this repo has | Status |
|---|---|---|
| Open-source general-purpose protocol emulator ASIC | 16-bit pin/wait/delay/shift/fifo/jump/mov ISA. Protocols are TOML graphs in `plans/`, loaded into imem after tapeout. Engine core is forbidden from naming a protocol (`loom check` prints `criteria ok: engine core names no protocol`). | Yes — as RTL/graphs |
| Not a UART+SPI+I2C block trio; new protocols after fabrication | Host two-phase imem write + TX FIFO + run (`docs/info.md`, `tests/test_host_load.py`). Same engine, new words; no resynth. | Yes — in simulation |
| Start with UART, SPI, and I2C | UART 8N1; SPI mode-0 MOSI/SCK/CS; I2C open-drain START / 8 bits / ACK / STOP. All three proven 0..255 on the interpreter. Push-pull I2C hello graphs still exist and are not the I2C formal case. | Yes — graphs + interp proof |
| Stretch: low-speed USB and 10 Mbit Ethernet | USB LS graphs encode NRZI (0=toggle, 1=hold), stuff after six 1s, SYNC KJKJKJKK, EOP SE0 on D+/D−, timed from pin2. Ethernet graphs put IEEE 802.3 MAC framing (seven `0x55` + `0xD5` SFD + payload) on clock+data. Neither is an analog PHY. | Partial — digital line language |
| Also named: JTAG, SWD, PS/2, CAN | JTAG: TMS TAP (TLR via ≥5 TMS=1, then Shift-DR). SWD: ≥50 SWDIO=1 clocks then 8 LSB. PS/2: host byte, odd parity, device ACK. CAN: SOF + both-polarity stuff through CRC-15 (`0x4599`) + ACK 0; proven 0..255 on the interpreter. Helper clock pin2. | Partial — bit-level graphs, not full stacks |
| FPGA smoke of RTL before ASIC flow | Named in the brief. Not run. | No |
| Formal methods | Yosys `sat -tempinduct`: 1-SM ISA + CRC MOV 7–11 + host CSR writes; ClockedImem; 2-SM fetch + SM0/SM1 CSR writes. Log: `Induction step proven: SUCCESS!` (`test/gen/formal.log`). Does not prove a protocol waveform on RTL. | Yes — ISA, not protocols |
| Random constrained tests | `tests/test_random_jitter.py`: UART baud error / jitter / runts; SPI clock asymmetry. Interpreter only. | Yes — UART/SPI interp |
| IHP 130 nm CMOS5L via Tiny Tapeout; CMOS5L Verilog template | `info.yaml` tiles `6x4`, `clock_hz` 50e6, `CLOCK_PERIOD` 20. `runs/wokwi` completed through GDS. | Yes |
| Area: 6×4 (~0.7 mm², ~24k cell budget) | Closed GDS (1 SM): 3,499 cells, 56,492 µm². Current 2-SM `loom_chip` uses IHP 2P SRAM for imem (stdcell count TBD on next P&R). | Yes — under budget |
| Full P&R + timing at a declared clock | 1-SM GDS: setup/hold WNS 0 @ 50 MHz; slow setup slack +8.986 ns. Magic DRC 0. LVS unique match. KLayout DRC skipped. 8 max-slew / 37 max-fanout at slow corner. 2-SM P&R stopped in detailed routing; no GDS. | Yes — 1-SM GDS only |
| Open source | Apache-2.0. Remote: `github.com/wsb1994/Gremlin-Board`. | Yes |
| Sign-up / submit by 2027-01-18 | Neither form is in the repo. | Open |

---

## 2. Closed GDS versus current source

`emit.py` writes two engines into `src/loom_engine.v`: `loom_engine` (1 SM, 1 slot) and `loom_chip` (2 SM, 4 slots).

| | Closed GDS (`runs/wokwi`, `tt_submission`) | Current `src/project.v` |
|---|---|---|
| Instantiates | `loom_engine` | `loom_chip` |
| SMs / slots | 1 SM, 1×32-word imem | 2 SM, 4×32-word imem |
| Cells / FFs | 3,499 / 623 | synth 14,944 / 2,412 |
| Area | 56,492 µm² (~8% of 6×4) | 233,174 µm² (still under 6×4) |
| DRC / LVS / 50 MHz | Magic DRC 0, LVS unique match, slack +8.99 ns | no GDS; P&R stopped in detailed route |

k-induction, iverilog protocol tests, and the exhaustive ISA sweep all target `GraphEngine()` / `loom_engine`. Dual-SM is `tests/test_dual_sm.py` only.

---

## 3. Named protocols: what the graphs are

Assembled length is `compile_plan` word count / 32. “Full protocol?” is relative to the named standard, not to a byte round-trip.

| Protocol | Graphs (words) | What the graph actually does | Full protocol? |
|---|---|---|---|
| UART | `uart_tx/rx` 9/8, `uart_8n1_*` 9/15, `uart_rx_frame` 15 | 8N1 on pin0, LSB, 8 SM-cycles/bit. Production RX: centre sample, start verify, stop check. | Yes — 8N1 byte |
| SPI | `spi_tx` 11, `spi_rx` 8 | Mode 0, MOSI=pin0, SCK=pin1, CS=pin2 active-low, MSB. | Partial — mode-0 byte with CS |
| I2C hello | `i2c_tx` 15, `i2c_rx` 9 | Push-pull bit dance. Not the formal I2C case. | No — cartoon |
| I2C open-drain | `i2c_od_tx` 22, `i2c_od_rx` 12 | Drive-0 via OE, START, 8 MSB, ACK 0, STOP. Golden slave is in `tests/test_i2c_opendrain.py`. | Partial — 1-byte master write |
| JTAG | `jtag_tx` 31, `jtag_shift` 15 | TMS TAP: ≥5 TMS=1 (TLR), then Shift-DR, 8 TDI LSB, Update-DR. | Partial — 8-bit Shift-DR, not IDCODE |
| SWD | `swd_tx` 16, `swd_rx` 10 | ≥50 clocks with SWDIO=1, then 8 LSB on SWCLK. | Partial — line-reset + byte, not DPIDR |
| PS/2 | `ps2_tx` 29, `ps2_rx` 14 | Host-clocked byte: start, 8 LSB, odd parity, stop, ACK 0. | Partial — host byte, not a keyboard host |
| CAN | `can_tx` 32, `can_rx` 32 | TX: SOF, 8 LSB, both-polarity stuff through CRC-15 (`0x4599`), ACK 0, one clocked recessive; parks on pull. RX: destuff 5 identical of either polarity, then wait TX pin4 (CRC-phase) before the next SOF. Helper clock pin2. | Partial — stuffed 1-byte data frame, not a CAN node |
| USB LS | `usb_tx` 32, `usb_rx` 32 | NRZI (0=toggle, 1=hold), stuff after six 1s, SYNC KJKJKJKK, EOP SE0 on D+/D−. RX samples D+ against previous level on pin3. Helper bit-clock pin2 (not a USB wire). | Partial — NRZI packet, not analog PHY |
| 10 Mbit Ethernet | `eth_tx` 32, `eth_rx` 13 | Seven `0x55` + `0xD5` SFD + payload on data+clock. Plan text: not 10BASE-T magnetics. | Partial — 802.3 framing, not 10BASE-T |

---

## 4. Was each path formally proven?

Two different claims. They are not interchangeable.

**1. ISA k-induction (RTL, protocol-agnostic).** `generator/loom/formal.py`. Yosys `sat -tempinduct`, 54 named assertions: FIFO occupancy, halt freezes the SM, run blocks imem writes, one-step semantics of all 8 opcodes. MOV assertions cover payload ≤ 6 (including dest ^= Y). MOV payloads 7–11 (hidden 15-bit CRC, poly `0x4599`) are unconstrained in that proof. Log: `Induction step proven: SUCCESS!` (`test/gen/formal.log`). Harness is `GraphEngine()` default: 1 SM, 1 slot, clkdiv=1, wrap 0..31, sideset off. It does not mention UART, SPI, or I2C. It does not prove a protocol waveform.

**2. Protocol completeness (interpreter, finite alphabet).** `generator/loom/formal_proto.py` (`loom formal-proto`). For each registered TX/RX pair and every byte `b` in 0..255: TX(`b`) ∈ L; RX(spec(`b`))=`b`; RX(TX(`b`))=`b`; SM returns to pull. Spec waves come from `generator/loom/line_lang.py` (`SPECS`), not from the TX graph. That is exhaustive model checking of an 8-bit FIFO engine **on the interpreter**, not k-induction of RTL.

Measured this session (all 256 bytes unless noted):

| Path | Exhaustive 0..255 interp | Amaranth RTL pins | Interpreter `Hi` | k-ind of this waveform |
|---|---|---|---|---|
| uart_tx / uart_rx | Yes | Yes (Hi trace) | Yes (165 cycles) | No |
| uart_8n1_tx / uart_8n1_rx | Yes | No | (not in PAIRS; codec 0..255) | No |
| spi_tx / spi_rx | Yes | Yes (Hi trace; graphs now include CS) | Yes (76 cycles) | No |
| i2c_tx / i2c_rx (push-pull) | No — not the formal case | Yes (Hi trace) | not the PAIRS pair | No |
| i2c_od_tx / i2c_od_rx | Yes | No | Yes (142 cycles) | No |
| jtag_tx / jtag_shift | Yes | No | Yes (164 cycles) | No |
| swd_tx / swd_rx | Yes | No | Yes (385 cycles) | No |
| ps2_tx / ps2_rx | Yes | No | Yes (166 cycles) | No |
| can_tx / can_rx | Yes vs `can_spec_wave` | No | Yes (640 cycles) | No |
| usb_tx / usb_rx | Yes vs `usb_spec_wave` | No | Yes (566 cycles) | No |
| eth_tx / eth_rx | Yes vs `eth_spec_wave` | No | Yes (554 cycles) | No |
| ISA step (all 8 opcodes) | n/a | golden snapshots | 2048 encodings × 7 stimuli (iverilog test exists) | Yes — 1 SM |

**Composition (stated as a composition, not as a solver run).** If RTL implements the ISA (k-induction, 1 SM, default CSRs) and a graph is a codec on the interpreter (all 256 bytes), then RTL executing that graph is a codec under those CSR defaults. That argument is written in `formal_proto.py`. It has not been discharged as one formal property. USB and CAN helper-clock graphs also sit outside the k-induction wrap 0..31 / clkdiv=1 defaults only in the sense that the **waveform** was never proven on RTL; the ISA step still applies.

| Other verification the brief named | Where | Result |
|---|---|---|
| Constrained-random UART/SPI pins | `tests/test_random_jitter.py` | Yes — those graphs |
| ASCII waveform expects | `tests/expect/uart_hi.txt`, `spi_hi.txt` | Yes — UART/SPI hello |
| I2C open-drain ACK + stretch | `tests/test_i2c_opendrain.py` vs software slave | Yes — model only |
| Host load two-phase imem + FIFO | `tests/test_host_load.py` | Yes — simulation |
| Gate-level cocotb | `test/test.py` | Partial — idle only (`run=0`) |
| iverilog Hi on `loom_engine` | `tests/test_verilog_sim.py` (every PAIRS name) | Test exists; not re-run this session after USB/CAN/I2C-OD graphs. TB ties `gpio_in` to `gpio_out` (no pull-up / OE). |
| Non-default clkdiv/wrap/sideset in k-induction | `formal.py` comments | No |
| 2-SM / 4-slot in k-induction or GDS | harness / GDS are 1 SM | No |

---

## 5. Is the simulator usable in a real scenario?

The interpreter is a cycle-accurate digital ISA simulator. Amaranth and iverilog are digital RTL copies. None of them model pads, cables, analog PHYs, or a real peer device. RTL 2-flop-synchronises GPIO inputs while running; the interpreter does not. `loom.stream.roundtrip` uses a wired-AND pull-up so open-drain ACK (I2C, PS/2) can work in that helper; a raw pin does not.

**What it is usable for.** Authoring a graph, checking that a TX/RX pair recovers every byte 0..255 against an independent spec language, locking an ASCII pin trace, and comparing interpreter vs Amaranth vs iverilog before tapeout. That is a real use in a design flow. It is not a protocol analyser, not a stand-in for an FPGA board, and not evidence that a USB-UART, SPI flash, I2C EEPROM, JTAG TAP, SWD target, PS/2 keyboard, USB device, 10BASE-T PHY, or CAN node would lock.

At 50 MHz with 8 SM-cycles/bit, clkdiv=1 is a 6.25 Mbit/s class line; 115200 8N1 is inside the divider range (clkdiv ≈ 54). That is a cycle-budget fact, not a bring-up result.

| Desk scenario | Graph | Simulator evidence | Usable on a real pin today? |
|---|---|---|---|
| UART 115200 8N1 to a USB-UART | `uart_8n1_*` | Codec 0..255; jitter/runt tests. RTL pin match is the hello pair, not 8n1. | No — never driven off-chip |
| SPI mode-0 flash JEDEC ID | `spi_tx/rx` | Byte codec 0..255 with CS. No flash model in the formal suite. | No — no flash |
| I2C EEPROM read, addr 0x50 | `i2c_od_*` | Codec 0..255; master write 0xA0 then 0x48 with ACK/stretch vs a software slave. | No — model only |
| JTAG TAP IDCODE | `jtag_*` | 8-bit Shift-DR after TLR. A 32-bit IDCODE sequence is not the graph. | No — cannot IDCODE |
| SWD line reset + DPIDR | `swd_*` | Line-reset + 8 data bits. No DPIDR parse. | No — cannot DPIDR |
| PS/2 keyboard byte | `ps2_*` | Host byte with odd parity and ACK on the interpreter. | No — never a keyboard |
| Low-speed USB | `usb_*` | NRZI+stuff+SYNC+EOP codec 0..255 on interp. RX/TX use pin2 as a bit-clock a USB cable does not carry. No analog PHY. | No — not a USB PHY; extra clock pin |
| 10BASE-T Ethernet | `eth_*` | Preamble/SFD/payload codec 0..255 on clock+data. Not Manchester, not magnetics. | No — not 10BASE-T |
| CAN 2.0 at 125 kbit | `can_*` | Stuffed CRC-15 codec 0..255 on interp; `Hi` and PNG SHA-256 round-trip. Helper clock pin2. No analog PHY, no arbitration. | No — not a CAN transceiver |
| Reprogram after fab | any pair | Interpreter reprogram test; host-load Amaranth test. | No — no board |

After fabrication of the closed 1-SM GDS, a host could in principle load `uart_8n1` or `spi` or `i2c_od` and bit-bang those byte-level contracts on 8 GPIO, at rates the 50 MHz divider can hit. That is an architectural claim plus simulation. It has not been demonstrated.

---

## 6. Remaining contest items

| Item | Why it is still open |
|---|---|
| Sign-up form | Required for the submission link. |
| Submit by 2027-01-18 | Nothing submitted. |
| FPGA smoke of UART Hi on a pin | Named in the brief. No board log. |
| P&R / GDS of the 2-SM / 4-slot netlist | Synth fits 6×4; stopped in detailed routing. |
| KLayout DRC | Skipped on the closed 1-SM run. Magic DRC was 0. |
| Gate-level UART Hi | cocotb presently asserts only `run=0` after reset. |
| k-induction of `loom_chip`, clkdiv, wrap, sideset, CRC MOV | Harness is 1-SM defaults; CRC MOV unconstrained. |
| End-to-end formal of a protocol waveform on RTL | Not done for any named protocol. |
| CAN analog PHY / multi-node arbitration | Interpreter codec is a 1-byte stuffed data frame on GPIO+clock. |
| Desk tests (USB-UART, W25, EEPROM, TAP, DPIDR) | Simulation and models only. |
| 8×4 tile | CMOS5L tooling in this tree defines 6×4. |

**Bottom line against the brief.** Architecture matches: a PIO-class reprogrammable pin/time engine, open source, on the CMOS5L 6×4 template, with a timing-closed 1-SM GDS. UART, SPI (mode-0 with CS), and open-drain I2C graphs exist and are exhaustive codecs on the interpreter. Stretch USB and Ethernet are digital line languages (NRZI packet; 802.3 framing on clock+data), not analog PHYs, and those codecs are proven 0..255 on the interpreter. JTAG/SWD/PS/2/CAN graphs implement the named bit-level mechanics in 32 words and are proven the same way. Formal methods were applied to the ISA, not to each protocol path on RTL. The simulator is usable as a graph lab. It is not evidence of a real-desk protocol emulator until a pin test exists.
