"""Amaranth RTL stream round-trip for representative payloads."""

from pathlib import Path

import pytest
from amaranth import Elaboratable, Module
from amaranth.sim import Simulator

from loom.rtl import GraphEngine
from loom.stream import load_graph

from payloads import PAYLOADS, PROTOCOLS

PLANS = Path(__file__).resolve().parents[1] / "plans"

# Full matrix is interpreter-tested. RTL covers one of each class.
RTL_NAMES = ("hello", "png_1x1", "gif_1x1", "json_nbbo", "packed_tick")


def _stream_rtl(tx_words, rx_words, payload: bytes) -> bytes:
    tx = GraphEngine()
    rx = GraphEngine()

    class Couple(Elaboratable):
        def elaborate(self, platform):
            m = Module()
            m.submodules.tx = tx
            m.submodules.rx = rx
            m.d.comb += rx.gpio_in.eq(tx.gpio_out)
            return m

    dut = Couple()
    got: list[int] = []
    src = list(payload)
    limit = 64 + len(payload) * 120

    async def tb(ctx):
        ctx.set(tx.run, 0)
        ctx.set(rx.run, 0)
        for i, w in enumerate(tx_words):
            ctx.set(tx.imem_waddr, i)
            ctx.set(tx.imem_wdata, w)
            ctx.set(tx.imem_we, 1)
            await ctx.tick()
        ctx.set(tx.imem_we, 0)
        for i, w in enumerate(rx_words):
            ctx.set(rx.imem_waddr, i)
            ctx.set(rx.imem_wdata, w)
            ctx.set(rx.imem_we, 1)
            await ctx.tick()
        ctx.set(rx.imem_we, 0)
        ctx.set(tx.run, 1)
        ctx.set(rx.run, 1)
        idle = 0
        pop = 0
        for _ in range(limit):
            if src and ctx.get(tx.tx_full) == 0:
                ctx.set(tx.tx_data, src.pop(0))
                ctx.set(tx.tx_we, 1)
            else:
                ctx.set(tx.tx_we, 0)
            ctx.set(rx.rx_re, pop)
            await ctx.tick()
            pop = 0
            if ctx.get(rx.rx_empty) == 0:
                got.append(ctx.get(rx.rx_data))
                pop = 1
                idle = 0
            else:
                idle += 1
            if not src and len(got) >= len(payload) and idle > 64:
                break
            if idle > 512 and len(got) >= len(payload):
                break

    sim = Simulator(dut)
    sim.add_clock(1e-6)
    sim.add_testbench(tb)
    sim.run()
    return bytes(got)


@pytest.mark.parametrize("proto", PROTOCOLS)
@pytest.mark.parametrize("name", RTL_NAMES)
def test_rtl_stream_roundtrip(proto: str, name: str):
    payload = PAYLOADS[name]
    tx = load_graph(PLANS / f"{proto}_tx.toml")
    rx = load_graph(PLANS / f"{proto}_rx.toml")
    got = _stream_rtl(tx, rx, payload)
    assert got == payload, (proto, name, got[:24], payload[:24])
