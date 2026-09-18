<!---
Tiny Tapeout datasheet.
-->

## How it works

A reprogrammable graph engine: pin, wait, delay, shift, fifo, jump, mov. UART, SPI, I2C, and anything else are graphs loaded into instruction memory after tapeout — not hardwired blocks.

The die holds **four 32-instruction graph slots** and **two state machines**, each with its own TX/RX FIFO. Baud is a clock divider CSR, not a hardwired UART. GPIO inputs are 2-flop synchronised while running. Four-slot instruction memory is IHP 2-port SRAM (`RM_IHPSG13_2P_256x16_c2_bm_bist`, 1-cycle `next_pc` fetch). It is volatile: `rst_n` forgets the graphs.

RTL is generated from `generator/loom` (Amaranth). Protocol graphs live in `plans/`. Production UART 8N1: `uart_8n1_tx.toml` / `uart_8n1_rx.toml`.

## How to test

Hello-world graphs: `plans/uart_tx.toml`, `uart_rx.toml`, `spi_*.toml`, `i2c_*.toml` encode/decode `Hi`.

Regenerate Verilog:

    PYTHONPATH=generator .venv/bin/python -m loom.emit

## Host protocol

Clock is `clk`. `rst_n` is active-low; the engine reset is `~rst_n`. Hold `rst_n=0` for ≥1 cycle, then release. Keep `ena=1`.

While `ui_in[0]=0` (halted), `uio` is input-only (`uio_oe=0`) and carries host data. While `ui_in[0]=1` (run), `uio` is GPIO.

Strobes are rising-edge sampled: drive 0 for ≥1 clk, 1 for ≥1 clk, 0 for ≥1 clk. Hold `uio_in` and `ui_in[6:2]` stable through the high phase of a strobe. `ui_in[1]`+`ui_in[7]` together is a CSR write, not an error.

### Pins

| pin | function |
|---|---|
| `ui_in[0]` | run |
| `ui_in[1]` | strobe A: imem write (two-phase) or CSR (if `ui_in[7]` is also 1) |
| `ui_in[6:2]` | imem/CSR address (latched on the imem low-byte strobe) |
| `ui_in[7]` | strobe B: TX push / RX pop; CSR qualifier with strobe A |
| `ui_in[2]` | during strobe B: 0 = TX push, 1 = RX pop |
| `uio_in[7:0]` | data byte while run=0; GPIO in while run=1 |
| `uo_out` | run=1: `{pc, rx_empty, tx_full, run}`. Halted with `ui_in[2]=1`: `rx_data`. Else status with run=0. |

### Load one 16-bit instruction

Word `W` at address `A` (0..31) in the current write-slot (CSR 0, default slot 0). Example: `A=0`, `W=0xC015`.

1. Halt: `ui_in[0]=0`, `ui_in[7]=0`.
2. Low byte: `ui_in[6:2]=A` (`0`), `uio_in=W[7:0]` (`0x15`). Pulse `ui_in[1]`.
3. High byte: `uio_in=W[15:8]` (`0xC0`). Pulse `ui_in[1]` again. The rising edge commits `{W[15:8], W[7:0]}` to `imem[slot][A]`.

A single strobe only latches the low byte; the word is not in imem until the second strobe.

### CSR write

Hold `ui_in[7]=1`, set `ui_in[6:2]` to the CSR address, `uio_in` to the byte, pulse `ui_in[1]`. Useful addresses: `0` write-slot 0..3; `1`/`2` SM0/SM1 execute-slot; `3`/`4`/`5` SM0 clkdiv lo/hi/frac; `6`/`7` SM0 wrap bottom/top; `9` host FIFO SM select.

### Push one TX byte (halt)

FIFO depth is 4 per state machine. CSR 9 selects which SM the host talks to (default 0). Skip the push if `uo_out[1]` (`tx_full`) is 1.

4. Halt: `ui_in[0]=0`, `ui_in[1]=0`, `ui_in[2]=0`.
5. `uio_in=byte`. Pulse `ui_in[7]`.

### Pop one RX byte (halt)

6. Halt, `ui_in[2]=1`. `uo_out` is the FIFO head. Pulse `ui_in[7]` to pop. Skip if `rx_empty`.

### Live FIFO (run=1, GPIO stays on `uio`)

Do not drop `run` to refill. While `ui_in[0]=1`, `uio` is the protocol bus.

- TX: two nibbles on `ui_in[6:3]`, `ui_in[2]=0`, pulse `ui_in[7]` each. First strobe latches the low nibble; second commits `{high, low}`.
- RX: `ui_in[2]=1` puts the FIFO head on `uo_out`; pulse `ui_in[7]` to pop.

### Run

7. Drive `ui_in[0]=1` with `ena=1`. SM0 and SM1 execute from `pc=0` in their assigned slots. `uio_oe` is registered (one-cycle turnaround). Inputs are 2-flop synchronised. `ena=0` forces OE=0 and ignores strobes.
8. To reprogram: `ui_in[0]=0`, then repeat from step 2. Asserting run clears a half-written imem word. Pulse `rst_n` to clear imem, FIFOs, CSRs, and `pc`.

`clkdiv` integer 0 is a 65536-cycle SM period, not “divide by 1”.

## External hardware

Protocol pins on the Tiny Tapeout bidirectional bank. Four graphs live on-chip (32 instructions each). Optional external memory can hold more; the host pages them into a slot.
