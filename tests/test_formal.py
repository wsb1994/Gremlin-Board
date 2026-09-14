"""k-induction proof of the engine's structural invariants and ISA step
semantics (see loom.formal). Needs a full yosys (native or via docker)."""

import shutil

import pytest

from loom.formal import prove


@pytest.mark.skipif(not (shutil.which("yosys") or shutil.which("docker")), reason="needs yosys or docker")
def test_formal_k_induction():
    ok, log = prove()
    assert ok, log[-3000:]
