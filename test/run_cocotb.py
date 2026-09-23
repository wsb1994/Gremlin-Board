"""Run the wrapper cocotb tests without make (cocotb >= 2 runner API).

    python3 test/run_cocotb.py            # RTL
    GATES=yes PDK_ROOT=... python3 test/run_cocotb.py   # hardened netlist
"""
import os
from pathlib import Path

from cocotb_tools.runner import get_runner

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
SRAM = SRC / "macros" / "RM_IHPSG13_2P_256x16_c2_bm_bist.v"
gates = os.environ.get("GATES") == "yes"

if gates:
    pdk = Path(os.environ["PDK_ROOT"]) / "ihp-sg13cmos5l" / "libs.ref"
    sources = [
        pdk / "sg13cmos5l_io/verilog/sg13cmos5l_io.v",
        pdk / "sg13cmos5l_stdcell/verilog/sg13cmos5l_udp.v",
        pdk / "sg13cmos5l_stdcell/verilog/sg13cmos5l_stdcell.v",
        HERE / "gate_level_netlist.v",
        SRAM,
    ]
    defines = {"GL_TEST": 1, "FUNCTIONAL": 1, "SIM": 1}
else:
    sources = [SRC / "loom_engine.v", SRC / "project.v", SRAM]
    defines = {}
sources.append(HERE / "tb.v")

runner = get_runner("icarus")
runner.build(
    sources=sources,
    hdl_toplevel="tb",
    defines=defines,
    includes=[SRC],
    build_dir=HERE / "sim_build" / ("gl" if gates else "rtl"),
    always=True,
)
runner.test(hdl_toplevel="tb", test_module="test", test_dir=HERE, waves=False)
