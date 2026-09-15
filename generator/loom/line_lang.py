"""Independent spec languages L for contest protocol byte pipes.

Waveforms are synthesised from the protocol rules, not from any TX graph.
Each `spec_wave(byte)` is a gpio_in trace of one well-formed one-byte frame.
`tx_matches_spec` checks a TX pin/OE trace is a word of the same language.
"""

from __future__ import annotations


def bus_from_od(out: list[int], oe: list[int], pullup: int = 0xFF) -> list[int]:
    bus: list[int] = []
    for o, e in zip(out, oe):
        b = pullup
        for i in range(8):
            if (e >> i) & 1:
                if (o >> i) & 1:
                    b |= 1 << i
                else:
                    b &= ~(1 << i)
        bus.append(b)
    return bus


def _sample_rise(data: list[int], clk: list[int], prev: int = 0) -> list[int]:
    bits: list[int] = []
    p = prev
    for d, c in zip(data, clk):
        c &= 1
        if c and not p:
            bits.append(d & 1)
        p = c
    return bits


def _sample_fall(data: list[int], clk: list[int], prev: int = 1) -> list[int]:
    bits: list[int] = []
    p = prev
    for d, c in zip(data, clk):
        c &= 1
        if (not c) and p:
            bits.append(d & 1)
        p = c
    return bits


def bits_msb(byte: int, n: int = 8) -> list[int]:
    return [((byte >> i) & 1) for i in range(n - 1, -1, -1)]


def bits_lsb(byte: int, n: int = 8) -> list[int]:
    return [((byte >> i) & 1) for i in range(n)]


def pack_msb(bits: list[int]) -> int:
    v = 0
    for b in bits[:8]:
        v = (v << 1) | (b & 1)
    return v


def pack_lsb(bits: list[int]) -> int:
    v = 0
    for i, b in enumerate(bits[:8]):
        v |= (b & 1) << i
    return v


# ---------------------------------------------------------------------------
# SPI mode 0 with chip-select. MOSI=0 SCK=1 CS=2. CS active low.
# ---------------------------------------------------------------------------

def spi_spec_wave(byte: int) -> list[int]:
    """Idle CS=1 SCK=0; CS falls; 8 MSB bits mode-0; CS rises."""
    wave = [0b100] * 4  # CS idle high
    wave += [0b000] * 2  # CS low, SCK low
    for bit in bits_msb(byte):
        wave += [bit, bit | 0b010, bit]  # setup, SCK rise, SCK fall
    wave += [0b000, 0b100, 0b100]
    return wave


def spi_tx_matches(gpio: list[int], byte: int) -> None:
    cs = [(t >> 2) & 1 for t in gpio]
    mosi = [t & 1 for t in gpio]
    sck = [(t >> 1) & 1 for t in gpio]
    try:
        fall = next(i for i in range(1, len(cs)) if cs[i - 1] == 1 and cs[i] == 0)
    except StopIteration as e:
        raise AssertionError("spi: no CS falling edge") from e
    try:
        rise = next(i for i in range(fall + 1, len(cs)) if cs[i - 1] == 0 and cs[i] == 1)
    except StopIteration as e:
        raise AssertionError("spi: no CS rising edge") from e
    window_m = mosi[fall:rise]
    window_c = sck[fall:rise]
    bits = _sample_rise(window_m, window_c, prev=0)
    if pack_msb(bits) != byte:
        raise AssertionError(f"spi CS-window samples {bits[:8]} != 0x{byte:02x}")
    if any(sck[i] for i in range(fall) if cs[i]):
        pass  # idle SCK may glitch before CS; ignore
    for i in range(fall, rise):
        if cs[i] != 0:
            raise AssertionError("spi: CS not held low during bits")


# ---------------------------------------------------------------------------
# I2C open-drain: SDA=0 SCL=1. START, 8 MSB bits, ACK (SDA=0), STOP.
# ---------------------------------------------------------------------------

def i2c_spec_wave(byte: int) -> list[int]:
    """Logical bus (pull-up 1). START, 8 MSB, ACK 0, STOP."""
    sda, scl = 1, 1
    wave = [0b11] * 4

    def snap():
        wave.append(sda | (scl << 1))

    sda = 0  # START while SCL high
    snap()
    snap()
    scl = 0
    snap()
    for bit in bits_msb(byte):
        sda = bit
        snap()
        scl = 1
        snap()
        snap()
        scl = 0
        snap()
    sda = 0  # ACK
    snap()
    scl = 1
    snap()
    snap()
    scl = 0
    snap()
    sda = 0
    snap()
    scl = 1  # STOP: SCL high then SDA rise
    snap()
    sda = 1
    snap()
    wave += [0b11] * 4
    return wave


def i2c_tx_matches(gpio: list[int], byte: int) -> None:
    sda = [t & 1 for t in gpio]
    scl = [(t >> 1) & 1 for t in gpio]
    start = None
    for i in range(1, len(gpio)):
        if scl[i] and scl[i - 1] and sda[i - 1] == 1 and sda[i] == 0:
            start = i
            break
    if start is None:
        raise AssertionError("i2c: no START")
    bits = _sample_rise(sda[start:], scl[start:], prev=scl[start])
    if len(bits) < 9:
        raise AssertionError(f"i2c: need 8 data + ACK, got {len(bits)}")
    if pack_msb(bits[:8]) != byte:
        raise AssertionError(f"i2c data {bits[:8]} != 0x{byte:02x}")
    if bits[8] != 0:
        raise AssertionError("i2c: ACK slot is not 0")
    stop = False
    for i in range(start + 1, len(gpio)):
        if scl[i] and scl[i - 1] and sda[i - 1] == 0 and sda[i] == 1:
            stop = True
            break
    if not stop:
        raise AssertionError("i2c: no STOP")


# ---------------------------------------------------------------------------
# JTAG: TDI=0 TCK=1 TMS=2. TLR (≥5 TMS=1) then Shift-DR, 8 TDI LSB, Update-DR.
# ---------------------------------------------------------------------------

def _jtag_tck(wave: list[int], tdi: int, tms: int) -> None:
    v = (tdi & 1) | ((tms & 1) << 2)
    wave += [v, v | 2, v]  # TCK lo, hi, lo


def jtag_spec_wave(byte: int) -> list[int]:
    wave = [0] * 2
    for _ in range(5):
        _jtag_tck(wave, 0, 1)  # TLR
    _jtag_tck(wave, 0, 0)  # RTI
    _jtag_tck(wave, 0, 1)  # Select-DR
    _jtag_tck(wave, 0, 0)  # Capture-DR
    _jtag_tck(wave, 0, 0)  # Shift-DR
    bits = bits_lsb(byte)
    for i, b in enumerate(bits):
        tms = 1 if i == 7 else 0  # last bit Exit1-DR
        _jtag_tck(wave, b, tms)
    _jtag_tck(wave, 0, 1)  # Update-DR
    _jtag_tck(wave, 0, 0)  # RTI
    wave += [0] * 4
    return wave


def jtag_tx_matches(gpio: list[int], byte: int) -> None:
    tdi = [t & 1 for t in gpio]
    tck = [(t >> 1) & 1 for t in gpio]
    tms = [(t >> 2) & 1 for t in gpio]
    edges = []
    prev = 0
    for i, c in enumerate(tck):
        if c and not prev:
            edges.append(i)
        prev = c
    if len(edges) < 5:
        raise AssertionError("jtag: not enough TCK edges")
    tms_at = [tms[i] for i in edges]
    if sum(tms_at[:5]) < 5:
        # allow extra clocks; find 5 consecutive TMS=1
        ok = False
        for i in range(0, len(tms_at) - 4):
            if tms_at[i : i + 5] == [1, 1, 1, 1, 1]:
                ok = True
                break
        if not ok:
            raise AssertionError("jtag: no TLR (≥5 TMS=1)")
    # Shift-DR: TMS=0 clocks with TDI, last of 8 has TMS=1
    tdi_at = [tdi[i] for i in edges]
    # hunt 7 TMS=0 followed by TMS=1 with 8 TDI bits = byte LSB first
    found = False
    for i in range(len(edges) - 7):
        if tms_at[i : i + 7] == [0] * 7 and tms_at[i + 7] == 1:
            got = pack_lsb(tdi_at[i : i + 8])
            if got == byte:
                found = True
                break
    if not found:
        raise AssertionError(f"jtag: no Shift-DR 8-bit LSB window for 0x{byte:02x}")


# ---------------------------------------------------------------------------
# SWD: SWDIO=0 SWCLK=1. ≥50 clocks with SWDIO=1, then 8 LSB data bits.
# ---------------------------------------------------------------------------

def swd_spec_wave(byte: int) -> list[int]:
    wave = [1] * 2  # SWDIO idle 1, clk 0
    for _ in range(50):
        wave += [1, 1 | 2, 1]  # line-reset: SWDIO=1
    for bit in bits_lsb(byte):
        wave += [bit, bit | 2, bit]
    wave += [0] * 4
    return wave


def swd_tx_matches(gpio: list[int], byte: int) -> None:
    dio = [t & 1 for t in gpio]
    clk = [(t >> 1) & 1 for t in gpio]
    bits = _sample_rise(dio, clk, prev=0)
    # first ≥50 samples must be 1 (line reset), then 8 data
    nreset = 0
    for b in bits:
        if b == 1:
            nreset += 1
        else:
            break
    if nreset < 50:
        # allow reset then data that starts with 0
        ones = 0
        i = 0
        while i < len(bits) and bits[i] == 1:
            ones += 1
            i += 1
        if ones < 50:
            raise AssertionError(f"swd: line-reset ones={ones} want ≥50")
        data = bits[i : i + 8]
    else:
        # 50+ ones; if data starts with 1s they overlap. Take bits after 50.
        data = bits[50:58]
    if pack_lsb(data) != byte:
        # if byte has leading 1s, they were counted as reset; recover:
        if nreset >= 50:
            # reconstruct: 50 ones consumed, remaining include data
            pass
        # retry: skip exactly 50 rise samples
        if len(bits) >= 58 and pack_lsb(bits[50:58]) == byte:
            return
        raise AssertionError(f"swd data {data} != 0x{byte:02x} (reset_ones={nreset})")


# ---------------------------------------------------------------------------
# PS/2 host byte: DATA=0 CLK=1. Start 0, 8 LSB, odd parity, stop 1, ACK 0.
# ---------------------------------------------------------------------------

def _odd_parity(byte: int) -> int:
    return 1 - (bin(byte).count("1") & 1)


def ps2_spec_wave(byte: int) -> list[int]:
    bits = [0] + bits_lsb(byte) + [_odd_parity(byte), 1, 0]  # start, data, par, stop, ack
    wave = [0b11] * 4
    for b in bits:
        wave += [b | 2, b | 2, b, b, b | 2, b | 2]  # clk hi, lo, hi
    wave += [0b11] * 4
    return wave


def ps2_tx_matches(gpio: list[int], byte: int) -> None:
    data = [t & 1 for t in gpio]
    clk = [(t >> 1) & 1 for t in gpio]
    bits = _sample_fall(data, clk, prev=1)
    if len(bits) < 11:
        raise AssertionError(f"ps2: need start+8+par+stop+ack, got {len(bits)}")
    if bits[0] != 0:
        raise AssertionError("ps2: start bit not 0")
    if pack_lsb(bits[1:9]) != byte:
        raise AssertionError(f"ps2 data {bits[1:9]} != 0x{byte:02x}")
    if bits[9] != _odd_parity(byte):
        raise AssertionError("ps2: odd parity mismatch")
    if bits[10] != 1:
        raise AssertionError("ps2: stop bit not 1")
    if len(bits) < 12 or bits[11] != 0:
        raise AssertionError("ps2: missing device ACK (DATA=0)")


# ---------------------------------------------------------------------------
# CAN: SOF + 8 data MSB + CRC15 + ACK slot + EOF, stuffed after 5 identical.
# ---------------------------------------------------------------------------

CAN_POLY = 0x4599


def crc15(bits: list[int]) -> int:
    crc = 0
    for b in bits:
        msb = (crc >> 14) & 1
        crc = ((crc << 1) & 0x7FFF)
        if msb ^ (b & 1):
            crc ^= CAN_POLY
    return crc


def can_stuff(bits: list[int]) -> list[int]:
    out: list[int] = []
    run = 0
    last = None
    for b in bits:
        b &= 1
        if last is None or b != last:
            run = 1
        else:
            run += 1
        out.append(b)
        last = b
        if run == 5:
            inv = 1 - b
            out.append(inv)
            last = inv
            run = 1
    return out


def can_destuff(bits: list[int]) -> list[int]:
    out: list[int] = []
    run = 0
    last = None
    skip = False
    for b in bits:
        b &= 1
        if skip:
            skip = False
            last = b
            run = 1
            continue
        out.append(b)
        if last is None or b != last:
            run = 1
        else:
            run += 1
        last = b
        if run == 5:
            skip = True
            run = 0
    return out


def can_destuff_n(bits: list[int], n: int = 24) -> tuple[list[int], list[int]]:
    """Destuff until n destuffed bits; return (destuffed, remaining wire bits)."""
    out: list[int] = []
    run = 0
    last = None
    skip = False
    rest_at = len(bits)
    for i, b in enumerate(bits):
        b &= 1
        if skip:
            skip = False
            last = b
            run = 1
            continue
        out.append(b)
        if last is None or b != last:
            run = 1
        else:
            run += 1
        last = b
        if run == 5:
            skip = True
            run = 0
        if len(out) == n:
            rest_at = i + 1
            if skip:
                rest_at = min(len(bits), rest_at + 1)
            break
    return out, bits[rest_at:]


def can_frame_bits(byte: int) -> list[int]:
    data = bits_lsb(byte)
    body = [0] + data  # SOF + 8 data LSB
    c = crc15(body)
    crc_bits = [(c >> i) & 1 for i in range(14, -1, -1)]
    # ISO 11898: stuffing SOF through CRC; delimiter/ACK/EOF are not stuffed.
    return can_stuff(body + crc_bits) + [1, 0, 1] + [1] * 7


def can_spec_wave(byte: int) -> list[int]:
    return _clocked_cells(can_frame_bits(byte), idle=1)


def _can_cells(gpio: list[int]) -> list[int]:
    """Clocked cells on pin2 if any rise exists, else 8-cycle majority on pin0."""
    rises = 0
    prev = 0
    cells: list[int] = []
    for t in gpio:
        clk = (t >> 2) & 1
        if clk and not prev:
            cells.append(t & 1)
            rises += 1
        prev = clk
    if rises >= 8:
        return cells
    pin = [t & 1 for t in gpio]
    i = 0
    while i < len(pin) and pin[i] == 1:
        i += 1
    cells = []
    while i + 7 < len(pin):
        sl = pin[i : i + 8]
        cells.append(1 if sum(sl) >= 4 else 0)
        i += 8
    return cells


def can_tx_matches(gpio: list[int], byte: int) -> None:
    cells = _can_cells(gpio)
    i = 0
    while i < len(cells) and cells[i] == 1:
        i += 1
    cells = cells[i:]
    if not cells or cells[0] != 0:
        raise AssertionError("can: no SOF dominant")
    dest, rest_wire = can_destuff_n(cells, 24)
    if len(dest) < 9 or pack_lsb(dest[1:9]) != byte:
        raise AssertionError(
            f"can destuffed data {dest[1:9] if len(dest) >= 9 else dest} != 0x{byte:02x}"
        )
    if len(dest) < 24:
        raise AssertionError("can: truncated (need CRC)")
    body = dest[:9]
    crc_field = 0
    for b in dest[9:24]:
        crc_field = (crc_field << 1) | (b & 1)
    want = crc15(body)
    if crc_field != want:
        raise AssertionError(f"can CRC 0x{crc_field:04x} != crc15 0x{want:04x}")
    rest = can_destuff(rest_wire) if rest_wire else dest[24:]
    if 0 not in rest[:8] and 0 not in rest_wire[:8]:
        raise AssertionError("can: missing ACK dominant")
    ones = rest.count(1) + rest_wire.count(1)
    tail = [t & 1 for t in gpio[-24:]]
    if ones < 7 and sum(tail) < 8:
        raise AssertionError("can: missing EOF ones")


# ---------------------------------------------------------------------------
# USB LS: NRZI (0=toggle 1=hold), stuff after six 1s, SYNC KJKJKJKK, EOP SE0.
# J=D-=1 D+=0 = 0b10; K=0b01; SE0=0.
# ---------------------------------------------------------------------------

USB_J, USB_K, USB_SE0 = 0b10, 0b01, 0


def usb_nrzi_encode(data_bits: list[int], start: int = USB_J) -> list[int]:
    """data_bits are raw (pre-NRZI) bits including stuffed zeros."""
    st = start
    out: list[int] = []
    for b in data_bits:
        if b == 0:
            st = USB_K if st == USB_J else USB_J
        out.append(st)
    return out


def usb_stuff(bits: list[int]) -> list[int]:
    out: list[int] = []
    ones = 0
    for b in bits:
        b &= 1
        out.append(b)
        if b == 1:
            ones += 1
            if ones == 6:
                out.append(0)
                ones = 0
        else:
            ones = 0
    return out


def usb_frame_states(byte: int) -> list[int]:
    # SYNC is KJKJKJKK on the wire (already NRZI of 00000001)
    sync = [USB_K, USB_J, USB_K, USB_J, USB_K, USB_J, USB_K, USB_K]
    raw = bits_lsb(byte)
    stuffed = usb_stuff(raw)
    # after SYNC the line is K; data NRZI starts from K
    data = usb_nrzi_encode(stuffed, start=USB_K)
    eop = [USB_SE0, USB_SE0, USB_J]
    return sync + data + eop


def _clocked_cells(states: list[int], idle: int, prefix: int = 8, suffix: int = 16) -> list[int]:
    """Idle, then each state with a wide pin2 clock for wait_pin RX."""
    wave = [idle] * prefix
    for st in states:
        s = st & 0b11
        wave += [s] * 2
        wave += [s | 4] * 8
        wave += [s] * 6
    wave += [idle] * suffix
    return wave


def usb_spec_wave(byte: int) -> list[int]:
    return _clocked_cells(usb_frame_states(byte), USB_J)


def usb_tx_matches(gpio: list[int], byte: int) -> None:
    """SYNC KJKJKJKK, NRZI data with stuff-after-6, EOP SE0.

    Bit cells are sampled on pin2 rising edges (emulator bit clock). EOP is
    SE0 on D+/D- after the last clocked cell.
    """
    cells: list[int] = []
    last_rise = 0
    prev_clk = 0
    for i, t in enumerate(gpio):
        clk = (t >> 2) & 1
        st = t & 0b11
        if clk and not prev_clk:
            cells.append(st)
            last_rise = i
        prev_clk = clk
    pat = [USB_K, USB_J, USB_K, USB_J, USB_K, USB_J, USB_K, USB_K]
    if len(cells) < 8 or cells[:8] != pat:
        raise AssertionError(f"usb: SYNC {cells[:8]} != KJKJKJKK")
    rest = cells[8:]
    nrzi: list[int] = []
    for s in rest:
        if s not in (USB_J, USB_K):
            break
        nrzi.append(s)
    if not nrzi:
        raise AssertionError("usb: no NRZI data after SYNC")
    st = USB_K
    raw: list[int] = []
    for s in nrzi:
        raw.append(0 if s != st else 1)
        st = s
    dest: list[int] = []
    ones = 0
    i = 0
    while i < len(raw):
        b = raw[i]
        dest.append(b)
        if b == 1:
            ones += 1
            if ones == 6:
                i += 1
                if i < len(raw) and raw[i] == 0:
                    ones = 0
                else:
                    break
        else:
            ones = 0
        i += 1
    if pack_lsb(dest[:8]) != byte:
        raise AssertionError(f"usb destuffed {dest[:8]} != 0x{byte:02x}")
    tail = [t & 0b11 for t in gpio[last_rise + 1 : last_rise + 64]]
    if USB_SE0 not in tail:
        raise AssertionError("usb: no EOP SE0")
    if sum(1 for t in tail if t == USB_SE0) < 2:
        raise AssertionError("usb: EOP SE0 shorter than two bit cells")


# ---------------------------------------------------------------------------
# Ethernet: seven 0x55 + 0xD5 SFD + payload, MSB, data=0 clk=1.
# ---------------------------------------------------------------------------

def _eth_clocked(byte: int, wave: list[int]) -> None:
    for bit in bits_msb(byte):
        # Wide clock so RX wait_rise / wait_fall / jmp has room between edges.
        wave += [bit, bit, bit | 2, bit | 2, bit, bit]


def eth_spec_wave(byte: int) -> list[int]:
    wave = [0] * 4
    for _ in range(7):
        _eth_clocked(0x55, wave)
    _eth_clocked(0xD5, wave)
    _eth_clocked(byte, wave)
    wave += [0] * 16
    return wave


def eth_tx_matches(gpio: list[int], byte: int) -> None:
    data = [t & 1 for t in gpio]
    clk = [(t >> 1) & 1 for t in gpio]
    bits = _sample_rise(data, clk, prev=0)
    if len(bits) < 72:
        raise AssertionError(f"eth: need 56+8+8 bits, got {len(bits)}")
    pre = [pack_msb(bits[i : i + 8]) for i in range(0, 56, 8)]
    if pre != [0x55] * 7:
        raise AssertionError(f"eth preamble {pre} != seven 0x55")
    sfd = pack_msb(bits[56:64])
    if sfd != 0xD5:
        raise AssertionError(f"eth SFD 0x{sfd:02x} != 0xD5")
    pay = pack_msb(bits[64:72])
    if pay != byte:
        raise AssertionError(f"eth payload 0x{pay:02x} != 0x{byte:02x}")


SPECS = {
    "spi": (spi_spec_wave, spi_tx_matches),
    "i2c": (i2c_spec_wave, i2c_tx_matches),
    "jtag": (jtag_spec_wave, jtag_tx_matches),
    "swd": (swd_spec_wave, swd_tx_matches),
    "ps2": (ps2_spec_wave, ps2_tx_matches),
    "can": (can_spec_wave, can_tx_matches),
    "usb": (usb_spec_wave, usb_tx_matches),
    "eth": (eth_spec_wave, eth_tx_matches),
}
