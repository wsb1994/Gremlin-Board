# Remaining work: contest criteria + infra tests

Goal of this chip: easiest agent-programmable pin/time engine. Not a Jane Street stack clone. Not a matching-engine NIC.

Jane Street’s stated use for a protocol emulator is hardware debugging and reverse engineering. Trading-infra tests below mean “can this talk to the boxes around a trading system,” not “can this carry the feed.”

## Already met (sim only)

- Reprogrammable graph ISA (pins, wait, delay, shift, jump, fifo). Protocols are graphs, not blocks.
- CMOS5L template, `info.yaml` tiles `6x4`, top `tt_um_loom_gpe`.
- UART / SPI / I2C encode+decode in interpreter, Amaranth, and iverilog.
- Agent path: TOML graph → compiler → generated Verilog.
- Open-source license on the template (Apache-2.0).

## Must complete to be a valid submission

1. Sign-up form on the contest page (not a commit; still required for the submission link).
2. Publish the repo (open source, build in public).
3. Host load that an agent can actually use after reset: write imem + TX FIFO + run without a lab hack. Document the byte protocol in `docs/info.md`.
4. Prove a fourth protocol with zero RTL change. Add `plans/jtag_tck.toml` or `plans/swd.toml`, round-trip in the same tests. That is the “new protocols after fabrication” clause.
5. Real I2C, not the hello cartoon: open-drain (OE only, bus pull-up), ACK bit, clock stretch via `wait_pin`. Golden test against a model that NACKs and stretches.
6. Synthesis on CMOS5L, 8×4. Record mapped cell count vs ~32k budget. Leave margin for CTS/routing. If over, cut SMs/FIFO or move imem to SRAM (TT has IHP SRAM examples).
7. Full LibreLane P&R + timing at a declared `clock_hz`. If 50 MHz fails, drop `CLOCK_PERIOD` and the graphs’ cycle budgets together. Gate-level sim of UART TX “Hi” on the netlist.
8. `docs/info.md` + README: how to load a graph, pinout, what the ISA is not (no UART block).
9. Submit by 2027-01-18 through their form.

## Should complete (they asked for these by name)

10. Constrained-random pin tests: random baud-ish delays, CS gaps, extra edges; decoder must still get the payload or flag framing error. AI-written generators are on-brief.
11. Formal or cheap equivalent: interp vs RTL on the ISA step function (one instruction, all opcodes). SymbiYosys or exhaustive golden for the 8 opcodes.
12. FPGA smoke (optional but named): same Verilog on a TT demo board FPGA or iCEBreaker; UART “Hi” on a pin, sigrok or a USB-UART.
13. Second state machine if area allows. Agent-programmable gets more interesting when UART log and SPI flash run together.
14. Stretch graphs in `plans/` (USB LS, 10M-class Ethernet, CAN) are **bit-layer subsets, not full PHYs**. USB is D+ 8N1 (not NRZI/packet). Ethernet is MII-like clock+data (not 10BASE-T magnetics). CAN has no bit stuffing/CRC. Do not treat them as LS USB PHY or 10BASE-T magnetics.

## Do not do for the contest

- Hardcaml rewrite.
- 10G / FIX-at-exchange-rate / matching-engine tests.
- Treating GIF/JSON roundtrips as trading infrastructure.

## Trading-infrastructure tests (debug/RE, on this die)

These are the tests that match “we bit-bang what is on the desk,” at this chip’s rates (~5–11 Mbps class, 8 GPIO).

| # | Test | Why it is infra | Pass |
|---|------|-----------------|------|
| T1 | UART 115200 8N1 to a USB-UART (graph delay loop or divider) | BMC, console, FPGA UART | sigrok or minicom shows `Hi` / a JSON snapshot |
| T2 | SPI mode 0 flash ID (`0x9F`) against a model, then a real W25 if FPGA | Config ROM, FPGA flash | 3-byte JEDEC ID |
| T3 | I2C EEPROM read (open-drain, ACK) addr `0x50` | SPD, QSFP, sensors | 16 bytes match |
| T4 | JTAG TAP: TMS/TCK/TDI/TDO IDCODE | FPGA/ASIC debug | 32-bit IDCODE stable |
| T5 | SWD line reset + `DPIDR` | MCU debug | DPIDR parsed |
| T6 | Bit-period error | Their whole point is timing | TX bit width within 2% at declared baud |
| T7 | Dual-SM: SPI read while UART dumps bytes | Agent debug session | both graphs, no RTL change |
| T8 | Reprogram in place | After-fab clause | halt, load CAN bit-layer subset or SWD graph, run T4/T5 without resynth |

Optional later, not criteria: CAN bit-layer subset (no stuffing/CRC) at 125 kbit if T1–T8 and area are green.

## Order

Sign-up and publish → host protocol doc → I2C open-drain+ACK → fourth graph (JTAG or SWD) → synth/area → P&R/timing/GL → constrained-random + opcode golden → T1–T8 on sim, FPGA if you have one → submission zip + writeup.

The writeup should say: agent loads graphs; chip is a PIO-class emulator; verification is interp≡RTL≡iverilog plus random and (if done) formal; area/timing attached. Do not lead with HFT payloads.
