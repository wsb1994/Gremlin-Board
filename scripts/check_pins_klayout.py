"""Independent check that every Tiny Tapeout pin of the hardened GDS is where the
template wants it, is on its own net, and reaches standard cells.

For each pin in the TT block template DEF (ui_in, uo_out, uio_*, ena, clk,
rst_n, VPWR, VGND):
  * a same-named label exists at the top level of the GDS inside the template
    rectangle (position + layer),
  * KLayout net extraction (Metal1..Metal4 + vias, stdcells flattened) puts that
    label on a net carrying no other port label (no port-to-port or
    port-to-supply short),
  * the net's Metal1 overlaps at least one logic standard cell (fill/decap/tap
    excluded), so the pin is wired to logic rather than dangling.

    klayout -b -r scripts/check_pins_klayout.py -rd gds=<final.gds> \
        -rd template=tt/tech/ihp-sg13cmos5l/def/tt_block_6x4_pgvdd.def
"""
import re, sys
import pya

gds = globals()["gds"]
template = globals().get("template", "tt/tech/ihp-sg13cmos5l/def/tt_block_6x4_pgvdd.def")
PHYS = ("sg13cmos5l_fill_", "sg13cmos5l_decap_", "sg13cmos5l_tap", "sg13cmos5l_antenna", "sg13cmos5l_endcap")

# --- template pins ---------------------------------------------------------
d = open(template).read()
pins_txt = d[d.index("PINS"):d.index("END PINS")]
tpl = {}
for m in re.finditer(r"- (\S+) \+ NET \S+(.*?);", pins_txt, re.S):
    name, body = m.group(1), m.group(2)
    lay = re.search(r"LAYER (\S+) \( (-?\d+) (-?\d+) \) \( (-?\d+) (-?\d+) \)", body)
    fx = re.search(r"(?:FIXED|PLACED) \( (-?\d+) (-?\d+) \)", body)
    if not lay or not fx:
        continue
    l, x0, y0, x1, y1 = lay.group(1), *map(int, lay.groups()[1:])
    px, py = int(fx.group(1)), int(fx.group(2))
    tpl[name] = (l, pya.DBox((px + x0) / 1000.0, (py + y0) / 1000.0, (px + x1) / 1000.0, (py + y1) / 1000.0))
print(f"template pins: {len(tpl)}")

# --- layout ----------------------------------------------------------------
ly = pya.Layout(); ly.read(gds)
top = ly.top_cell(); dbu = ly.dbu
LN = {"Metal1": 8, "Metal2": 10, "Metal3": 30, "Metal4": 50}
l2n = pya.LayoutToNetlist(pya.RecursiveShapeIterator(ly, top, []))
def mk(n, ln, dt): return l2n.make_layer(ly.layer(ln, dt), n)
M = {k: mk(k, v, 0) for k, v in LN.items()}
Mp = {k: mk(k + "p", v, 2) for k, v in LN.items()}
V = {"V1": mk("V1", 19, 0), "V2": mk("V2", 29, 0), "V3": mk("V3", 49, 0)}
for r in list(M.values()) + list(Mp.values()) + list(V.values()):
    l2n.connect(r)
for k in LN:
    l2n.connect(M[k], Mp[k])
for a, v, b in (("Metal1", "V1", "Metal2"), ("Metal2", "V2", "Metal3"), ("Metal3", "V3", "Metal4")):
    l2n.connect(M[a], V[v]); l2n.connect(V[v], M[b])
for k, ln in LN.items():
    t = l2n.make_text_layer(ly.layer(ln, 25), k + "lbl"); l2n.connect(M[k], t)
l2n.extract_netlist()
circ = l2n.netlist().circuit_by_name(top.name)

# labels at top level
labels = {}
for k, ln in LN.items():
    for s in top.shapes(ly.layer(ln, 25)).each():
        if s.is_text():
            v = s.text_trans.disp * dbu
            labels.setdefault(s.text_string, []).append((k, pya.DPoint(v.x, v.y)))

# logic cell instance boxes (for "reaches logic")
cells = [i.dbbox() for i in top.each_inst()
         if i.cell.name.startswith("sg13cmos5l_") and not i.cell.name.startswith(PHYS)]
print(f"logic std cells: {len(cells)}")

fail = 0
rows = []
for name, (layer, box) in sorted(tpl.items(), key=lambda kv: kv[0]):
    if name not in labels:
        rows.append((name, "MISSING LABEL", "", 0)); fail += 1; continue
    # the label sits at the pin centre; allow the label to be snapped to grid
    inside = [(k, p) for k, p in labels[name] if k == layer and box.enlarged(0.5, 0.5).contains(p)]
    if not inside:
        rows.append((name, f"label not in template rect on {layer}", "", 0)); fail += 1; continue
    k, p = inside[0]
    # probe the pin metal itself (template rectangle centre); the label is
    # attached to the same net through the text layer
    net = l2n.probe_net(M[k], box.center())
    nname = net.name if net else None
    if not nname:
        rows.append((name, f"no Metal4 pin at template centre {box.center()} (label at {p})", "", 0)); fail += 1; continue
    if name not in {n.split("$")[0] for n in nname.split(",")}:
        rows.append((name, f"pin metal net is {nname!r}, label elsewhere", nname, 0)); fail += 1; continue
    names = set(re.split(r"[,]", nname))
    names = {n.split("$")[0] for n in names}
    others = names - {name}
    if others:
        rows.append((name, f"SHORT with {sorted(others)[:4]}", nname, 0)); fail += 1; continue
    # reach: Metal1 shapes of this net vs logic cell boxes
    reg = l2n.shapes_of_net(net, M["Metal1"], True)
    nreach = 0
    if reg is not None and not reg.is_empty():
        bb = reg.bbox()
        for cb in cells:
            if cb.to_itype(dbu).overlaps(bb) and not (reg & pya.Region(cb.to_itype(dbu))).is_empty():
                nreach += 1
    ok = nreach > 0
    if not ok: fail += 1
    rows.append((name, "ok" if ok else "REACHES NO LOGIC CELL", nname, nreach))

w = max(len(r[0]) for r in rows)
for name, status, nn, nreach in rows:
    print(f"{name:{w}s}  {status:28s} cells_on_net={nreach}")
print("PASS" if fail == 0 else f"FAIL ({fail})")
sys.exit(1 if fail else 0)
