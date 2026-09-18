"""Clocked instruction memory: 1-cycle read, next_pc addressing.

IHP 2-port SRAM timing: ADDR this posedge, DOUT that word on the next posedge.
4 slots × 32 words = 128 × 16. The 1-SM formal engine keeps combinational FF
fetch; only the 2-SM / 4-slot chip uses this path so the decode is not sitting
on a 128:1 mux.

`use_macro=True` instantiates `RM_IHPSG13_2P_256x16_c2_bm_bist` (emit/GDS).
Python tests keep the Array model (same 1-cycle contract, write-through).
"""

from __future__ import annotations

from amaranth import Array, Cat, ClockSignal, Const, Elaboratable, Instance, Module, Mux, Signal

SRAM_NAME = "RM_IHPSG13_2P_256x16_c2_bm_bist"


class ClockedImem(Elaboratable):
    """128 × 16, two read ports, one write port, registered DOUT."""

    DEPTH = 128

    def __init__(self, use_macro: bool = False) -> None:
        self.use_macro = use_macro
        self.w_en = Signal()
        self.w_addr = Signal(7)
        self.w_data = Signal(16)
        self.a_addr = Signal(7)
        self.a_data = Signal(16)
        self.b_addr = Signal(7)
        self.b_data = Signal(16)

    def elaborate(self, platform) -> Module:
        m = Module()
        if self.use_macro:
            a_addr8 = Cat(Mux(self.w_en, self.w_addr, self.a_addr), Const(0, 1))
            b_addr8 = Cat(self.b_addr, Const(0, 1))
            ones16 = Const(0xFFFF, 16)
            zero16 = Const(0, 16)
            m.submodules.imem_sram = Instance(
                SRAM_NAME,
                i_A_CLK=ClockSignal(),
                i_A_MEN=Const(1, 1),
                i_A_WEN=self.w_en,
                i_A_REN=~self.w_en,
                i_A_ADDR=a_addr8,
                i_A_DIN=self.w_data,
                i_A_DLY=Const(1, 1),
                o_A_DOUT=self.a_data,
                i_A_BM=ones16,
                i_A_BIST_CLK=Const(0, 1),
                i_A_BIST_EN=Const(0, 1),
                i_A_BIST_MEN=Const(0, 1),
                i_A_BIST_WEN=Const(0, 1),
                i_A_BIST_REN=Const(0, 1),
                i_A_BIST_ADDR=Const(0, 8),
                i_A_BIST_DIN=zero16,
                i_A_BIST_BM=ones16,
                i_B_CLK=ClockSignal(),
                i_B_MEN=Const(1, 1),
                i_B_WEN=Const(0, 1),
                i_B_REN=Const(1, 1),
                i_B_ADDR=b_addr8,
                i_B_DIN=zero16,
                i_B_DLY=Const(1, 1),
                o_B_DOUT=self.b_data,
                i_B_BM=ones16,
                i_B_BIST_CLK=Const(0, 1),
                i_B_BIST_EN=Const(0, 1),
                i_B_BIST_MEN=Const(0, 1),
                i_B_BIST_WEN=Const(0, 1),
                i_B_BIST_REN=Const(0, 1),
                i_B_BIST_ADDR=Const(0, 8),
                i_B_BIST_DIN=zero16,
                i_B_BIST_BM=ones16,
            )
            return m

        mem = Array(Signal(16, name=f"iw{i}") for i in range(self.DEPTH))
        self.dbg_mem = mem
        with m.If(self.w_en):
            m.d.sync += mem[self.w_addr].eq(self.w_data)
        a_next = Mux(self.w_en & (self.w_addr == self.a_addr), self.w_data, mem[self.a_addr])
        b_next = Mux(self.w_en & (self.w_addr == self.b_addr), self.w_data, mem[self.b_addr])
        m.d.sync += self.a_data.eq(a_next)
        m.d.sync += self.b_data.eq(b_next)
        return m
