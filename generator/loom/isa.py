"""16-bit ISA for one graph-node executor.

Opcodes are pin, time, shift, and control primitives. They are not protocols.
A protocol is a graph of these nodes, loaded after tapeout.

Bit layout:
  [15:13] opcode
  [12:8]  delay (extra cycles after the op, 0-31)
  [7:5]   field (dest / condition / push-vs-pull)
  [4:0]   payload (imm, pin, bitcount, address)
"""

from __future__ import annotations

OP_JMP = 0
OP_WAIT = 1
OP_IN = 2
OP_OUT = 3
OP_FIFO = 4  # field 0 = PUSH isr->rx, field 1 = PULL tx->osr
OP_MOV = 5
OP_SET = 6
OP_NOP = 7

OP_NAMES = {
    OP_JMP: "JMP",
    OP_WAIT: "WAIT",
    OP_IN: "IN",
    OP_OUT: "OUT",
    OP_FIFO: "FIFO",
    OP_MOV: "MOV",
    OP_SET: "SET",
    OP_NOP: "NOP",
}

# JMP field
JMP_ALWAYS = 0
JMP_X_EQ0 = 1
JMP_Y_EQ0 = 2
JMP_X_DEC = 3
JMP_Y_DEC = 4
JMP_PIN = 5

# WAIT payload: [4]=polarity, [3:0]=pin
# IN/OUT field: shift direction on the 8-bit register, protocol-agnostic
SHIFT_LSB = 0  # emit/sample register bit 0, then shift toward 0
SHIFT_MSB = 1  # emit/sample register bit 7, then shift toward 7

# FIFO field
FIFO_PUSH = 0
FIFO_PULL = 1

# SET field
SET_PINS = 0
SET_PINDIRS = 1
SET_X = 2
SET_Y = 3
SET_BIT = 4
CLR_BIT = 5
SET_OUTPIN = 6
SET_INPIN = 7

# MOV dest/src in field/payload
REG_X = 0
REG_Y = 1
REG_OSR = 2
REG_ISR = 3
REG_PINS = 4
REG_NULL = 5

IMEM_WORDS = 32
FIFO_DEPTH = 4


def encode(op: int, delay: int = 0, field: int = 0, payload: int = 0) -> int:
    if not 0 <= op < 8:
        raise ValueError(f"op {op}")
    if not 0 <= delay < 32:
        raise ValueError(f"delay {delay}")
    if not 0 <= field < 8:
        raise ValueError(f"field {field}")
    if not 0 <= payload < 32:
        raise ValueError(f"payload {payload}")
    return (op << 13) | (delay << 8) | (field << 5) | payload


def decode(word: int) -> tuple[int, int, int, int]:
    word &= 0xFFFF
    op = (word >> 13) & 7
    delay = (word >> 8) & 31
    field = (word >> 5) & 7
    payload = word & 31
    return op, delay, field, payload


def fmt(word: int) -> str:
    op, delay, field, payload = decode(word)
    return f"{OP_NAMES[op]:4s} delay={delay:2d} field={field} payload={payload:02d}  0x{word:04x}"
