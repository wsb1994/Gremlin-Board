<!---
Tiny Tapeout datasheet.
-->

## How it works

A reprogrammable graph engine: pin, wait, delay, shift, fifo, jump. UART, SPI, I2C, and anything else are graphs loaded into instruction memory after tapeout — not hardwired blocks.

RTL is generated from `generator/loom` (Amaranth). Protocol graphs live in `plans/`.

## How to test

Hello-world graphs: `plans/uart_tx.toml`, `uart_rx.toml`, `spi_*.toml`, `i2c_*.toml` encode/decode `Hi`.

Regenerate Verilog:

    PYTHONPATH=generator .venv/bin/python -m loom.emit

## Host protocol

Clock is `clk`. `rst_n` is active-low; the engine reset is `~rst_n`. Hold `rst_n=0` for ≥1 cycle, then release. Keep `ena=1`.

While `ui_in[0]=0` (halted), `uio` is input-only (`uio_oe=0`) and carries host data. While `ui_in[0]=1` (run), `uio` is GPIO.

Strobes are rising-edge sampled: drive 0 for ≥1 clk, 1 for ≥1 clk, 0 for ≥1 clk. Do not raise `ui_in[1]` and `ui_in[7]` on the same cycle. Hold `uio_in` and `ui_in[6:2]` stable through the high phase of a strobe.

### Pins

| pin | function |
|---|---|
| `ui_in[0]` | run |
| `ui_in[1]` | imem write strobe (two-phase) |
| `ui_in[6:2]` | imem word address (latched on the low-byte strobe) |
| `ui_in[7]` | TX FIFO push strobe |
| `uio_in[7:0]` | data byte while run=0; GPIO in while run=1 |
| `uo_out[0]` | run (echo) |
| `uo_out[1]` | tx_full |
| `uo_out[2]` | rx_empty |
| `uo_out[7:3]` | pc |

### Load one 16-bit instruction

Word `W` at address `A` (0..31). Example: `A=0`, `W=0xC015` (`SET` pins=`0x15`; low byte `0x15`, high byte `0xC0`).

1. Halt: `ui_in[0]=0`, `ui_in[7]=0`.
2. Low byte: `ui_in[6:2]=A` (`0`), `uio_in=W[7:0]` (`0x15`). Pulse `ui_in[1]`: 0 → 1 for ≥1 clk → 0 for ≥1 clk.
3. High byte: `uio_in=W[15:8]` (`0xC0`). Pulse `ui_in[1]` again. Address is ignored on this pulse. The rising edge commits `{W[15:8], W[7:0]}` to `imem[A]`.

A single strobe only latches the low byte; the word is not in imem until the second strobe.

### Push one TX byte

FIFO depth is 4. Skip the push if `uo_out[1]` (`tx_full`) is 1.

4. Halt: `ui_in[0]=0`, `ui_in[1]=0`.
5. `uio_in=byte` (e.g. `0x48` = `'H'`). Pulse `ui_in[7]`: 0 → 1 for ≥1 clk → 0 for ≥1 clk.

### Run

6. Drive `ui_in[0]=1`. The engine executes from `pc=0`. `uio` becomes GPIO (`uio_oe` follows the graph).
7. To reprogram: `ui_in[0]=0`, then repeat from step 2. Asserting run clears a half-written imem word so the next load starts on the low byte. Pulse `rst_n` to clear imem, FIFOs, and `pc`.

## External hardware

Protocol pins on the Tiny Tapeout bidirectional bank. Optional external memory/SD/USB can hold extra graphs; the on-chip working set is 32 instructions.
