#!/usr/bin/env python3
"""Dump engine pin traces and decode them with sigrok-cli.

The engine only toggles pins. sigrok-cli is the protocol decoder.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generator"))

from loom.compile import compile_plan  # noqa: E402
from loom.interp import Engine  # noqa: E402
from loom.ir import Plan  # noqa: E402
from loom.vcd import write_vcd  # noqa: E402

PLANS = ROOT / "plans"
OUT = ROOT / "traces"
HELLO = b"Hi"
CYCLES = 500
# 1 us / engine cycle, UART bit = 8 cycles → 125000 baud
BAUD = 125000
IMAGE = "debian:bookworm-slim"


def assemble(name: str) -> list[int]:
    return compile_plan(Plan.from_toml(PLANS / name)).assemble()


def tx_trace(plan: str, payload: bytes = HELLO) -> list[int]:
    eng = Engine()
    eng.load(assemble(plan))
    for b in payload:
        eng.sm.tx.push(b)
    eng.run_cycles(CYCLES)
    return eng.trace_out


def dump() -> dict[str, Path]:
    uart = tx_trace("uart_tx.toml")
    spi = tx_trace("spi_tx.toml")
    i2c = tx_trace("i2c_tx.toml")
    files = {
        "uart": write_vcd(
            OUT / "uart_hi.vcd",
            {"TX": [t & 1 for t in uart]},
        ),
        "spi": write_vcd(
            OUT / "spi_hi.vcd",
            {
                "MOSI": [t & 1 for t in spi],
                "SCK": [(t >> 1) & 1 for t in spi],
                "CS": [0] * len(spi),
            },
        ),
        "i2c": write_vcd(
            OUT / "i2c_hi.vcd",
            {
                "SDA": [t & 1 for t in i2c],
                "SCL": [(t >> 1) & 1 for t in i2c],
            },
        ),
    }
    (OUT / "uart_hi.txt").write_text(_bits("TX", [t & 1 for t in uart]))
    (OUT / "spi_hi.txt").write_text(
        _bits("MOSI", [t & 1 for t in spi])
        + _bits("SCK", [(t >> 1) & 1 for t in spi])
    )
    (OUT / "i2c_hi.txt").write_text(
        _bits("SDA", [t & 1 for t in i2c])
        + _bits("SCL", [(t >> 1) & 1 for t in i2c])
    )
    return files


def _bits(name: str, bits: list[int], width: int = 120) -> str:
    s = "".join("█" if b else "·" for b in bits[:width])
    return f"{name:4s} {s}\n"


def sigrok(files: dict[str, Path]) -> None:
    work = "/work"
    cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{ROOT}:{work}",
        "-w",
        work,
        IMAGE,
        "bash",
        "-lc",
        f"""
set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq sigrok-cli >/tmp/apt.log
echo '======== UART (125000 8N1) ========'
sigrok-cli -i {work}/traces/uart_hi.vcd -I vcd \\
  -P uart:rx=TX:baudrate={BAUD}:format=ascii \\
  -A uart=rx-data
echo
echo '======== SPI mode 0 ========'
sigrok-cli -i {work}/traces/spi_hi.vcd -I vcd \\
  -P spi:clk=SCK:mosi=MOSI:cs=CS:cpol=0:cpha=0 \\
  -A spi=mosi-data
echo
echo '======== I2C ========'
sigrok-cli -i {work}/traces/i2c_hi.vcd -I vcd \\
  -P i2c:scl=SCL:sda=SDA
""",
    ]
    print("running sigrok-cli in", IMAGE, flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    files = dump()
    for k, p in files.items():
        print(f"wrote {p}")
    print()
    print((OUT / "uart_hi.txt").read_text(), end="")
    print((OUT / "spi_hi.txt").read_text(), end="")
    print((OUT / "i2c_hi.txt").read_text(), end="")
    print()
    sigrok(files)


if __name__ == "__main__":
    main()
