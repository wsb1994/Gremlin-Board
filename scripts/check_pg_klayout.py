"""Independent power-grid connectivity check on a final GDS with KLayout.

Extracts Metal1..Metal4 + Via1..Via3 connectivity over the whole layout
(SRAM GDS included) and checks that
  * the VPWR and VGND labels each land on exactly one extracted net,
  * every SRAM supply pin (VDD!, VDDARRAY! -> VPWR; VSS! -> VGND), taken from
    the macro LEF and the instance placement, lies on that net,
and reports how much Metal4 strap width and how many Via3 cuts feed each pin.

    klayout -b -r scripts/check_pg_klayout.py -rd gds=<final.gds> -rd lef=<macro.lef>
"""
import re, sys
import pya

gds = globals()["gds"]
lef = globals().get("lef", "src/macros/RM_IHPSG13_2P_256x16_c2_bm_bist.lef")
sram = globals().get("sram", "RM_IHPSG13_2P_256x16_c2_bm_bist")
NETMAP = {"VDD!": "VPWR", "VDDARRAY!": "VPWR", "VSS!": "VGND"}

ly = pya.Layout(); ly.read(gds)
top = ly.top_cell()
dbu = ly.dbu
l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(ly, top, []))
def mk(name, ln, dt):
    return l2n.make_layer(ly.layer(ln, dt), name)
M1, M2, M3, M4 = mk("M1", 8, 0), mk("M2", 10, 0), mk("M3", 30, 0), mk("M4", 50, 0)
M1p, M2p, M3p, M4p = mk("M1p", 8, 2), mk("M2p", 10, 2), mk("M3p", 30, 2), mk("M4p", 50, 2)
V1, V2, V3 = mk("V1", 19, 0), mk("V2", 29, 0), mk("V3", 49, 0)
for r in (M1, M2, M3, M4, M1p, M2p, M3p, M4p, V1, V2, V3):
    l2n.connect(r)
for a, b in ((M1, M1p), (M2, M2p), (M3, M3p), (M4, M4p), (M1, V1), (V1, M2), (M2, V2), (V2, M3), (M3, V3), (V3, M4)):
    l2n.connect(a, b)
for name, ln in (("M1", 8), ("M4", 50)):
    t = l2n.make_text_layer(ly.layer(ln, 25), name + "lbl")
    l2n.connect({"M1": M1, "M4": M4}[name], t)
l2n.extract_netlist()
circ = l2n.netlist().circuit_by_name(top.name)

fail = 0
for want in ("VPWR", "VGND"):
    nets = [n.name for n in circ.each_net() if n.name and re.split(r"[$,]", n.name)[0] == want]
    print(f"{want}: {len(nets)} extracted net(s): {nets[:6]}")
    if len(nets) != 1:
        fail += 1

# SRAM pins from LEF, placed by the instance transform
s = open(lef).read()
pins = []
for name in NETMAP:
    body = re.search(r"PIN %s\s(.*?)END %s" % (re.escape(name), re.escape(name)), s, re.S).group(1)
    for lay, x0, y0, x1, y1 in re.findall(r"LAYER (\S+) ;\s+RECT ([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)", body):
        if lay == "Metal4":
            pins.append((name, pya.DBox(float(x0), float(y0), float(x1), float(y1))))
insts = [i for i in top.each_inst() if i.cell.name == sram]
print(f"SRAM instances: {len(insts)}; LEF Metal4 supply pins: {len(pins)}")

m4_all = pya.Region(top.begin_shapes_rec(ly.layer(50, 0)))   # Metal4 drawing, whole design
v3_top = pya.Region(top.shapes(ly.layer(49, 0)))             # Via3 cuts placed at top level (PDN)
bad = []
summary = {}
for inst in insts:
    t = inst.dcplx_trans
    for name, box in pins:
        b = t * box
        net = l2n.probe_net(M4p, b.center())
        nname = re.split(r"[$,]", net.name)[0] if net and net.name else None
        # feed: top-level Metal4 shapes crossing the macro edge inside this pin's x-span
        edge = pya.DBox(b.left, b.bottom - 1.0, b.right, b.bottom + 1.0) if b.bottom <= t.disp.y + 0.01 else None
        edge_t = pya.DBox(b.left, b.top - 1.0, b.right, b.top + 1.0) if b.top >= t.disp.y + inst.dbbox().height() - 0.3 else None
        width = 0.0
        for e in (edge, edge_t):
            if e is None: continue
            r = pya.Region(top.shapes(ly.layer(50, 0))) & pya.Region(e.to_itype(dbu))
            width += r.area() * dbu * dbu / 2.0   # band is 2um tall -> summed strap width
        cuts = (v3_top & pya.Region(b.enlarged(0.5, 0.5).to_itype(dbu))).count()
        ok = nname == NETMAP[name]
        if not ok: bad.append((name, b.center().to_s(), nname))
        k = (name, NETMAP[name])
        summary.setdefault(k, []).append((ok, width, cuts))
for (name, want), rows in summary.items():
    nok = sum(1 for ok, _, _ in rows if ok)
    print(f"SRAM {name:10s} -> {want}: {nok}/{len(rows)} pins on net; Metal4 feed width at macro edge "
          f"min/sum {min(w for _, w, _ in rows):.2f}/{sum(w for _, w, _ in rows):.1f} um; Via3 cuts on pins {sum(c for _, _, c in rows)}")
for b in bad[:10]:
    print("  MISWIRED/UNCONNECTED:", b)
fail += len(bad)
print("PASS" if fail == 0 else f"FAIL ({fail})")
sys.exit(1 if fail else 0)
