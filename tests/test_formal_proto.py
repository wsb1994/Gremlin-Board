"""Protocol completeness: every byte 0..255, every shipped TX/RX pair."""

import pytest

from loom.formal_proto import CASES, prove_case, prove_loop, prove_roundtrip, prove_rx_spec, prove_tx_encoding, certify_tx


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_tx_program_is_the_protocol_skeleton(case):
    certify_tx(case)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_tx_encodes_all_256_bytes(case):
    prove_tx_encoding(case)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_rx_decodes_spec_frames_all_256_bytes(case):
    prove_rx_spec(case)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_roundtrip_all_256_bytes(case):
    prove_roundtrip(case)


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_tx_loops_on_pull(case):
    prove_loop(case)


def test_prove_case_uart():
    prove_case(CASES[0])
