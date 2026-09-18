"""16-bit ISA for one graph-node executor.

Opcodes are pin, time, shift, and control primitives. They are not protocols.
A protocol is a graph of these nodes, loaded after tapeout.

Bit layout:
  [15:13] opcode
  [12:8]  delay (extra cycles after the op, 0-31). If sideset_count=1, [12] is
          the sideset bit and [11:8] is delay 0-15.
  [7:5]   field (dest / condition / push-vs-pull)
  [4:0]   payload (imm, pin, address, MOV src; reserved for IN/OUT, which move one bit)

On-die extras (CSRs, not opcodes): clock divider, wrap, 4 graph slots, 2 SMs.
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
JMP_TX_NE = 6  # jump if TX FIFO has a byte (hold CS / next frame)
JMP_TX_EQ0 = 7  # jump if TX FIFO empty

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
REG_PINDIRS = 5  # MOV dest field 5 writes all 8 OE bits (src NULL is payload 5)
REG_XOR_Y = 6  # MOV dest = dest ^ Y (payload 6)
REG_CRC_FEED = 7  # feed OSR LSB into hidden CRC-15 (poly 0x4599)
REG_CRC_LO = 8  # dest = crc[7:0]
REG_CRC_HI = 9  # dest = crc[14:8]
REG_CRC_CLR = 10  # crc = 0
REG_CRC_OUT = 11  # dest = crc[14], crc <<= 1
CRC15_POLY = 0x4599

IMEM_WORDS = 32
FIFO_DEPTH = 4
N_SLOTS = 4  # resident graphs on the Tiny Tapeout die
N_SM_CHIP = 2

# CSR byte addresses (halted we+tx strobe). Per-SM blocks are 16 apart.
CSR_WRITE_SLOT = 0  # subsequent imem writes land in this slot
CSR_SM0_SLOT = 1
CSR_SM1_SLOT = 2
CSR_SM0_CLKDIV_LO = 3
CSR_SM0_CLKDIV_HI = 4
CSR_SM0_CLKDIV_FRAC = 5
CSR_SM0_WRAP_BOT = 6
CSR_SM0_WRAP_TOP = 7
CSR_SM0_SIDE = 8  # [2:0] base pin, [4]=sideset_count (0 or 1)
CSR_FIFO_SEL = 9  # host TX/RX target SM (0 or 1)
CSR_SM1_CLKDIV_LO = 19
CSR_SM1_CLKDIV_HI = 20
CSR_SM1_CLKDIV_FRAC = 21
CSR_SM1_WRAP_BOT = 22
CSR_SM1_WRAP_TOP = 23
CSR_SM1_SIDE = 24


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
