"""Open-drain I2C master: OE drive-0, ACK slot, clock stretch.

Golden slave lives here, not in the engine core.
SDA=pin0, SCL=pin1. Idle OE=0 (release); pull-up is gpio_in=1.
Drive 0: OE=1 and out=0. Never drive a 1 on SDA/SCL.
"""

from pathlib import Path

from loom.compile import compile_plan
from loom.interp import Engine
from loom.ir import Plan
from loom.isa import IMEM_WORDS
from loom.perf import instruction_count

PLANS = Path(__file__).resolve().parents[1] / "plans"
SDA = 0
SCL = 1
PULLUP = 0xFF
ADDR_WRITE = 0xA0  # 7-bit 0x50 + write
DATA = 0x48


def _plan(name: str) -> Plan:
    return Plan.from_toml(PLANS / name)


def _prog(name: str):
    return compile_plan(_plan(name))


def _words(name: str) -> list[int]:
    return _prog(name).assemble()


def bus_bit(v: int, pin: int) -> int:
    return (v >> pin) & 1


def wire(oe: int, out: int, slave_sda: int, slave_scl: int) -> int:
    """Pull-up AND master open-drain AND slave open-drain."""
    w = PULLUP
    w &= ~(oe & ~out)
    if slave_sda == 0:
        w &= ~(1 << SDA)
    if slave_scl == 0:
        w &= ~(1 << SCL)
    return w


class I2CSlaveModel:
    """ACK=0 after each byte. Optional stretch: hold SCL low after ACK setup."""

    def __init__(self, stretch_cycles: int = 0, stretch_on_ack: int = 1):
        self.sda = 1
        self.scl = 1
        self.prev_sda = 1
        self.prev_scl = 1
        self.shifter = 0
        self.nbits = 0
        self.bytes: list[int] = []
        self.phase = "data"
        self.started = False
        self.stretch_cycles = stretch_cycles
        self.stretch_on_ack = stretch_on_ack
        self.ack_count = 0
        self.stretch_left = 0
        self.ack_windows = 0

    def observe(self, bus: int) -> None:
        sda = bus_bit(bus, SDA)
        scl = bus_bit(bus, SCL)

        if self.stretch_left:
            self.scl = 0
            self.stretch_left -= 1
            if self.stretch_left == 0:
                self.scl = 1
            self.prev_sda, self.prev_scl = sda, scl
            return

        if scl and self.prev_scl and self.prev_sda and not sda:
            self.started = True
            self.shifter = 0
            self.nbits = 0
            self.phase = "data"
            self.sda = 1
            self.scl = 1

        if scl and self.prev_scl and (not self.prev_sda) and sda:
            self.started = False
            self.sda = 1
            self.scl = 1
            self.phase = "data"

        if self.started and scl and not self.prev_scl:
            if self.phase == "data":
                self.shifter = ((self.shifter << 1) | sda) & 0xFF
                self.nbits += 1
            elif self.phase == "ack":
                self.ack_windows += 1

        if self.started and (not scl) and self.prev_scl:
            if self.phase == "data" and self.nbits == 8:
                self.bytes.append(self.shifter)
                self.shifter = 0
                self.nbits = 0
                self.phase = "ack"
                self.sda = 0
                self.ack_count += 1
                if self.stretch_cycles and self.ack_count == self.stretch_on_ack:
                    self.stretch_left = self.stretch_cycles
                    self.scl = 0
            elif self.phase == "ack":
                self.sda = 1
                self.phase = "data"

        self.prev_sda, self.prev_scl = sda, scl


def run_master(
    payload: bytes = bytes([ADDR_WRITE, DATA]),
    cycles: int = 400,
    stretch_cycles: int = 0,
    stretch_on_ack: int = 1,
) -> tuple[Engine, I2CSlaveModel, list[int], list[int], list[int]]:
    eng = Engine()
    eng.load(_words("i2c_od_tx.toml"))
    for b in payload:
        assert eng.sm.tx.push(b)
    slave = I2CSlaveModel(stretch_cycles=stretch_cycles, stretch_on_ack=stretch_on_ack)
    bus_trace: list[int] = []
    eng.sm.run = True
    for _ in range(cycles):
        bus = wire(eng.sm.oe_reg, eng.sm.out_reg, slave.sda, slave.scl)
        bus_trace.append(bus)
        eng.sm.tick(bus)
        eng.trace_out.append(eng.sm.out_reg)
        eng.trace_oe.append(eng.sm.oe_reg)
        eng.cycles += 1
        slave.observe(bus)
    return eng, slave, bus_trace, eng.trace_oe, eng.trace_out


def test_graphs_fit_imem():
    for name in ("i2c_od_tx.toml", "i2c_od_rx.toml"):
        n = instruction_count(_plan(name))
        assert n <= IMEM_WORDS, (name, n)


def test_master_never_drives_high_on_sda_scl():
    _, _, _, oe, out = run_master()
    for e, o in zip(oe, out):
        assert not ((e & 1) and (o & 1)), "SDA driven high"
        assert not ((e & 2) and (o & 2)), "SCL driven high"


def test_master_write_addr_then_data_with_ack():
    eng, slave, bus, oe, out = run_master()
    assert slave.bytes == [ADDR_WRITE, DATA], slave.bytes
    assert slave.ack_count == 2
    assert slave.ack_windows >= 2

    labels = _prog("i2c_od_tx.toml").labels
    ack_clk = labels["ack_clk"]
    ack_wait = labels["ack_wait"]
    released = 0
    sm = Engine()
    sm.load(_words("i2c_od_tx.toml"))
    for b in (ADDR_WRITE, DATA):
        sm.sm.tx.push(b)
    slave2 = I2CSlaveModel()
    sm.sm.run = True
    for _ in range(400):
        busv = wire(sm.sm.oe_reg, sm.sm.out_reg, slave2.sda, slave2.scl)
        if sm.sm.pc in (ack_clk, ack_wait) and sm.sm.delay_ctr == 0:
            assert (sm.sm.oe_reg & 1) == 0, "SDA must be released in ACK slot"
            released += 1
        sm.sm.tick(busv)
        slave2.observe(busv)
    assert released >= 2


def test_clock_stretch_waits_for_scl_high():
    labels = _prog("i2c_od_tx.toml").labels
    wait_pcs = {labels["wait_scl"], labels["ack_wait"]}
    stretch = 12

    eng, slave, bus, *_ = run_master(stretch_cycles=stretch, stretch_on_ack=1)
    assert slave.bytes == [ADDR_WRITE, DATA], slave.bytes

    stalled = 0
    eng2 = Engine()
    eng2.load(_words("i2c_od_tx.toml"))
    for b in (ADDR_WRITE, DATA):
        eng2.sm.tx.push(b)
    slave2 = I2CSlaveModel(stretch_cycles=stretch, stretch_on_ack=1)
    eng2.sm.run = True
    saw_stretch = False
    for _ in range(500):
        busv = wire(eng2.sm.oe_reg, eng2.sm.out_reg, slave2.sda, slave2.scl)
        if slave2.stretch_left or slave2.scl == 0:
            saw_stretch = True
            if eng2.sm.pc in wait_pcs:
                stalled += 1
        eng2.sm.tick(busv)
        slave2.observe(busv)
    assert saw_stretch
    assert stalled >= stretch // 2
    assert slave2.bytes == [ADDR_WRITE, DATA]


def test_rx_decodes_open_drain_transaction():
    _, _, bus, *_ = run_master()
    rx = Engine()
    rx.load(_words("i2c_od_rx.toml"))
    rx.run_cycles(len(bus), bus)
    assert bytes(rx.sm.rx.q) == bytes([ADDR_WRITE, DATA]), bytes(rx.sm.rx.q)


def test_idle_is_released():
    words = _words("i2c_od_tx.toml")
    eng = Engine()
    eng.load(words)
    eng.sm.run = True
    eng.sm.tick(PULLUP)
    eng.sm.tick(PULLUP)
    assert (eng.sm.oe_reg & 3) == 0
    assert (eng.sm.out_reg & 3) == 0
