# Changelog

## 0.4.0

- Production graph engine: MOV and JMP Y==0 implemented; clock divider (16.8); wrap; 1-bit sideset
- Die holds 4×32-word graph slots and 2 state machines (`loom_chip`); host can pop RX
- GPIO 2FF sync while running; CSR bus for slot/clkdiv/wrap/sideset
- UART 8N1 production graphs (`uart_8n1_tx.toml` / `uart_8n1_rx.toml`): centre sample, start verify, stop check, dual-SM
- Protocol completeness (`loom formal-proto`): all 256 bytes on every TX/RX pair — encoding ∈ L, RX(spec)=id, round-trip, pull-loop
- Contest line codecs in 32-word graphs: SPI mode-0+CS, I2C open-drain, JTAG TMS TAP, SWD line-reset, PS/2 odd parity+ACK, CAN stuffed CRC-15, USB LS NRZI+SYNC+EOP, Ethernet preamble/SFD; Big Chungus PNG SHA-256 round-trip on each pair

## 0.3.0

- CMOS5L GDS via LibreLane: DRC/LVS clean, 3,499 cells, 50 MHz closed; gl_test and precheck pass in CI
- Formal: `loom formal` k-induction (yosys sat) over ISA step semantics + FIFO/halt/imem invariants
- Exhaustive ISA golden: every encoding, interp vs emitted Verilog under iverilog
- Constrained-random pin tests: baud error, edge jitter, gaps, glitches, SPI clock asymmetry
- `plans/uart_rx_frame.toml`: start-bit verify, stop-bit check, frame-error flag on pin1
- `uart_rx` syncs to idle-high and samples at bit centre (pass band now symmetric)
- Interpreter IN/OUT move one bit per instruction, matching RTL (payload reserved)
- info.yaml tiles 6x4 (8x4 not yet defined by the CMOS5L tooling); gl_test includes `sg13cmos5l_udp.v`

## 0.2.0

- CLI: `loom emit|check|plans|synth`
- Host load documented and tested
- Open-drain I2C graphs + ACK/stretch tests
- Optional second SM (`n_sm=2`, default 1)
- ISA golden tests and random pin roundtrips
- Generic Yosys area estimate (not CMOS5L P&R)
- USB/ETH/CAN labeled as bit-layer subsets

## 0.1.0

- Graph IR, ISA, interpreter, Amaranth RTL, Tiny Tapeout CMOS5L wrapper
