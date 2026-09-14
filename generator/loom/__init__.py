"""Loom graph protocol engine.

A protocol is a graph of pin/time nodes (goblin-engine shaped Plan/Step).
The executor is protocol-agnostic. UART, SPI, and I2C are graphs in plans/.

Verilog is gated on generator/loom/criteria.py — do not emit RTL until
those checks and the interpreter hello-world tests pass.
"""

from loom.criteria import assert_criteria
from loom.compile import compile_plan
from loom.ir import Plan
from loom.interp import Engine as InterpEngine

__all__ = ["Plan", "compile_plan", "InterpEngine", "assert_criteria"]
