# Remaining work: contest criteria + infra tests

Status 2026-09-16: digital criteria 2–8, 10, 11, 13, 14 and T1–T8 **in simulation** are filled. Open: 1 sign-up, 9 submit, 12 FPGA (skipped), analog PHYs (out of scope), 2-SM+SRAM GDS close.

Goal of this chip: easiest agent-programmable pin/time engine. Not a Jane Street stack clone. Not a matching-engine NIC.

## Already met (sim / RTL / 1-SM GDS)

- Reprogrammable graph ISA (pins, wait, delay, shift, jump, fifo, mov). Protocols are graphs, not blocks. `loom check` forbids protocol names in the engine core.
- CMOS5L template, `info.yaml` tiles `6x4`, top `tt_um_loom_gpe`. Closed 1-SM GDS: 3,499 cells, Magic DRC 0, LVS unique, slow setup +8.99 ns @ 50 MHz.
- Current source: 2 SM / 4 slots, per-SM FIFOs, live nibble FIFO while GPIO is live, IHP 2P SRAM instance on `loom_chip`.
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
6. Synthesis on CMOS5L 6×4 — 1-SM GDS under budget; 2-SM uses SRAM macro (P&R of that netlist not closed).
7. Full P&R + timing — 1-SM GDS closed. Gate-level UART Hi on the **submitted** netlist is still the idle/SET_BIT/start-bit cocotb RTL wrapper (`test/test.py`). 2-SM+SRAM GDS not closed.
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
