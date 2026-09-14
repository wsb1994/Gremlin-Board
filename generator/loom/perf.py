"""Cycle cost of a graph: each node is 1 cycle plus its delay field.

No protocol has a hidden tax in the engine. Timing is whatever the graph
asks for. Used to judge whether a plan is fast enough before RTL.
"""

from __future__ import annotations

from loom.compile import compile_plan
from loom.ir import Plan
from loom.isa import IMEM_WORDS, decode


def assembled_words(plan: Plan) -> list[int]:
    return compile_plan(plan).assemble()


def instruction_count(plan: Plan) -> int:
    return len(assembled_words(plan))


def fits_onchip_imem(plan: Plan) -> bool:
    return instruction_count(plan) <= IMEM_WORDS


def static_cycle_lower_bound(plan: Plan) -> int:
    """Sum of (1 + delay) over straight-line nodes; ignores taken loops."""
    total = 0
    for w in assembled_words(plan):
        _op, delay, _field, _payload = decode(w)
        total += 1 + delay
    return total
