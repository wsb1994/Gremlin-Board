# What Jane Street has actually rewarded in hardware

The reverse-engineering contest writeups are not public yet. What is public, and what this contest page itself links, is the methodology they already use.

## ASCII waveform expect tests (Jun 2020)

https://blog.janestreet.com/using-ascii-waveforms-to-test-hardware-designs/

They do not eyeball GTKWave for the tests that matter. Hardcaml sim prints a cycle-accurate ASCII waveform; an expect test captures it; later diffs fail the build. The contest page features that post.

Loom: `tests/test_timing_infra.py` + `tests/expect/*.txt`.

## Cycle-accurate sim in the same language as the design

Hardcaml: design and testbench in OCaml. Advent of Hardcaml / step testbenches are the same idea.

Loom: interpreter is the spec; Amaranth RTL must match; iverilog on generated Verilog is the third copy.

## Verification as the differentiator (this contest)

They named formal methods, constrained random, AI-assisted verification. They did not name “carry the trading feed.”

Loom: random 8-byte UART payloads; agent retunes RX graphs from measured bit time (`loom.correct`); opcode-level formal is still open.

## This chip’s job in a trading shop

The brief: bit-bang for debug and reverse engineering. Infra tests that belong here: SPI JEDEC bytes, JTAG-style TCK sample, reprogram UART→SPI→JTAG with no RTL change, exact UART bit widths.

Stretch USB LS / 10M Ethernet / CAN graphs are bit-layer subsets, not full PHYs: USB is D+ 8N1 (not NRZI/packet); Ethernet is MII-like clock+data (not 10BASE-T magnetics); CAN has no bit stuffing/CRC.

Not: 10G MAC, Hardcaml rewrite, FIX at exchange rate.
