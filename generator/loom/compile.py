"""Compile a goblin-style Plan into ISA words."""

from __future__ import annotations

from dataclasses import dataclass, field

from loom.ir import InputKind, Plan, LoomError
from loom.isa import (
    CLR_BIT,
    FIFO_PULL,
    FIFO_PUSH,
    IMEM_WORDS,
    JMP_ALWAYS,
    JMP_PIN,
    JMP_X_DEC,
    JMP_X_EQ0,
    JMP_Y_DEC,
    JMP_Y_EQ0,
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
    REG_Y,
    SET_BIT,
    SET_INPIN,
    SET_OUTPIN,
    SET_PINDIRS,
    SET_PINS,
    SET_X,
    SET_Y,
    SHIFT_LSB,
    SHIFT_MSB,
    encode,
)

_REG = {
    "x": REG_X,
    "y": REG_Y,
    "osr": REG_OSR,
    "isr": REG_ISR,
    "pins": REG_PINS,
    "null": REG_NULL,
}


@dataclass
class Instr:
    op: int
    delay: int = 0
    field: int = 0
    payload: int | str = 0  # str = unresolved label
    comment: str = ""


@dataclass
class Program:
    name: str = ""
    instrs: list[Instr] = field(default_factory=list)
    labels: dict[str, int] = field(default_factory=dict)
    sideset_count: int = 0
    wrap_bottom: int = 0
    wrap_top: int = 31

    def mark(self, name: str) -> None:
        if name in self.labels:
            raise LoomError(f"duplicate label {name}")
        self.labels[name] = len(self.instrs)

    def add(self, instr: Instr) -> None:
        self.instrs.append(instr)

    def assemble(self) -> list[int]:
        words: list[int] = []
        for ins in self.instrs:
            payload = ins.payload
            if isinstance(payload, str):
                if payload not in self.labels:
                    raise LoomError(f"unresolved label {payload}")
                payload = self.labels[payload]
            words.append(encode(ins.op, ins.delay, ins.field, int(payload)))
        if len(words) > IMEM_WORDS:
            raise LoomError(f"{self.name}: {len(words)} instrs > {IMEM_WORDS}")
        return words


def _imm(step, default: int = 0) -> int:
    if not step.inputs:
        return default
    inp = step.inputs[0]
    if inp.kind == InputKind.LABEL:
        raise LoomError(f"{step.name}: expected immediate, got label")
    return int(inp.value, 0)


def _label(step) -> str:
    if not step.inputs:
        raise LoomError(f"{step.name}: missing jump target")
    return step.inputs[0].value


def _delay_field(plan: Plan, step) -> int:
    d = step.delay
    if plan.sideset_count:
        side = 0 if step.sideset is None else (step.sideset & 1)
        if d > 15:
            d = 15
        return (side << 4) | (d & 15)
    return d


def _reg(step, idx: int, default: int = 0) -> int:
    if idx >= len(step.inputs):
        return default
    raw = step.inputs[idx].value.lower()
    if raw in _REG:
        return _REG[raw]
    return int(raw, 0) & 7


def compile_plan(plan: Plan) -> Program:
    plan.validate()
    prog = Program(
        name=plan.name,
        sideset_count=plan.sideset_count,
        wrap_bottom=plan.wrap_bottom,
        wrap_top=plan.wrap_top,
    )
    for step in plan.steps:
        prog.mark(step.name)
        dmax = 15 if plan.sideset_count else 31
        extra = max(0, step.delay - dmax)
        d = _delay_field(plan, step)
        fn = step.function
        if fn == "pull":
            prog.add(Instr(OP_FIFO, d, FIFO_PULL, 0, step.name))
        elif fn == "push":
            prog.add(Instr(OP_FIFO, d, FIFO_PUSH, 0, step.name))
        elif fn == "set_pins":
            prog.add(Instr(OP_SET, d, SET_PINS, _imm(step) & 31, step.name))
        elif fn == "set_pindirs":
            prog.add(Instr(OP_SET, d, SET_PINDIRS, _imm(step) & 31, step.name))
        elif fn == "set_x":
            prog.add(Instr(OP_SET, d, SET_X, _imm(step) & 31, step.name))
        elif fn == "set_y":
            prog.add(Instr(OP_SET, d, SET_Y, _imm(step) & 31, step.name))
        elif fn == "set_bit":
            prog.add(Instr(OP_SET, d, SET_BIT, _imm(step) & 31, step.name))
        elif fn == "clr_bit":
            prog.add(Instr(OP_SET, d, CLR_BIT, _imm(step) & 31, step.name))
        elif fn == "set_outpin":
            prog.add(Instr(OP_SET, d, SET_OUTPIN, _imm(step) & 7, step.name))
        elif fn == "set_inpin":
            prog.add(Instr(OP_SET, d, SET_INPIN, _imm(step) & 7, step.name))
        elif fn == "wait_pin":
            # inputs: pin, polarity
            pin = 0
            pol = 1
            if len(step.inputs) >= 1:
                pin = int(step.inputs[0].value, 0) & 15
            if len(step.inputs) >= 2:
                pol = int(step.inputs[1].value, 0) & 1
            prog.add(Instr(OP_WAIT, d, 0, (pol << 4) | pin, step.name))
        elif fn == "out_lsb":
            n = _imm(step, 1) & 31
            prog.add(Instr(OP_OUT, d, SHIFT_LSB, n, step.name))
        elif fn == "out_msb":
            n = _imm(step, 1) & 31
            prog.add(Instr(OP_OUT, d, SHIFT_MSB, n, step.name))
        elif fn == "in_lsb":
            n = _imm(step, 1) & 31
            prog.add(Instr(OP_IN, d, SHIFT_LSB, n, step.name))
        elif fn == "in_msb":
            n = _imm(step, 1) & 31
            prog.add(Instr(OP_IN, d, SHIFT_MSB, n, step.name))
        elif fn == "delay":
            prog.add(Instr(OP_NOP, d if d else _imm(step, 0), 0, 0, step.name))
        elif fn == "jmp":
            prog.add(Instr(OP_JMP, d, JMP_ALWAYS, _label(step), step.name))
        elif fn == "jmp_x_dec":
            prog.add(Instr(OP_JMP, d, JMP_X_DEC, _label(step), step.name))
        elif fn == "jmp_y_dec":
            prog.add(Instr(OP_JMP, d, JMP_Y_DEC, _label(step), step.name))
        elif fn == "jmp_x_eq0":
            prog.add(Instr(OP_JMP, d, JMP_X_EQ0, _label(step), step.name))
        elif fn == "jmp_y_eq0":
            prog.add(Instr(OP_JMP, d, JMP_Y_EQ0, _label(step), step.name))
        elif fn == "jmp_pin":
            prog.add(Instr(OP_JMP, d, JMP_PIN, _label(step), step.name))
        elif fn == "mov":
            dest = _reg(step, 0, REG_X)
            src = _reg(step, 1, REG_NULL)
            prog.add(Instr(OP_MOV, d, dest, src, step.name))
        else:
            raise LoomError(f"no compiler for primitive {fn}")
        for i in range(extra):
            prog.add(Instr(OP_NOP, 0, 0, 0, f"{step.name}.pad{i}"))
    return prog
