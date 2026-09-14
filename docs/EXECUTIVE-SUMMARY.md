# Executive summary: contest checklist vs Loom

Source: https://blog.janestreet.com/protocol-emulator-asic-competition/ (scraped 2026-09-14). Template: Tiny Tapeout ttihp-verilog-template branch cmos5l, GDS action `ihp-cmos5l` / PDK `ihp-sg13cmos5l`. Tests: 168 pytest minus iverilog; 9 protocols × Hi on iverilog.

Verdict: the architecture matches the brief (reprogrammable pin/time machine, not hardwired UART/SPI/I2C). The submission is not complete: no CMOS5L P&R, no closed timing, repo not public, sign-up unknown. Unique hook is agent-loaded graphs + interp≡RTL≡iverilog, not a trading PHY.

## Rules (must)

| Item | Status | Evidence |
|------|--------|----------|
| IHP 130nm CMOS5L via Tiny Tapeout | Partial | `.github/workflows/gds.yaml` uses `tt-gds-action@ihp-cmos5l`. GDS job has not been shown to pass. |
| Start from CMOS5L Verilog template | Yes | Fork of `ttihp-verilog-template` cmos5l (`src/config.json` PDN 50.0 / 2.1). |
| `info.yaml` tiles `8x4` | Yes | `info.yaml` tiles `"8x4"`, top `tt_um_loom_gpe`. |
| Area ≤ 8×4 (~32k cells) | Likely, unmapped | Generic Yosys 2333 cells (`estimates/synth.json`). Not CMOS5L stdcells. SRAM not used (FF imem, 623 seq). |
| Synth early, then P&R + timing | No | Generic synth only. No liberty, no LibreLane, `timing_50mhz: unknown`. |
| Open source | License yes, publish no | Apache-2.0. Git remote is still the TT template; not a public Loom repo. |
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
| Formal methods | Weak | Opcode golden interp vs RTL (`test_isa_golden.py`). No SymbiYosys. |
| Constrained random | Yes | `test_random_pins.py`, `test_random_uart_payloads`. |
| AI-assisted verification | Yes | Agent-built tests + criteria gate. |
| ASCII waveform expects (JS 2020 post, linked from contest) | Yes | `tests/expect/uart_hi.txt`, `spi_hi.txt`. |
| Gate-level after GDS | No | iverilog on RTL only. |

## Score

Ship the idea: 7/10. Ship a shuttle: 3/10 until LibreLane GDS + timing + public repo + sign-up.

Next three: (1) run `tt-gds-action@ihp-cmos5l` and keep the GDS artifact, (2) switch default I2C tests to open-drain graphs, (3) publish and fill the sign-up form.
