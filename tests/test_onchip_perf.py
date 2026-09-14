"""On-chip rate estimates from measured interpreter cycles at 50 MHz."""

from __future__ import annotations

import json
from pathlib import Path

from loom.stream import load_graph, roundtrip

from payloads import PAYLOADS, PROTOCOLS

PLANS = Path(__file__).resolve().parents[1] / "plans"
OUT = Path(__file__).resolve().parents[1] / "estimates"
CLK_HZ = 50_000_000
PERIOD_NS = 20


def _row(proto: str, name: str, payload: bytes) -> dict:
    tx = load_graph(PLANS / f"{proto}_tx.toml")
    rx = load_graph(PLANS / f"{proto}_rx.toml")
    got, cycles = roundtrip(tx, rx, payload)
    assert got == payload
    sec = cycles / CLK_HZ
    bits = len(payload) * 8
    return {
        "protocol": proto,
        "payload": name,
        "bytes": len(payload),
        "cycles": cycles,
        "ns": cycles * PERIOD_NS,
        "Mbps": round(bits / sec / 1e6, 4) if sec else 0,
        "kBps": round(len(payload) / sec / 1e3, 3) if sec else 0,
        "ns_per_byte": round(cycles * PERIOD_NS / len(payload), 1),
    }


def test_onchip_estimates(tmp_path=None):
    rows = [
        _row(p, n, b) for p in PROTOCOLS for n, b in sorted(PAYLOADS.items())
    ]
    OUT.mkdir(exist_ok=True)
    (OUT / "onchip.json").write_text(json.dumps(rows, indent=2))
    lines = [
        "protocol payload bytes cycles ns Mbps kBps ns_per_byte",
        *[
            f"{r['protocol']} {r['payload']} {r['bytes']} {r['cycles']} "
            f"{r['ns']} {r['Mbps']} {r['kBps']} {r['ns_per_byte']}"
            for r in rows
        ],
        "",
        "Clock assumption: 50 MHz (Tiny Tapeout CLOCK_PERIOD 20 ns), unproven P&R.",
        "Primary HFT feeds (10/25/100GbE) do not fit this pin engine.",
        "This path is sideband: config, snapshots, JSON control, image debug.",
    ]
    (OUT / "onchip.txt").write_text("\n".join(lines) + "\n")
    uart_nbbo = next(
        r for r in rows if r["protocol"] == "uart" and r["payload"] == "json_nbbo"
    )
    assert uart_nbbo["cycles"] > 0
    assert uart_nbbo["Mbps"] > 0
    assert uart_nbbo["Mbps"] < 10  # sanity: not a 10G NIC
