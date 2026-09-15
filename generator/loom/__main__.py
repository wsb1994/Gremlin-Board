"""CLI: emit, check, plans, synth, formal."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def cmd_emit(_args: argparse.Namespace) -> int:
    from loom.emit import emit

    print(emit())
    print(ROOT / "src" / "loom_engine.v")
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    from loom.criteria import assert_criteria

    assert_criteria()
    print("criteria ok: engine core names no protocol")
    return 0


def cmd_plans(_args: argparse.Namespace) -> int:
    for p in sorted((ROOT / "plans").glob("*.toml")):
        print(p.stem)
    return 0


def cmd_synth(_args: argparse.Namespace) -> int:
    import runpy

    runpy.run_path(str(ROOT / "scripts" / "synth_area.py"), run_name="__main__")
    return 0


def cmd_formal(_args: argparse.Namespace) -> int:
    from loom.formal import main as formal_main

    return formal_main()


def cmd_formal_proto(_args: argparse.Namespace) -> int:
    from loom.formal_proto import main as proto_main

    return proto_main()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="loom",
        description="Graph protocol engine: compile plans, emit Tiny Tapeout Verilog.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("emit", help="write src/loom_engine.v and src/project.v")
    sub.add_parser("check", help="engine-core criteria")
    sub.add_parser("plans", help="list protocol graphs")
    sub.add_parser("synth", help="generic Yosys area estimate")
    sub.add_parser("formal", help="k-induction proof of ISA step semantics + FIFO invariants")
    sub.add_parser(
        "formal-proto",
        help="protocol completeness: all 256 bytes, TX encoding + RX spec + round-trip + loop",
    )
    args = parser.parse_args(argv)
    fn = {
        "emit": cmd_emit,
        "check": cmd_check,
        "plans": cmd_plans,
        "synth": cmd_synth,
        "formal": cmd_formal,
        "formal-proto": cmd_formal_proto,
    }[args.cmd]
    sys.exit(fn(args))


if __name__ == "__main__":
    main()
