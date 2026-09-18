"""Yosys generic synth area estimate for the CMOS5L 8x4 Tiny Tapeout die.

Not a PDK map, not LibreLane P&R, not GDS. Timing is unknown without liberty.
Prefers `yosys` on PATH; otherwise `docker run hdlc/yosys`. amaranth-yosys
(wasm) has no read_verilog/synth/stat and is not used for this estimate.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = ROOT / "estimates"
TOP = "tt_um_loom_gpe"
SOURCES = ("src/project.v", "src/loom_engine.v", "src/macros/RM_IHPSG13_2P_256x16_c2_bm_bist.v")
TILES = "6x4"
TILE_COUNT = 24
CELL_BUDGET = 32_000
CELL_MARGIN = 24_000
CLOCK_NS = 20
DOCKER_IMAGE = "hdlc/yosys"

YOSYS_SCRIPT = f"""
read_verilog -sv src/project.v
read_verilog src/loom_engine.v
read_verilog src/macros/RM_IHPSG13_2P_256x16_c2_bm_bist.v
hierarchy -check -top {TOP}
synth -top {TOP} -flatten
stat
stat -tech cmos
stat -json
"""


def _yosys_invocation() -> tuple[list[str], str]:
    yosys = shutil.which("yosys")
    if yosys:
        return [yosys, "-p", YOSYS_SCRIPT], f"{yosys} -p <script>"
    docker = shutil.which("docker")
    if docker:
        return (
            [
                docker,
                "run",
                "--rm",
                "-v",
                f"{ROOT}:/work",
                "-w",
                "/work",
                DOCKER_IMAGE,
                "yosys",
                "-p",
                YOSYS_SCRIPT,
            ],
            f"docker run --rm -v {ROOT}:/work -w /work {DOCKER_IMAGE} yosys -p <script>",
        )
    sys.exit(
        "no yosys on PATH and no docker; amaranth-yosys wasm cannot synth "
        "(no read_verilog/synth/stat)"
    )


def _last_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    last = None
    i = 0
    while True:
        j = text.find("{", i)
        if j < 0:
            break
        try:
            obj, end = decoder.raw_decode(text, j)
            last = obj
            i = j + end
        except json.JSONDecodeError:
            i = j + 1
    if not isinstance(last, dict):
        raise RuntimeError("yosys output contained no JSON object from stat -json")
    return last


def _pdk_blockers() -> list[str]:
    blockers = []
    if not shutil.which("librelane") and not shutil.which("openlane"):
        blockers.append("LibreLane/OpenLane not on PATH")
    pdk_root = os.environ.get("PDK_ROOT") or os.environ.get("PDK")
    if not pdk_root:
        blockers.append("PDK_ROOT/PDK unset; IHP sg13cmos5l liberty not present")
    else:
        pdk = Path(pdk_root)
        if not pdk.exists():
            blockers.append(f"PDK_ROOT={pdk_root} does not exist")
        else:
            hits = list(pdk.glob("**/*sg13cmos5l*"))[:1]
            if not hits:
                blockers.append(f"no sg13cmos5l files under {pdk_root}")
    blockers.append("CMOS5L P&R/STA/GDS not run (not faked)")
    return blockers


def run_synth() -> tuple[dict, str]:
    for rel in SOURCES:
        path = ROOT / rel
        if not path.is_file():
            sys.exit(f"missing {rel}; run PYTHONPATH=generator .venv/bin/python -m loom.emit")
    cmd, cmd_summary = _yosys_invocation()
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True)
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if proc.returncode != 0:
        sys.stderr.write(text[-8000:])
        sys.exit(f"yosys failed with exit {proc.returncode}")
    blob = _last_json_object(text)
    design = blob.get("design") or next(iter(blob.get("modules", {}).values()), {})
    cells_by_type = design.get("num_cells_by_type") or {}
    num_cells = int(design.get("num_cells") or 0)
    if num_cells <= 0:
        raise RuntimeError("yosys reported zero cells; refusing to write an estimate")
    seq = sum(n for name, n in cells_by_type.items() if "DFF" in name)
    trans_m = re.search(r"Estimated number of transistors:\s+(\d+)(\+?)", text)
    transistors = int(trans_m.group(1)) if trans_m else None
    trans_plus = bool(trans_m and trans_m.group(2) == "+")
    ver_m = re.search(r"Yosys (\d+\.\d+\S*(?:\s+\([^)]+\))?)", text)
    nand2_eq_combo = round(transistors / 4, 1) if transistors is not None else None
    under_margin = num_cells < CELL_MARGIN
    report = {
        "top": TOP,
        "sources": list(SOURCES),
        "tiles": TILES,
        "tile_count": TILE_COUNT,
        "cell_budget": CELL_BUDGET,
        "cell_margin": CELL_MARGIN,
        "clock_period_ns": CLOCK_NS,
        "clock_hz_target": 50_000_000,
        "yosys_version": ver_m.group(1).strip() if ver_m else "unknown",
        "yosys_command": cmd_summary,
        "yosys_script": YOSYS_SCRIPT.strip(),
        "mapping": "generic Yosys synth -flatten (not CMOS5L standard cells)",
        "num_cells": num_cells,
        "num_sequential": seq,
        "num_combo": num_cells - seq,
        "cells_by_type": cells_by_type,
        "cmos_transistor_estimate": transistors,
        "cmos_transistor_estimate_incomplete": trans_plus,
        "nand2_eq_combo": nand2_eq_combo,
        "nand2_eq_note": (
            "Yosys stat -tech cmos transistors/4 for combinational gates; "
            "the trailing + means sequential cells are not in that transistor count"
        ),
        "under_24k_margin": under_margin,
        "timing_50mhz": "unknown",
        "gds": False,
        "blockers": _pdk_blockers(),
    }
    return report, text


def _txt(report: dict) -> str:
    cells = report["num_cells"]
    nand = report["nand2_eq_combo"]
    trans = report["cmos_transistor_estimate"]
    trans_s = f"{trans}+" if report["cmos_transistor_estimate_incomplete"] else str(trans)
    lines = [
        "CMOS5L 8x4 area/timing estimate (generic Yosys, not PDK P&R)",
        f"top {report['top']}",
        f"sources {' '.join(report['sources'])}",
        f"tiles {report['tiles']} ({report['tile_count']} tiles, "
        f"~{report['cell_budget']} cell budget, ~{report['cell_margin']} with CTS/route margin)",
        f"yosys {report['yosys_version']}",
        f"command {report['yosys_command']}",
        f"mapping {report['mapping']}",
        "",
        f"cells {cells}",
        f"sequential {report['num_sequential']}",
        f"combo {report['num_combo']}",
        f"yosys_cmos_transistors {trans_s}",
        f"nand2_eq_combo {nand}  # transistors/4, combo only",
        f"under_24k_margin {str(report['under_24k_margin']).lower()}  "
        f"({cells} {'<' if report['under_24k_margin'] else '>='} {report['cell_margin']})",
        "",
        "cells_by_type",
    ]
    for name, n in sorted(report["cells_by_type"].items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"  {name} {n}")
    lines += [
        "",
        f"CLOCK_PERIOD target {report['clock_period_ns']} ns ({report['clock_hz_target'] // 1_000_000} MHz)",
        "timing_50mhz unknown  # no liberty, no STA, no P&R",
        "gds not produced (not faked)",
        "",
        "blockers",
        *[f"  - {b}" for b in report["blockers"]],
        "",
        report["nand2_eq_note"],
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    report, _log = run_synth()
    OUT.mkdir(exist_ok=True)
    (OUT / "synth.json").write_text(json.dumps(report, indent=2) + "\n")
    (OUT / "synth.txt").write_text(_txt(report))
    print(f"cells {report['num_cells']}")
    print(f"nand2_eq_combo {report['nand2_eq_combo']}")
    print(f"under_24k_margin {report['under_24k_margin']}")
    print(f"timing {report['timing_50mhz']}")
    print(OUT / "synth.txt")
    print(OUT / "synth.json")


if __name__ == "__main__":
    main()
