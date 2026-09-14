"""Cycle-accurate ISA interpreter — golden model for RTL and protocol tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from loom.isa import (
    CLR_BIT,
    FIFO_DEPTH,
    FIFO_PULL,
    FIFO_PUSH,
    IMEM_WORDS,
    JMP_ALWAYS,
    JMP_PIN,
    JMP_X_DEC,
    JMP_X_EQ0,
    JMP_Y_DEC,
    OP_FIFO,
    OP_IN,
    OP_JMP,
    OP_NOP,
    OP_OUT,
    OP_SET,
    OP_WAIT,
    SET_BIT,
    SET_INPIN,
    SET_OUTPIN,
    SET_PINDIRS,
    SET_PINS,
    SET_X,
    SET_Y,
    SHIFT_LSB,
    decode,
)


class Fifo:
    def __init__(self, depth: int = FIFO_DEPTH):
        self.depth = depth
        self.q: list[int] = []

    def push(self, v: int) -> bool:
        if len(self.q) >= self.depth:
            return False
        self.q.append(v & 0xFF)
        return True

    def pop(self) -> int | None:
        if not self.q:
            return None
        return self.q.pop(0)

    @property
    def empty(self) -> bool:
        return not self.q

    @property
    def full(self) -> bool:
        return len(self.q) >= self.depth


@dataclass
class SM:
    pc: int = 0
    x: int = 0
    y: int = 0
    osr: int = 0
    isr: int = 0
    delay_ctr: int = 0
    out_reg: int = 0
    oe_reg: int = 0
    out_pin: int = 0
    in_pin: int = 0
    run: bool = False
    imem: list[int] = field(default_factory=lambda: [0] * IMEM_WORDS)
    tx: Fifo = field(default_factory=Fifo)
    rx: Fifo = field(default_factory=Fifo)

    def load(self, words: list[int]) -> None:
        self.imem = [0] * IMEM_WORDS
        for i, w in enumerate(words):
            self.imem[i] = w & 0xFFFF
        self.pc = 0
        self.delay_ctr = 0

    def effective_pins(self, gpio_in: int) -> int:
        eff = 0
        for i in range(8):
            if (self.oe_reg >> i) & 1:
                bit = (self.out_reg >> i) & 1
            else:
                bit = (gpio_in >> i) & 1
            eff |= bit << i
        return eff

    def tick(self, gpio_in: int = 0) -> None:
        if not self.run:
            return
        if self.delay_ctr:
            self.delay_ctr -= 1
            return
        op, delay, field, payload = decode(self.imem[self.pc & 31])
        eff = self.effective_pins(gpio_in)
        stall = False
        next_pc = (self.pc + 1) & 31

        if op == OP_JMP:
            target = payload & 31
            if field == JMP_ALWAYS:
                next_pc = target
            elif field == JMP_X_EQ0:
                if self.x == 0:
                    next_pc = target
            elif field == JMP_X_DEC:
                if self.x != 0:
                    self.x = (self.x - 1) & 0xFF
                    next_pc = target
            elif field == JMP_Y_DEC:
                if self.y != 0:
                    self.y = (self.y - 1) & 0xFF
                    next_pc = target
            elif field == JMP_PIN:
                if (eff >> self.in_pin) & 1:
                    next_pc = target
        elif op == OP_WAIT:
            pin = payload & 15
            pol = (payload >> 4) & 1
            if ((eff >> pin) & 1) != pol:
                stall = True
        elif op == OP_OUT:
            n = payload if payload else 8
            for _ in range(n):
                if field == SHIFT_LSB:
                    bit = self.osr & 1
                    self.osr = (self.osr >> 1) & 0xFF
                else:
                    bit = (self.osr >> 7) & 1
                    self.osr = (self.osr << 1) & 0xFF
                p = self.out_pin
                if bit:
                    self.out_reg |= 1 << p
                else:
                    self.out_reg &= ~(1 << p)
                self.out_reg &= 0xFF
        elif op == OP_IN:
            n = payload if payload else 8
            pin = self.in_pin
            for _ in range(n):
                sample = (eff >> pin) & 1
                if field == SHIFT_LSB:
                    self.isr = ((self.isr >> 1) | (sample << 7)) & 0xFF
                else:
                    self.isr = ((self.isr << 1) | sample) & 0xFF
        elif op == OP_FIFO:
            if field == FIFO_PULL:
                v = self.tx.pop()
                if v is None:
                    stall = True
                else:
                    self.osr = v
            else:
                if not self.rx.push(self.isr):
                    stall = True
        elif op == OP_SET:
            if field == SET_PINS:
                self.out_reg = (self.out_reg & ~0x1F) | (payload & 0x1F)
            elif field == SET_PINDIRS:
                self.oe_reg = (self.oe_reg & ~0x1F) | (payload & 0x1F)
            elif field == SET_X:
                self.x = payload & 31
            elif field == SET_Y:
                self.y = payload & 31
            elif field == SET_BIT:
                self.out_reg = (self.out_reg | (1 << (payload & 7))) & 0xFF
            elif field == CLR_BIT:
                self.out_reg = (self.out_reg & ~(1 << (payload & 7))) & 0xFF
            elif field == SET_OUTPIN:
                self.out_pin = payload & 7
            elif field == SET_INPIN:
                self.in_pin = payload & 7
        elif op == OP_NOP:
            pass

        if not stall:
            self.pc = next_pc
            self.delay_ctr = delay


class Engine:
    def __init__(self, n_sm: int = 1) -> None:
        if n_sm not in (1, 2):
            raise ValueError("n_sm must be 1 or 2")
        self.n_sm = n_sm
        self.sms = [SM() for _ in range(n_sm)]
        self.sm = self.sms[0]
        self.cycles = 0
        self.trace_out: list[int] = []
        self.trace_oe: list[int] = []

    def load(self, words: list[int], sm: int = 0) -> None:
        self.sms[sm].load(words)
        self.sms[sm].run = False
        if sm == 0:
            self.cycles = 0
            self.trace_out = []
            self.trace_oe = []

    def _bus(self, gpio_in: int) -> int:
        bus = gpio_in & 0xFF
        for sm in self.sms:
            for i in range(8):
                if (sm.oe_reg >> i) & 1:
                    bus = (bus & ~(1 << i)) | (sm.out_reg & (1 << i))
        return bus

    def run_cycles(self, n: int, gpio_in_seq: list[int] | None = None) -> None:
        for sm in self.sms:
            sm.run = True
        for i in range(n):
            gin = 0
            if gpio_in_seq is not None:
                gin = gpio_in_seq[i] if i < len(gpio_in_seq) else gpio_in_seq[-1]
            bus = self._bus(gin)
            for sm in self.sms:
                sm.tick(bus)
            out = 0
            oe = 0
            for sm in self.sms:
                out |= sm.out_reg
                oe |= sm.oe_reg
            self.trace_out.append(out)
            self.trace_oe.append(oe)
            self.cycles += 1
