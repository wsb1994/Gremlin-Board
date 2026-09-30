PYTHON ?= .venv/bin/python
export PYTHONPATH := generator

.PHONY: test test-verilog test-exhaustive formal verify emit check plans synth ci check-pg

test:
	$(PYTHON) -m pytest tests -k 'not verilog'

test-verilog:
	$(PYTHON) -m pytest tests/test_verilog_sim.py

test-exhaustive:  # every ISA encoding, interp vs emitted Verilog (iverilog)
	$(PYTHON) -m pytest tests/test_verilog_isa_exhaustive.py

formal:  # k-induction: ISA step semantics + FIFO/halt invariants (yosys sat)
	$(PYTHON) -m loom formal

formal-proto:  # all 256 bytes × every protocol: TX encoding, RX spec, round-trip, loop
	$(PYTHON) -m loom formal-proto

verify: test-verilog test-exhaustive formal

emit:
	$(PYTHON) -m loom emit

check:
	$(PYTHON) -m loom check

plans:
	$(PYTHON) -m loom plans

synth:
	$(PYTHON) -m loom synth

ci: check test emit

GDS ?= tt_submission/tt_um_loom_gpe.gds
check-pg:  # supply connectivity of the hardened GDS: VPWR/VGND single nets, every SRAM pin on them
	docker run --rm -v "$(CURDIR):$(CURDIR)" -w "$(CURDIR)" ghcr.io/librelane/librelane:3.1.0.dev3 \
	  klayout -b -r scripts/check_pg_klayout.py -rd gds=$(GDS) -rd lef=src/macros/RM_IHPSG13_2P_256x16_c2_bm_bist.lef
