"""The CMOS5L synth estimate files exist. Does not re-run Yosys."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_synth_report_exists():
    txt = ROOT / "estimates" / "synth.txt"
    js = ROOT / "estimates" / "synth.json"
    assert txt.is_file(), txt
    assert js.is_file(), js
    assert txt.stat().st_size > 0
    assert js.stat().st_size > 0
