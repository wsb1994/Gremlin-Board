PYTHON ?= .venv/bin/python
export PYTHONPATH := generator

.PHONY: test test-verilog emit check plans synth ci

test:
	$(PYTHON) -m pytest tests -k 'not verilog'

test-verilog:
	$(PYTHON) -m pytest tests/test_verilog_sim.py

emit:
	$(PYTHON) -m loom emit

check:
	$(PYTHON) -m loom check

plans:
	$(PYTHON) -m loom plans

synth:
	$(PYTHON) -m loom synth

ci: check test emit
