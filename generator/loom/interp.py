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
    JMP_Y_EQ0,
    N_SLOTS,
    OP_FIFO,
    OP_IN,
    OP_JMP,
    OP_MOV,
    OP_NOP,
    OP_OUT,
    OP_SET,
    OP_WAIT,
    REG_ISR,
    REG_NULL,
    REG_OSR,
    REG_PINS,
    REG_X,
    REG_XOR_Y,
    REG_CRC_CLR,
    REG_CRC_FEED,
    REG_CRC_HI,
    REG_CRC_LO,
    REG_CRC_OUT,
    CRC15_POLY,
    REG_Y,
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
    slot: int = 0
    clkdiv_int: int = 1
    clkdiv_frac: int = 0
    div_down: int = 0
    frac_acc: int = 0
    wrap_bottom: int = 0
    wrap_top: int = 31
    sideset_count: int = 0
    side_base: int = 0
    side_latched: int = 0
    crc: int = 0

    def load(self, words: list[int]) -> None:
        if len(self.imem) != IMEM_WORDS:
            self.imem = [0] * IMEM_WORDS
        else:
            for i in range(IMEM_WORDS):
                self.imem[i] = 0
        for i, w in enumerate(words):
            if i >= IMEM_WORDS:
                break
            self.imem[i] = w & 0xFFFF
        self.pc = 0
        self.delay_ctr = 0
        self.div_down = 0
        self.frac_acc = 0
        self.crc = 0

    def effective_pins(self, gpio_in: int) -> int:
        eff = 0
        for i in range(8):
            if (self.oe_reg >> i) & 1:
                bit = (self.out_reg >> i) & 1
            else:
                bit = (gpio_in >> i) & 1
            eff |= bit << i
        return eff

    def _clk_en(self) -> bool:
        """True when this sysclk is an SM cycle. clkdiv_int=1, frac=0 → every cycle."""
        intval = self.clkdiv_int if self.clkdiv_int else 65536
        if self.div_down:
            self.div_down -= 1
            return False
        extra = 0
        self.frac_acc = (self.frac_acc + self.clkdiv_frac) & 0x1FF
        if self.frac_acc >= 256:
            extra = 1
            self.frac_acc -= 256
        self.div_down = intval - 1 + extra
        return True

    def _apply_sideset(self) -> None:
        if not self.sideset_count:
            return
        p = self.side_base & 7
        if self.side_latched:
            self.out_reg |= 1 << p
        else:
            self.out_reg &= ~(1 << p)
        self.out_reg &= 0xFF

    def _mov_src(self, src: int, eff: int) -> int:
        if src == REG_X:
            return self.x
        if src == REG_Y:
            return self.y
        if src == REG_OSR:
            return self.osr
        if src == REG_ISR:
            return self.isr
        if src == REG_PINS:
            return eff
        return 0  # NULL and unknown

    def _mov_dst(self, dest: int, value: int) -> None:
        value &= 0xFF
        if dest == REG_X:
            self.x = value
        elif dest == REG_Y:
            self.y = value
        elif dest == REG_OSR:
            self.osr = value
        elif dest == REG_ISR:
            self.isr = value
        elif dest == REG_PINS:
            self.out_reg = value

    def tick(self, gpio_in: int = 0) -> None:
        if not self.run:
            return
        if not self._clk_en():
            return
        if self.delay_ctr:
            self.delay_ctr -= 1
            self._apply_sideset()
            return
        op, delay_field, field, payload = decode(self.imem[self.pc & 31])
        if self.sideset_count:
            self.side_latched = (delay_field >> 4) & 1
            delay = delay_field & 15
        else:
            delay = delay_field
        self._apply_sideset()
        eff = self.effective_pins(gpio_in)
        stall = False
        taken_jmp = False
        target = payload & 31
        next_pc = (self.pc + 1) & 31

        if op == OP_JMP:
            if field == JMP_ALWAYS:
                next_pc = target
                taken_jmp = True
            elif field == JMP_X_EQ0:
                if self.x == 0:
                    next_pc = target
                    taken_jmp = True
            elif field == JMP_Y_EQ0:
                if self.y == 0:
                    next_pc = target
                    taken_jmp = True
            elif field == JMP_X_DEC:
                if self.x != 0:
                    self.x = (self.x - 1) & 0xFF
                    next_pc = target
                    taken_jmp = True
            elif field == JMP_Y_DEC:
                if self.y != 0:
                    self.y = (self.y - 1) & 0xFF
                    next_pc = target
                    taken_jmp = True
            elif field == JMP_PIN:
                if (eff >> self.in_pin) & 1:
                    next_pc = target
                    taken_jmp = True
        elif op == OP_WAIT:
            pin = payload & 15
            pol = (payload >> 4) & 1
            if ((eff >> pin) & 1) != pol:
                stall = True
        elif op == OP_OUT:
            # One bit per instruction on out_pin; payload is reserved (RTL ignores it).
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
            # One sample per instruction from in_pin; payload is reserved (RTL ignores it).
            sample = (eff >> self.in_pin) & 1
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
        elif op == OP_MOV:
            if payload == REG_XOR_Y:
                if field == REG_X:
                    cur = self.x
                elif field == REG_Y:
                    cur = self.y
                elif field == REG_OSR:
                    cur = self.osr
                elif field == REG_ISR:
                    cur = self.isr
                elif field == REG_PINS:
                    cur = self.out_reg
                else:
                    cur = 0
                self._mov_dst(field, cur ^ self.y)
            elif payload == REG_CRC_FEED:
                b = self.osr & 1
                msb = (self.crc >> 14) & 1
                self.crc = ((self.crc << 1) & 0x7FFF)
                if msb ^ b:
                    self.crc ^= CRC15_POLY
            elif payload == REG_CRC_LO:
                self._mov_dst(field, self.crc & 0xFF)
            elif payload == REG_CRC_HI:
                self._mov_dst(field, (self.crc >> 8) & 0x7F)
            elif payload == REG_CRC_CLR:
                self.crc = 0
            elif payload == REG_CRC_OUT:
                bit = (self.crc >> 14) & 1
                self.crc = (self.crc << 1) & 0x7FFF
                self._mov_dst(field, bit)
            else:
                self._mov_dst(field, self._mov_src(payload, eff))
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
            if taken_jmp:
                self.pc = next_pc
            elif self.pc == (self.wrap_top & 31):
                self.pc = self.wrap_bottom & 31
            else:
                self.pc = next_pc
            self.delay_ctr = delay


class Engine:
    def __init__(self, n_sm: int = 1, n_slots: int = 1) -> None:
        if n_sm not in (1, 2):
            raise ValueError("n_sm must be 1 or 2")
        if n_slots not in (1, N_SLOTS):
            raise ValueError("n_slots must be 1 or 4")
        self.n_sm = n_sm
        self.n_slots = n_slots
        self.slots = [[0] * IMEM_WORDS for _ in range(n_slots)]
        self.write_slot = 0
        self.sms = [SM() for _ in range(n_sm)]
        if n_slots > 1:
            for i, sm in enumerate(self.sms):
                sm.slot = min(i, n_slots - 1)
                sm.imem = self.slots[sm.slot]
        self.sm = self.sms[0]
        self.cycles = 0
        self.trace_out: list[int] = []
        self.trace_oe: list[int] = []

    def load(self, words: list[int], sm: int = 0, slot: int | None = None) -> None:
        if self.n_slots == 1:
            self.sms[sm].load(words)
            self.sms[sm].run = False
            if sm == 0:
                self.cycles = 0
                self.trace_out = []
                self.trace_oe = []
            return
        if slot is None:
            slot = self.sms[sm].slot
        slot &= self.n_slots - 1
        bank = self.slots[slot]
        self.sms[sm].imem = bank
        self.sms[sm].slot = slot
        self.sms[sm].load(words)
        self.sms[sm].imem = bank
        self.sms[sm].run = False
        if sm == 0:
            self.cycles = 0
            self.trace_out = []
            self.trace_oe = []

    def bind_slot(self, sm: int, slot: int) -> None:
        slot &= self.n_slots - 1
        self.sms[sm].slot = slot
        self.sms[sm].imem = self.slots[slot]

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
