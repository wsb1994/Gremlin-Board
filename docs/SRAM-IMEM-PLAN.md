# SRAM instruction memory (same graphs, far less fabric)

Date: 2026-09-16
Status: `loom_chip` instantiates `RM_IHPSG13_2P_256x16_c2_bm_bist` (`src/macros/`). Python/formal keep the 1-cycle Array model. 2-SM+SRAM GDS not yet closed.

Keep the ISA, 4 slots, 2 SMs, host pins, and UART 8N1 traces. Stop implementing imem as 2048 flops. Use one IHP **2-port SRAM macro** as the instruction memory. No FF windows. No copy FSM.

## Why the previous draft was too heavy

The first SRAM plan kept **per-SM 32×16 FF windows + a 32-cycle copy FSM + write-through** so fetch could stay combinational. That preserves timing, but it still leaves **1024 imem flops** and extra FSM states. Those windows are the problem we were trying to delete.

We do not need them.

IHP `RM_IHPSG13_2P_*` is **one-cycle access**: present `ADDR` this posedge, `DOUT` is that word on the **next** posedge. If the SM puts **`next_pc` on ADDR in the same cycle it executes `DOUT`**, then after a 1-cycle preload while halted, **every execute cycle matches today’s combo `imem[pc]`**. Jumps, WAIT stalls, and delay counts included.

That is the same physical and simulated capability with ~**364 stdcell flops + 1 macro**, not 2412 flops.

## Non-negotiables

1. Same ISA cycle semantics **while running** (interp traces for UART 8N1, SPI later, etc.).
2. Four graphs, 32 × 16-bit, host-loadable.
3. Two SMs can run **different** slots at once.
4. Same Tiny Tapeout host protocol and 6×4 pins.
5. No protocol hard-blocks.

Volatile is unchanged. SRAM is not flash.

## Architecture (simple)

```
  run=0, host write ──► port A  WEN, ADDR={slot,word}, DIN=instr
  run=0, preload     ──► port A REN SM0 pc=0 ; port B REN SM1 pc=0
  run=1              ──► port A ADDR=SM0 next_pc, DOUT -> SM0 instr
                         port B ADDR=SM1 next_pc, DOUT -> SM1 instr
```

```
                    RM_IHPSG13_2P_256x16_c2_bm_bist
                    256 x 16, two independent ports
                    words [slot*32 + pc]   slot=0..3, pc=0..31
                    words 128..255 unused

     SM0:  instr = A_DOUT     SM1:  instr = B_DOUT
           A_ADDR = next_pc         B_ADDR = next_pc
```

**Execute cycle (already true in current RTL, with `instr` combo from FFs):**

- This cycle: decode `instr`, compute `stall` / `next_pc`, maybe side-effects.
- Posedge: `pc <= next_pc` if not stall.
- **SRAM:** `ADDR` is **`next_pc` (or `pc` if stall)** this cycle. Next posedge `DOUT` is that word — which is the instruction we execute next. Same as combo `imem[pc]` after the posedge.

**Stalls (WAIT, FIFO empty/full):** `next_pc = pc`, ADDR holds, DOUT holds, re-execute. Same as today.

**Delay:** `clk_en=0` or delay counter: do not advance pc; hold ADDR; REN can stay 1 with same address. Same.

**Taken jump:** `next_pc = target` combo from the JMP we are executing; ADDR=target; next cycle DOUT=imem[target]. Same as combo fetch.

**Reset / after load:** while `run=0`, one (or more) clocks with `REN=1`, `ADDR=0` (each SM’s reset pc). Then `A_DOUT`/`B_DOUT` are `imem[0]` before `run` rises. Host already leaves idle clocks between the last imem strobe and `run=1`. **No extra host protocol.**

**Host write:** `run=0` only (already true). Port A: `WEN=1`, `REN=0`, `ADDR={wr_slot, waddr}`, `DIN=wdata`. Port B idle or still preloading SM1. Do not WEN and REN the same address on both ports in one cycle (PDK: no conflict logic). Easy: writes only on A, reads for preload on B for SM1, SM0 preload on A in a cycle without a write. Wrapper already has “imem commit on we rising, not every clock.”

Preload vs write: if a write cycle happens, skip preload that cycle; after the last write, the next halt clocks preload pc=0. Tests and humans already wait ≥1 clock after the high-byte strobe.

## What we deleted vs the window plan

| Piece | Window plan | This plan |
|---|---|---|
| 4 FF banks | gone | gone |
| SM0/SM1 32-word windows | **1024 FFs** | **gone** |
| Copy FSM (32 cycles) | yes | **gone** |
| Write-through into windows | yes | **gone** |
| SRAM | 1P 256×16 | **2P 256×16** (required: two fetches/cycle) |
| Flops in fabric | ~1388 | **~364** |
| Fetch | combo window | `DOUT` of next_pc (equiv. after preload) |

2-port is the one extra we **add**, because two SMs read two PCs every SM cycle. A 1-port macro cannot do that without windows or a 2:1 time-mux (that *would* change timing).

## Macro

**`RM_IHPSG13_2P_256x16_c2_bm_bist`**

- PDK: `ihp-sg13cmos5l` `libs.ref/sg13cmos5l_sram`
- 256 × 16, 2 ports, one-cycle access
- LEF size **419.95 × 136.97 µm** (~57.5k µm²) on a **1289 × 711 µm** 6×4 die (~6% of the tile)
- Use 128 words (`{slot[1:0], pc[4:0]}`). Top half tied unused.
- `*_DLY` **must be 1** (datasheet).
- BIST `*_BIST_EN = 0`, other BIST pins 0.
- No write+read of the **same** address on A and B in one cycle. Halt: writes on A. Run: both ports **read** (dual-read of the same word is two SMs on the same slot+pc — avoid if the compiler forbids; two SMs on one slot is allowed today. If 2P dual-read-same-addr is unsafe, force SM0/SM1 to different slots or insert a 1-word FF bypass only when addresses collide — only needed if datasheet forbids it; default assume dual **read** is OK, dual **write** / write-read-same is not.)

1P 256×16 is smaller (237×119) but **cannot** serve two SMs without bringing windows back. Do not use it for the chip config (`n_sm=2`). `loom_engine` test config (`n_sm=1`, `n_slots=1`) can stay FF-only so formal/iverilog do not need the macro.

## Flop / P&R expectation

| | 4-slot FF now | This plan |
|---|---|---|
| Imem in stdcells | 2048 DFF | 0 |
| Fetch mux | 128:1 × 16b × 2 | none (macro) |
| Clk fanout | 2413 | ~364 + 2 SRAM clks |
| DRT | 6h+, 20k shorts | old-chip class or better (old was 11 min DRT, **512 of 623 FFs were imem**) |
| Full LibreLane | 8–12h / GHA timeout | **~45–90 min**, GHA-viable |
| Die | 6×4 | 6×4, macro + stdcell |

Old closed chip: 623 FFs, 45 min total, Magic DRC 31 min. This plan has **fewer stdcell FFs than that** plus a DRC-clean macro. Routing should be easier than the already-taped 1-bank FF design.

## Simulated identity

- **Interp:** unchanged lists, combo `imem[pc]`.
- **`GraphEngine(n_sm=1)` tests/formal:** still FF `Array` (no macro).
- **`GraphEngine(n_sm=2, n_slots=4)` / `loom_chip`:** SRAM behavioural Verilog from the PDK. After `load`, one halt cycle with REN so `DOUT` matches `imem[0]` before `run`.
- **Wrapper:** already ≥1 clk between imem commit and `run`. Optionally hold `run` internally until preload_done (1 bit) so even a same-cycle run still works.
- **Formal:** keep proving the SM against combo imem (1-slot FF). Do not k-induce the SRAM wrapper.
- **UART 8N1:** same graphs, same bit times. Preload is idle-high / not-running.

If a test writes imem and raises `run` in the **same** cycle, add 1 halt tick. That is the only test delta. Function of graphs is unchanged.

## Physical identity

Same pins, same 4 slots, same 2 SMs, same CSRs, same 8N1 dual-SM. Extra SRAM words are **not** extra slots (do not advertise 8). Still forgets on `rst_n`.

## LibreLane

- `EXTRA_LEFS` / `EXTRA_GDS_FILES` / `EXTRA_LIBS`: `RM_IHPSG13_2P_256x16_c2_bm_bist`
- Behavioural `.v` for GL sim
- Place macro on one side, ≥10 µm halo, do not hit the 6×4 tap spine
- **PDN hooks:** SRAM pins are likely `VDD`/`VSS` not `VPWR`/`VGND` — map explicitly
- LVS: `sram_integration.lvs` / Magic `read_sram_gds.tcl`
- `RT_MAX_LAYER` Metal4; macro internal layers stay in GDS

## Risks

| Risk | Mitigation |
|---|---|
| 2P dual-read same address | Check timing doc; if forbidden, when `sm0_addr==sm1_addr` feed SM1 from A_DOUT |
| Write-read same cycle | `run=0` writes; never WEN while that port RENs the same addr |
| `*_DLY` | Tie 1 |
| Preload missed | Wrapper `preload_done` before accepting `run` |
| Macro VDD vs VPWR | `FP_PDN_MACRO_HOOKS` |
| Current 6h FF DRT | Kill it; wrong netlist |

## Key decisions

1. **No windows, no copy FSM** — 2P SRAM + next_pc ADDR is enough for 1-cycle-equivalent fetch.
2. **2-port 256×16**, not 1-port — two SMs, two PCs, one cycle.
3. **FF `loom_engine` stays** for formal/ISA tests; only `loom_chip` instantiates the macro.
4. **Do not grow to 8 slots** just because the array is 256 deep.
5. **Do not execute a “window plan” first** unless 2P dual-read is shown illegal.

## PR plan

### PR 1 — Chip imem = 2P SRAM + next_pc fetch
- `generator/loom/rtl.py` (or `imem.py`), `emit.py`, PDK blackbox/behavioural include
- `n_slots==4 && n_sm==2` only
- Halt preload; host write on port A
- Tests: existing dual-SM + UART 8N1 on `GraphEngine(n_sm=2,n_slots=4)` with SRAM model; 1-slot tests untouched

### PR 2 — Floorplan + LibreLane extras
- LEF/GDS/LIB, PDN, placement, `docs/info.md` (volatile SRAM, not a new pin protocol)
- Run P&R; expect DRT minutes
- DRC/LVS/50 MHz; then `tt_submission/`

### PR 3 — GL sim
- TT `gl_test` + one slot-load + dual-SM smoke if models allow

No PR for windows/copy. If PR 1 hits a 2P same-addr read ban, add a **1-mux bypass** (when addrs equal, SM1 uses A_DOUT) — still no 1024-FF windows.

## Rejected (more complex or lost function)

| Idea | Why not |
|---|---|
| FF windows + copy FSM | Works, ~1024 extra FFs, extra FSM; we can do without |
| 1P SRAM | Cannot fetch two PCs; needs windows or 1 SM |
| 1 SM only | Loses simultaneous TX+RX |
| 2 slots only | Loses 4 resident graphs |
| Sync fetch without next_pc (instr 1 cycle late) | Breaks bit timing |
| Infer RAM from `Array` | Yosys will still emit DFFs on this ASIC flow |
| Use unused 128 words as slots 4–7 | Host/CSR change; out of scope |
