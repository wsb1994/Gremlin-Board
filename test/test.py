# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# plans/uart_tx.toml assembled (idle, drive, pull, count, start, bit, next, stop, again)
UART_TX = [0xC001, 0xC021, 0x8020, 0xC047, 0xC700, 0x6601, 0x0065, 0xC701, 0x0002]


async def _pulse_ui(dut, ui, uio, high=1):
    dut.ui_in.value = ui
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, high)
    dut.ui_in.value = ui & ~0x82  # drop strobes 1 and 7
    await ClockCycles(dut.clk, 1)


async def _load_word(dut, addr, word):
    ui = ((addr & 0x1F) << 2) | 0x02
    await _pulse_ui(dut, ui, word & 0xFF)
    await _pulse_ui(dut, ui, (word >> 8) & 0xFF)


@cocotb.test()
async def test_project(dut):
    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)
    # Engine idle: run=0, outputs driven.
    assert int(dut.uo_out.value) & 1 == 0
    assert int(dut.uio_oe.value) == 0

    # ena=0: ignore run, keep pads off
    dut.ena.value = 0
    dut.ui_in.value = 1
    await ClockCycles(dut.clk, 2)
    assert int(dut.uio_oe.value) == 0
    dut.ena.value = 1
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 2)

    # SET_BIT pin0 = 0xC080. Two-phase imem write at addr 0, then run.
    await _load_word(dut, 0, 0xC080)
    await ClockCycles(dut.clk, 2)  # preload
    dut.ui_in.value = 1  # run
    await ClockCycles(dut.clk, 6)
    assert int(dut.uo_out.value) & 1 == 1
    assert int(dut.uio_oe.value) & 1 == 1
    assert int(dut.uio_out.value) & 1 == 1

    # Re-halt, load UART TX graph, push 'H', run until start bit on pin0.
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
    for i, w in enumerate(UART_TX):
        await _load_word(dut, i, w)
    await _pulse_ui(dut, 0x80, 0x48)  # TX push 'H'
    await ClockCycles(dut.clk, 2)
    dut.ui_in.value = 1
    saw_start = False
    for _ in range(40):
        await ClockCycles(dut.clk, 1)
        if int(dut.uio_oe.value) & 1 and (int(dut.uio_out.value) & 1) == 0:
            saw_start = True
            break
    assert saw_start, "UART TX never drove pin0 start-bit low"
