"""Goblin-engine shaped IR: Primitive ~= Script, Plan of Steps with StepInputs.

Control-flow edges (jmp targets) may form cycles. Data edges must be a DAG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
import tomllib


class LoomError(Exception):
    pass


class InputKind(Enum):
    LITERAL = "literal"
    STEP_REF = "step_ref"  # data dependency
    LABEL = "label"  # control target (jmp)


@dataclass(frozen=True)
class StepInput:
    kind: InputKind
    value: str

    @staticmethod
    def parse(raw: str, step_names: set[str], control: bool) -> "StepInput":
        if control:
            return StepInput(InputKind.LABEL, raw)
        if raw in step_names:
            return StepInput(InputKind.STEP_REF, raw)
        return StepInput(InputKind.LITERAL, raw)


@dataclass
class Primitive:
    """Reusable protocol atom — goblin Script analog."""

    name: str
    description: str = ""
    control: bool = False
    timeout_cycles: int = 0
    require_test: bool = True


PRIMITIVES: dict[str, Primitive] = {
    p.name: p
    for p in (
        Primitive("pull", "Load TX FIFO byte into OSR"),
        Primitive("push", "Store ISR byte into RX FIFO"),
        Primitive("set_pins", "Write low 5 GPIO output bits"),
        Primitive("set_pindirs", "Write low 5 GPIO OE bits"),
        Primitive("set_x", "Load scratch X"),
        Primitive("set_y", "Load scratch Y"),
        Primitive("set_bit", "Set one output bit"),
        Primitive("clr_bit", "Clear one output bit"),
        Primitive("set_outpin", "Select OUT pin index"),
        Primitive("set_inpin", "Select IN/WAIT pin index"),
        Primitive("wait_pin", "Stall until pin == polarity"),
        Primitive("out_lsb", "Drive out-pin from OSR bit 0, then shift toward 0"),
        Primitive("out_msb", "Drive out-pin from OSR bit 7, then shift toward 7"),
        Primitive("in_lsb", "Sample in-pin into ISR using shift-toward-0"),
        Primitive("in_msb", "Sample in-pin into ISR using shift-toward-7"),
        Primitive("delay", "NOP with delay"),
        Primitive("mov", "Copy register"),
        Primitive("jmp", "Unconditional jump", control=True),
        Primitive("jmp_x_dec", "If X!=0: X--, jump", control=True),
        Primitive("jmp_y_dec", "If Y!=0: Y--, jump", control=True),
        Primitive("jmp_x_eq0", "Jump if X==0", control=True),
        Primitive("jmp_y_eq0", "Jump if Y==0", control=True),
        Primitive("jmp_pin", "Jump if pin high", control=True),
    )
}


@dataclass
class Step:
    name: str
    function: str
    inputs: list[StepInput] = field(default_factory=list)
    delay: int = 0
    sideset: int | None = None
    timeout: int | None = None


@dataclass
class Plan:
    name: str
    steps: list[Step]
    description: str = ""
    protocol: str = ""
    direction: str = ""  # encode | decode | both
    sideset_count: int = 0  # 0 = delay is 5 bits; 1 = delay 4 bits + 1 sideset bit
    side_base: int = 0  # GPIO pin driven by sideset when sideset_count=1
    wrap_bottom: int = 0
    wrap_top: int = 31

    def step_names(self) -> set[str]:
        return {s.name for s in self.steps}

    def validate(self) -> None:
        names = [s.name for s in self.steps]
        if len(names) != len(set(names)):
            raise LoomError(f"{self.name}: duplicate step names")
        known = set(names)
        for s in self.steps:
            if s.function not in PRIMITIVES:
                raise LoomError(
                    f"{self.name}.{s.name}: unknown primitive {s.function!r}"
                )
            prim = PRIMITIVES[s.function]
            for inp in s.inputs:
                if inp.kind == InputKind.LABEL and inp.value not in known:
                    raise LoomError(
                        f"{self.name}.{s.name}: missing jump target {inp.value!r}"
                    )
                if inp.kind == InputKind.STEP_REF and inp.value not in known:
                    raise LoomError(
                        f"{self.name}.{s.name}: missing dependency {inp.value!r}"
                    )
            if s.delay < 0:
                raise LoomError(f"{self.name}.{s.name}: negative delay")
            if s.sideset is not None and s.sideset not in (0, 1):
                raise LoomError(f"{self.name}.{s.name}: sideset must be 0 or 1")
            _ = prim
        if self.sideset_count not in (0, 1):
            raise LoomError(f"{self.name}: sideset_count must be 0 or 1")
        if not 0 <= self.wrap_bottom < 32 or not 0 <= self.wrap_top < 32:
            raise LoomError(f"{self.name}: wrap bounds must be 0..31")

        # Data-edge cycle detection (goblin analog). Control edges ignored.
        data_adj: dict[str, list[str]] = {n: [] for n in known}
        for s in self.steps:
            for inp in s.inputs:
                if inp.kind == InputKind.STEP_REF:
                    data_adj[inp.value].append(s.name)
        visiting: set[str] = set()
        seen: set[str] = set()

        def dfs(n: str) -> None:
            if n in visiting:
                raise LoomError(f"{self.name}: circular data dependency at {n}")
            if n in seen:
                return
            visiting.add(n)
            for m in data_adj[n]:
                dfs(m)
            visiting.remove(n)
            seen.add(n)

        for n in known:
            dfs(n)

    @staticmethod
    def from_toml(path: str | Path) -> "Plan":
        path = Path(path)
        with path.open("rb") as f:
            data = tomllib.load(f)
        return Plan.from_dict(data)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "Plan":
        raw_steps = data.get("steps") or []
        names = {s["name"] for s in raw_steps}
        steps: list[Step] = []
        for s in raw_steps:
            fn = s["function"]
            prim = PRIMITIVES.get(fn)
            control = bool(prim.control) if prim else False
            inputs = [
                StepInput.parse(str(x), names, control) for x in s.get("inputs", [])
            ]
            steps.append(
                Step(
                    name=s["name"],
                    function=fn,
                    inputs=inputs,
                    delay=int(s.get("delay", 0)),
                    sideset=int(s["sideset"]) if "sideset" in s else None,
                    timeout=int(s["timeout"]) if "timeout" in s else None,
                )
            )
        plan = Plan(
            name=str(data["name"]),
            steps=steps,
            description=str(data.get("description", "")),
            protocol=str(data.get("protocol", "")),
            direction=str(data.get("direction", "")),
            sideset_count=int(data.get("sideset_count", 0)),
            side_base=int(data.get("side_base", 0)),
            wrap_bottom=int(data.get("wrap_bottom", 0)),
            wrap_top=int(data.get("wrap_top", 31)),
        )
        plan.validate()
        return plan
