"""Clock-divider helpers. Graphs stay baud-agnostic; the SM cycle is 1/clkdiv of clk."""

from __future__ import annotations


def clkdiv(sys_hz: int, baud: int, cycles_per_bit: int = 8) -> tuple[int, int]:
    """Return (clkdiv_int, clkdiv_frac) so 8 SM-cycles equal one bit at `baud`.

    SM cycle rate = sys_hz / (int + frac/256). Bit rate = SM / cycles_per_bit.
    """
    if baud <= 0 or sys_hz <= 0 or cycles_per_bit <= 0:
        raise ValueError("sys_hz, baud, cycles_per_bit must be positive")
    target = sys_hz / (cycles_per_bit * baud)
    intval = int(target)
    if intval < 1:
        intval = 1
    if intval > 65535:
        intval = 65535
    frac = int(round((target - intval) * 256))
    if frac >= 256:
        intval += 1
        frac = 0
    if frac < 0:
        frac = 0
    return intval, frac
