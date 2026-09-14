"""Infer wire timing and emit a matching RX graph. Correction is in the graph, not the ISA."""

from __future__ import annotations

from loom.ir import Plan


def bit_runs(pin: list[int]) -> list[tuple[int, int]]:
    if not pin:
        return []
    out: list[tuple[int, int]] = []
    v, n = pin[0] & 1, 1
    for b in pin[1:]:
        b &= 1
        if b == v:
            n += 1
        else:
            out.append((v, n))
            v, n = b, 1
    out.append((v, n))
    return out


def infer_uart_bit_cycles(pin: list[int]) -> int:
    """Mode of inter-edge gaps. Use a payload with transitions (e.g. 0x55)."""
    bits = [b & 1 for b in pin]
    edges = [i for i in range(1, len(bits)) if bits[i] != bits[i - 1]]
    gaps = [b - a for a, b in zip(edges, edges[1:])]
    if not gaps:
        raise ValueError("no edges")
    counts: dict[int, int] = {}
    for g in gaps:
        counts[g] = counts.get(g, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


def uart_rx_dict(bit_cycles: int) -> dict:
    if bit_cycles < 4:
        raise ValueError("bit time too small")
    # wait consumes the first low cycle; then delay to first-data center;
    # each data bit is sample+(bit_cycles-2) plus a 1-cycle jump.
    to_first = bit_cycles + bit_cycles // 2 - 3
    sample_delay = bit_cycles - 2
    return {
        "name": f"uart_rx_{bit_cycles}",
        "description": "8N1 decode retuned to measured bit time",
        "protocol": "uart",
        "direction": "decode",
        "steps": [
            {"name": "wait_start", "function": "wait_pin", "inputs": ["0", "0"]},
            {"name": "to_first", "function": "delay", "delay": to_first},
            {"name": "count", "function": "set_x", "inputs": ["7"]},
            {
                "name": "sample",
                "function": "in_lsb",
                "inputs": ["1"],
                "delay": sample_delay,
            },
            {"name": "next_bit", "function": "jmp_x_dec", "inputs": ["sample"]},
            {"name": "store", "function": "push"},
            {"name": "again", "function": "jmp", "inputs": ["wait_start"]},
        ],
    }


def uart_rx_plan(bit_cycles: int) -> Plan:
    return Plan.from_dict(uart_rx_dict(bit_cycles))
