# Executive summary: contest checklist vs Loom

Source: https://blog.janestreet.com/protocol-emulator-asic-competition/ (scraped 2026-09-14). Template: Tiny Tapeout ttihp-verilog-template branch cmos5l, GDS action `ihp-cmos5l` / PDK `ihp-sg13cmos5l`. Tests: 168 pytest minus iverilog; 9 protocols × Hi on iverilog.

Verdict (updated 2026-09-14): the architecture matches the brief (reprogrammable pin/time machine, not hardwired UART/SPI/I2C). CMOS5L GDS, timing, gate-level sim and precheck all pass; repo is public. Open: sign-up form, final submission form, 8x4 tile once the tooling defines it, FPGA smoke. Unique hook is agent-loaded graphs + interp≡RTL≡iverilog≡formal, not a trading PHY.

## Rules (must)

| Item | Status | Evidence |
|------|--------|----------|
| IHP 130nm CMOS5L via Tiny Tapeout | Yes | `tt-gds-action@ihp-cmos5l`: gds, gl_test, precheck, viewer all green (run 34895469813). Local LibreLane 3.1.0.dev3: Magic/KLayout DRC 0, LVS 0, antenna 0. |
| Start from CMOS5L Verilog template | Yes | Fork of `ttihp-verilog-template` cmos5l (`src/config.json` PDN 50.0 / 2.1). |
| `info.yaml` tiles | 6x4 for now | Contest says 8x4; the CMOS5L tt-support-tools branch defines up to 6x4/8x2, so 8x4 fails config. Flip back when added. |
| Area | Yes | 3,499 mapped CMOS5L cells, 56,492 µm², 8% of the 6x4 die (~2.6% of 8x4). FF imem, no SRAM. |
| Synth early, then P&R + timing | Yes | LibreLane P&R at 50 MHz: setup slack +9.0 ns (slow 1.08 V 125 °C), hold +0.12 ns (fast), 8 max-slew pins on one net in the slow corner (warning only). |
| Open source | Yes | Apache-2.0, public: https://github.com/wsb1994/Gremlin-Board |
| Deadline 2027-01-18 | Time left | ~4 months. |
| Sign-up form | Unknown | Not in repo. Final submit form not on the page yet. |
| `tt_um_*` + `src/` + `docs/info.md` | Yes | Generated `src/loom_engine.v` (2841 lines), wrapper `src/project.v`, host protocol in `docs/info.md`. |

## Challenge (function)

| Item | Status | Tests |
|------|--------|-------|
| General-purpose emulator, not UART+SPI+I2C blocks | Yes | Engine core forbids protocol names (`loom check`, `tests/test_hello_graphs.py`). Graphs in `plans/`. |
| ISA: read/write pins, count cycles, hit timing | Yes | 16-bit ISA; UART bits exactly 8 cycles (`test_uart_bit_time_is_exact`). |
| Reprogrammable after fab | Yes in sim | Host load (`test_host_load.py`); reload UART→SPI→JTAG (`test_reprogram_*`). 32-word imem. |
| UART | Yes | Interp, Amaranth, iverilog `Hi`; payloads; ASCII expect waves. |
| SPI | Yes | Same. JEDEC bytes as payload. |
| I2C | Split | Cartoon push-pull still the default Hi pair. Open-drain + ACK + stretch: `plans/i2c_od_*.toml`, `tests/test_i2c_opendrain.py`. |
| Stretch USB LS | Bit-layer only | D+ 8N1, not NRZI/packets. iverilog `Hi`. |
| Stretch 10Mbit Ethernet | Bit-layer only | MII-like clk+data, not magnetics. iverilog `Hi`. |
| JTAG, SWD, PS/2, CAN | Bit-layer yes | All nine round-trip `Hi` in interp and iverilog (`test_all_protocols` + `test_verilog_every_protocol_hi`). CAN: no stuff/CRC. |
| FPGA before ASIC | No | Not run. |
| “Anything else” | Partial | Agent graph compiler; self-correct RX from measured bit time (`loom.correct`); optional `n_sm=2`. |

## Verification (they named these)

| Item | Status | Tests |
|------|--------|-------|
| Language besides Verilog | Yes | Amaranth generator. Not Hardcaml (optional). |
| Formal methods | Yes | `loom formal`: k-induction (yosys `sat`, MiniSat) over 129 assertions: one-step semantics of all 8 opcodes incl. stalls and delay, FIFO occupancy/pointer/full-drop, halt freeze, no imem load while running. Mutation-checked. Plus exhaustive golden: all 2048 encodings × 7 stimuli, interp vs emitted Verilog (`test_verilog_isa_exhaustive.py`). |
| Constrained random | Yes | `test_random_jitter.py`: ±3% baud + ±1 cycle edge jitter, tolerance-band sweep (≥±4%), runt-start rejection, break flag + recovery, SPI clock asymmetry/gaps/MOSI noise. Plus `test_random_pins.py`. |
| AI-assisted verification | Yes | Agent-built tests + criteria gate. |
| ASCII waveform expects (JS 2020 post, linked from contest) | Yes | `tests/expect/uart_hi.txt`, `spi_hi.txt`. |
| Gate-level after GDS | Yes | cocotb `GATES=yes` on the `tt_submission` netlist passes (CI gl_test and locally). |

## Score

Ship the idea: 8/10. Ship a shuttle: 8/10; remaining items are paperwork (sign-up, submission form) and the 8x4 tile flip.

Next three: (1) fill the sign-up form, (2) ask Tiny Tapeout when 8x4 lands on the CMOS5L branch and flip `info.yaml`, (3) FPGA smoke of UART `Hi` on a demo board.
