"""Serialize a protocol graph the same way goblin serializes a plan.

The blob is what a memory chip, SD card, or USB host would store.
The engine does not care which medium held it.
"""

from __future__ import annotations

import json

from loom.ir import Plan


def graph_to_dict(plan: Plan) -> dict:
    return {
        "name": plan.name,
        "description": plan.description,
        "protocol": plan.protocol,
        "direction": plan.direction,
        "steps": [
            {
                "name": s.name,
                "function": s.function,
                "inputs": [i.value for i in s.inputs],
                "delay": s.delay,
                **({"timeout": s.timeout} if s.timeout is not None else {}),
            }
            for s in plan.steps
        ],
    }


def dumps(plan: Plan) -> bytes:
    return json.dumps(graph_to_dict(plan), separators=(",", ":")).encode("utf-8")


def loads(blob: bytes) -> Plan:
    data = json.loads(blob.decode("utf-8"))
    return Plan.from_dict(data)


def node_count(plan: Plan) -> int:
    return len(plan.steps)
