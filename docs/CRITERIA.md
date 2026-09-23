# Remaining work: contest criteria + infra tests

Status 2026-09-23: digital criteria 2–8, 10, 11, 13, 14 and T1–T8 **in simulation** are filled. 2-SM+SRAM GDS closed in CI (`d69796a`). Open: 1 sign-up, 9 submit, 12 FPGA (skipped), analog PHYs (out of scope).

Goal of this chip: easiest agent-programmable pin/time engine. Not a Jane Street stack clone. Not a matching-engine NIC.

## Already met (sim / RTL / gate-level / 2-SM GDS)

- Reprogrammable graph ISA (pins, wait, delay, shift, jump, fifo, mov). Protocols are graphs, not blocks. `loom check` forbids protocol names in the engine core.
- CMOS5L template, `info.yaml` tiles `6x4`, top `tt_um_loom_gpe`. Closed 2-SM / 4-slot / SRAM GDS: 5,086 std cells + macro, 14.3% util, Magic DRC 0, LVS clean, antenna 0, slow setup +7.46 ns @ 50 MHz, hold +0.11 ns.
- Current source (= closed GDS): 2 SM / 4 slots, per-SM FIFOs, live nibble FIFO while GPIO is live, IHP 2P SRAM instance on `loom_chip`.
- Gate-level UART round-trip on the hardened netlist: SM0 `uart_tx` on pin0, external loopback, SM1 `uart_rx` in slot 1, host pops `Hi` (`test/test.py`, CI `gl_test`).
- UART / SPI / I2C / JTAG / SWD / PS/2 / CAN / USB-LS-codec / ETH-framing encode+decode in interpreter; UART/SPI/I2C also Amaranth + iverilog.
- Host load: two-phase imem, halt byte TX, live nibble TX, RX pop (`docs/info.md`, `tests/test_host_load.py`).
- Formal: k-induction ISA + CRC MOV + CSR writes (1-SM and 2-SM), ClockedImem, 2-SM fetch. Protocol completeness 10×256 on the interpreter.
- Constrained-random UART/SPI pin tests. PNG SHA-256 round-trip on all 10 pairs.

## Must complete to be a valid submission

1. Sign-up form on the contest page (not a commit).
2. Publish the repo — done if remote is public.
3. Host load — done.
4. Fourth protocol with zero RTL change — JTAG/SWD/PS2/CAN/USB/ETH graphs. Done.
5. Real I2C open-drain — done (`i2c_od_*`, ACK, stretch).
6. Synthesis on CMOS5L 6×4 — 2-SM + SRAM GDS under budget (14.3%). Done.
7. Full P&R + timing — 2-SM + SRAM GDS closed at 50 MHz. Gate-level UART `Hi` round-trip on the submitted netlist passes (`test/test.py`). Done.
8. `docs/info.md` + README — done.
9. Submit by 2027-01-18 through their form.

## Should complete (they asked for these by name)

10. Constrained-random pin tests — done.
11. Formal ISA k-induction — done (plus CSR writes, CRC, 2-SM fetch).
12. FPGA smoke — skipped (Verilog app; not this pass).
13. Second SM — in source (`loom_chip`). Dual-SM UART+SPI on disjoint pins: `tests/test_infra_desk.py` T7.
14. Stretch graphs are **bit-layer codecs** (USB NRZI+stuff, CAN stuffed CRC-15, ETH preamble/SFD). Not analog PHYs.

## Desk-infra tests (simulation)

| # | Test | Where | Pass |
|---|------|--------|------|
| T1 | UART 8N1 `Hi` + 115200 clkdiv formula | `test_infra_desk.py` | interp |
| T2 | SPI JEDEC `0x9F` + 3 bytes, CS held | `spi_burst_*` | interp |
| T3 | I2C OD 0xA0 + 16 EEPROM-style bytes | `i2c_od_*` | interp |
| T4 | JTAG 32-bit IDCODE as four Shift-DR bytes | `jtag_tx` / `jtag_shift` | interp |
| T5 | SWD 32-bit DPIDR as four bytes after line reset | `swd_*` | interp |
| T6 | UART start+zeros bit width within 2% | `test_infra_desk.py` | interp |
| T7 | Dual-SM: UART 8N1 pin0 + SPI MOSI/SCK/CS pins 3/4/5 | `spi_tx_p345` | interp |
| T8 | Halt, load SPI over UART, run | `test_infra_desk.py` | interp |

Not on a USB-UART, W25, or TAP. Same graphs, interpreter/RTL.

## Do not do for the contest

- Hardcaml rewrite.
- 10G / FIX-at-exchange-rate / matching-engine tests.
- Analog USB/CAN/10BASE-T PHYs.
- FPGA bring-up this pass.
