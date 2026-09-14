from pathlib import Path

from loom.compile import compile_plan
from loom.criteria import (
    PROTOCOL_NAMES,
    assert_criteria,
    engine_source,
)
from loom.graphfmt import dumps, loads
from loom.interp import Engine
from loom.ir import Plan, PRIMITIVES
from loom.perf import fits_onchip_imem, instruction_count
from loom.stores import MemoryStore, SdStore, UsbStore

PLANS = Path(__file__).resolve().parents[1] / "plans"
HELLO = b"Hi"
BAUD = 8


def load_plan(name: str) -> Plan:
    return Plan.from_toml(PLANS / name)


def assemble(name: str) -> list[int]:
    return compile_plan(load_plan(name)).assemble()


def test_criteria_gate():
    assert_criteria()
    src = engine_source()
    for name in PROTOCOL_NAMES:
        assert name not in src


def test_graphs_are_goblin_shaped_nodes():
    plan = load_plan("uart_tx.toml")
    assert plan.steps
    for step in plan.steps:
        assert step.name
        assert step.function in PRIMITIVES
        assert step.function not in PROTOCOL_NAMES


def test_graph_roundtrip_through_memory_sd_usb():
    plan = load_plan("uart_tx.toml")
    blob = dumps(plan)
    for store in (MemoryStore(), SdStore(), UsbStore()):
        store.write(plan.name, blob)
        again = loads(store.read(plan.name))
        assert again.name == plan.name
        assert [s.function for s in again.steps] == [s.function for s in plan.steps]


def test_hello_graphs_fit_onchip_working_set():
    for name in (
        "uart_tx.toml",
        "uart_rx.toml",
        "spi_tx.toml",
        "spi_rx.toml",
        "i2c_tx.toml",
        "i2c_rx.toml",
    ):
        plan = load_plan(name)
        assert fits_onchip_imem(plan), (name, instruction_count(plan))


def test_reprogram_does_not_change_engine():
    """Same interpreter, new graph — the Jane Street reprogrammable requirement."""
    eng = Engine()
    ident = id(eng.sm)
    eng.load(assemble("uart_tx.toml"))
    eng.load(assemble("spi_tx.toml"))
    eng.load(assemble("i2c_tx.toml"))
    assert id(eng.sm) == ident


def _push(eng: Engine, payload: bytes) -> None:
    for b in payload:
        assert eng.sm.tx.push(b)


def _run_tx(plan_file: str, payload: bytes, cycles: int) -> list[int]:
    eng = Engine()
    eng.load(assemble(plan_file))
    _push(eng, payload)
    eng.run_cycles(cycles)
    return eng.trace_out


def _run_rx(plan_file: str, gpio_seq: list[int], cycles: int) -> bytes:
    eng = Engine()
    eng.load(assemble(plan_file))
    eng.run_cycles(cycles, gpio_seq)
    return bytes(eng.sm.rx.q)


def _uart_frame(byte: int) -> list[int]:
    bits = [0] * BAUD
    for i in range(8):
        bits += [((byte >> i) & 1)] * BAUD
    bits += [1] * BAUD
    return bits


def test_uart_encode_hello():
    trace = _run_tx("uart_tx.toml", HELLO, 400)
    pin = [t & 1 for t in trace]
    start = pin.index(0)
    got = pin[start : start + 10 * BAUD]
    want = _uart_frame(HELLO[0])
    assert got == want, list(zip(got, want))


def test_uart_decode_hello():
    wave = [1] * 16
    for b in HELLO:
        wave += _uart_frame(b)
    wave += [1] * 32
    gpio = wave  # pin0
    got = _run_rx("uart_rx.toml", gpio, len(gpio))
    assert got == HELLO, got


def test_uart_encode_then_decode_hello():
    trace = _run_tx("uart_tx.toml", HELLO, 500)
    gpio = [t & 1 for t in trace]
    got = _run_rx("uart_rx.toml", gpio, len(gpio))
    assert got == HELLO, got


def test_spi_encode_then_decode_hello():
    tx = _run_tx("spi_tx.toml", HELLO, 300)
    gpio = tx  # bit0 MOSI, bit1 SCK
    got = _run_rx("spi_rx.toml", gpio, len(gpio))
    assert got == HELLO, got


def test_i2c_encode_then_decode_hello():
    tx = _run_tx("i2c_tx.toml", HELLO, 400)
    gpio = tx  # bit0 SDA, bit1 SCL
    got = _run_rx("i2c_rx.toml", gpio, len(gpio))
    assert got == HELLO, got


def test_node_cost_is_one_plus_delay():
    from loom.isa import encode, OP_NOP
    from loom.interp import SM

    sm = SM()
    sm.imem[0] = encode(OP_NOP, delay=3)
    sm.imem[1] = encode(OP_NOP, delay=0)
    sm.run = True
    for _ in range(4):
        sm.tick()
    assert sm.pc == 1
    sm.tick()
    assert sm.pc == 2
