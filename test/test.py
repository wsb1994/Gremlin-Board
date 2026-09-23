# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

"""Tiny Tapeout wrapper tests. Run on RTL (make -B) or the hardened
netlist (make -B GATES=yes). The UART test is real protocol traffic:
SM0 encodes on pin0, the bench loops pin0 back, SM1 decodes, host pops."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge, RisingEdge

# plans/uart_tx.toml assembled (idle, drive, pull, count, start, bit, next, stop, again)
UART_TX = [0xC001, 0xC021, 0x8020, 0xC047, 0xC700, 0x6601, 0x0065, 0xC701, 0x0002]
# plans/uart_rx.toml assembled (sync, wait_start, to_first, count, sample, next, store, again)
UART_RX = [0x2010, 0x2000, 0xE900, 0xC047, 0x4601, 0x0064, 0x8000, 0x0001]

CSR_WRITE_SLOT = 0
CSR_SM1_SLOT = 2
CSR_FIFO_SEL = 9

PAYLOAD = b"Hi"


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


async def _csr(dut, addr, data):
    await _pulse_ui(dut, ((addr & 0x1F) << 2) | 0x82, data)


async def _tx_push(dut, byte):
    await _pulse_ui(dut, 0x80, byte)


async def _rx_pop(dut):
    dut.ui_in.value = 0x04  # halt, ui_in[2]=1: uo_out is the FIFO head
    await ClockCycles(dut.clk, 1)
    head = int(dut.uo_out.value)
    await _pulse_ui(dut, 0x84, 0)
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, 1)
    return head


async def _reset(dut):
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


def _pin(dut, n):
    """Pad level of uio[n]: driven value if OE, else pull-up."""
    oe = int(dut.uio_oe.value) >> n & 1
    return (int(dut.uio_out.value) >> n & 1) if oe else 1


async def _loopback(dut, trace):
    """External pad model: every uio bit is wired to itself with a pull-up.
    Also records pin0 once per clock for host-side decoding."""
    while True:
        await FallingEdge(dut.clk)
        oe = int(dut.uio_oe.value)
        out = int(dut.uio_out.value)
        dut.uio_in.value = (out & oe) | (~oe & 0xFF)
        trace.append(_pin(dut, 0))


def _decode_8n1(trace):
    """Decode 8N1 frames from a per-clock pin trace. The bit period is the
    shortest run of a constant level (single-bit runs exist in every byte
    of the payload)."""
    runs = []
    lvl, n = trace[0], 0
    for v in trace:
        if v == lvl:
            n += 1
        else:
            runs.append((lvl, n))
            lvl, n = v, 1
    runs.append((lvl, n))
    period = min(n for _, n in runs[1:-1]) if len(runs) > 2 else 0
    assert period >= 2, f"no UART activity on pin0 (runs={runs[:8]})"
    out = []
    i = 1
    while i < len(trace):
        if trace[i - 1] == 1 and trace[i] == 0:  # falling edge: start bit
            centre = i + period // 2
            bits = [trace[centre + k * period] for k in range(1, 9) if centre + k * period < len(trace)]
            stop_at = centre + 9 * period
            if len(bits) < 8 or stop_at >= len(trace):
                break
            assert trace[stop_at] == 1, f"bad stop bit at {stop_at}"
            out.append(sum(b << k for k, b in enumerate(bits)))
            i = stop_at
        else:
            i += 1
    return bytes(out), period


@cocotb.test()
async def test_project(dut):
    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())
    await _reset(dut)
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
    await _tx_push(dut, 0x48)
    await ClockCycles(dut.clk, 2)
    dut.ui_in.value = 1
    saw_start = False
    for _ in range(40):
        await ClockCycles(dut.clk, 1)
        if int(dut.uio_oe.value) & 1 and (int(dut.uio_out.value) & 1) == 0:
            saw_start = True
            break
    assert saw_start, "UART TX never drove pin0 start-bit low"


@cocotb.test()
async def test_uart_loopback(dut):
    """Full UART traffic through the wrapper: host loads uart_tx into slot 0
    (SM0) and uart_rx into slot 1 (SM1), pushes PAYLOAD, runs, and pops the
    decoded bytes back from SM1's RX FIFO. The bench wires pin0 to itself
    and independently decodes the pin0 waveform as 8N1."""
    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())
    await _reset(dut)

    for i, w in enumerate(UART_TX):
        await _load_word(dut, i, w)
    await _csr(dut, CSR_WRITE_SLOT, 1)
    for i, w in enumerate(UART_RX):
        await _load_word(dut, i, w)
    await _csr(dut, CSR_SM1_SLOT, 1)
    for b in PAYLOAD:
        assert int(dut.uo_out.value) & 0x02 == 0, "tx_full before push"
        await _tx_push(dut, b)
    await ClockCycles(dut.clk, 2)

    trace = []
    lb = cocotb.start_soon(_loopback(dut, trace))
    dut.ui_in.value = 1  # run both SMs
    # 10 bits x ~8 clocks per byte, plus sync/turnaround slack.
    await ClockCycles(dut.clk, 120 * len(PAYLOAD) + 200)
    dut.ui_in.value = 0  # halt; FIFOs and imem survive
    await ClockCycles(dut.clk, 4)
    lb.cancel()

    decoded, period = _decode_8n1(trace)
    dut._log.info(f"pin0 8N1 host-side decode: {decoded!r} (bit period {period} clk)")
    assert decoded == PAYLOAD, f"pin0 waveform decoded {decoded!r}, want {PAYLOAD!r}"

    await _csr(dut, CSR_FIFO_SEL, 1)  # host talks to SM1's FIFOs
    got = bytearray()
    for _ in PAYLOAD:
        assert int(dut.uo_out.value) & 0x04 == 0, f"rx_empty after {bytes(got)!r}"
        got.append(await _rx_pop(dut))
    assert int(dut.uo_out.value) & 0x04, "RX FIFO not empty after popping the payload"
    dut._log.info(f"SM1 RX FIFO popped by host: {bytes(got)!r}")
    assert bytes(got) == PAYLOAD, f"SM1 decoded {bytes(got)!r}, want {PAYLOAD!r}"
