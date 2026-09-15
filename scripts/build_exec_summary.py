#!/usr/bin/env python3
"""Build docs/loom-executive-summary.pdf — contest-criteria status only."""

from __future__ import annotations

import math
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "generator"))
OUT = ROOT / "docs" / "loom-executive-summary.pdf"

NAVY = colors.HexColor("#0D2137")
STEEL = colors.HexColor("#1B4F72")
TEAL = colors.HexColor("#0E7C66")
GREEN = colors.HexColor("#1B7A4E")
AMBER = colors.HexColor("#9A6700")
RED = colors.HexColor("#8B1E1E")
LIGHT = colors.HexColor("#F3F5F7")
LINE = colors.HexColor("#C5CDD6")
TEXT = colors.HexColor("#1B1F24")
MUTED = colors.HexColor("#4B5563")
WHITE = colors.white
TEAL_SOFT = colors.HexColor("#D7EFE8")
AMBER_SOFT = colors.HexColor("#F6E8C8")
RED_SOFT = colors.HexColor("#F3E4DC")


def S():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "H1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=13.5, textColor=NAVY, spaceBefore=12, spaceAfter=7, leading=17,
        ),
        "h2": ParagraphStyle(
            "H2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=11, textColor=STEEL, spaceBefore=10, spaceAfter=5, leading=14,
        ),
        "body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.1, textColor=TEXT, leading=12.4, alignment=TA_JUSTIFY, spaceAfter=6,
        ),
        "body_left": ParagraphStyle(
            "BodyL", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9.1, textColor=TEXT, leading=12.4, alignment=TA_LEFT, spaceAfter=6,
        ),
        "cap": ParagraphStyle(
            "Cap", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=MUTED, leading=10.4, alignment=TA_CENTER,
            spaceBefore=2, spaceAfter=9,
        ),
        "cell": ParagraphStyle(
            "Cell", parent=base["BodyText"], fontName="Helvetica",
            fontSize=7.4, textColor=TEXT, leading=9.8, alignment=TA_LEFT,
        ),
        "cellb": ParagraphStyle(
            "CellB", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.4, textColor=NAVY, leading=9.8, alignment=TA_LEFT,
        ),
        "th": ParagraphStyle(
            "TH", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.4, textColor=WHITE, leading=9.8, alignment=TA_LEFT,
        ),
        "yes": ParagraphStyle(
            "Yes", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.4, textColor=GREEN, leading=9.8,
        ),
        "no": ParagraphStyle(
            "No", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.4, textColor=RED, leading=9.8,
        ),
        "part": ParagraphStyle(
            "Part", parent=base["BodyText"], fontName="Helvetica-Bold",
            fontSize=7.4, textColor=AMBER, leading=9.8,
        ),
        "call": ParagraphStyle(
            "Call", parent=base["BodyText"], fontName="Helvetica",
            fontSize=8.8, textColor=NAVY, leading=12.2, alignment=TA_LEFT,
            leftIndent=6, rightIndent=6,
        ),
        "src": ParagraphStyle(
            "Src", parent=base["BodyText"], fontName="Helvetica-Oblique",
            fontSize=8, textColor=MUTED, leading=10.8, alignment=TA_LEFT, spaceAfter=8,
        ),
    }


def P(text, style):
    return Paragraph(text, style)


def is_status(value: str) -> bool:
    v = value.lower().strip()
    return v.startswith(
        ("yes", "no", "partial", "open", "n/a", "proven", "closed")
    )


def result_style(st, value: str):
    v = value.lower().strip()
    if v.startswith("n/a"):
        return st["cell"]
    if v.startswith("yes") or v.startswith("closed") or v.startswith("proven"):
        return st["yes"]
    if v.startswith("no") or v.startswith("not ") or v.startswith("open"):
        return st["no"]
    return st["part"]


def _header_footer(c, doc, first=False):
    w, h = letter
    c.saveState()
    if first:
        c.setFillColor(NAVY)
        c.rect(0, h - 92, w, 92, fill=1, stroke=0)
        c.setFillColor(TEAL)
        c.rect(0, h - 96, w, 4, fill=1, stroke=0)
    else:
        c.setFillColor(NAVY)
        c.rect(0, h - 28, w, 28, fill=1, stroke=0)
        c.setFillColor(WHITE)
        c.setFont("Helvetica", 8)
        c.drawString(54, h - 18, "Loom  ·  Jane Street protocol-emulator ASIC")
        c.drawRightString(w - 54, h - 18, "Criteria status")
    c.setFillColor(LIGHT)
    c.rect(0, 0, w, 30, fill=1, stroke=0)
    c.setFillColor(MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(54, 12, "Tiny Tapeout IHP CMOS5L  ·  6×4 tiles  ·  50 MHz  ·  Apache-2.0")
    c.drawRightString(w - 54, 12, f"{doc.page}")
    c.restoreState()


def on_first(c, doc):
    _header_footer(c, doc, first=True)
    w, h = letter
    c.saveState()
    c.setFillColor(TEAL)
    c.setFont("Helvetica", 8)
    c.drawString(54, h - 28, "JANE STREET PROTOCOL-EMULATOR ASIC CONTEST")
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(54, h - 50, "Criteria status — facts only")
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor("#D5DEE8"))
    c.drawString(54, h - 68, "Mapped to blog.janestreet.com/protocol-emulator-asic-competition")
    c.setFont("Helvetica", 8)
    c.drawRightString(w - 54, h - 68, "2026-09-15")
    c.restoreState()


def on_later(c, doc):
    _header_footer(c, doc, first=False)


def rbox(c, x, y, w, h, fill, stroke, r=5):
    c.setFillColor(fill)
    c.setStrokeColor(stroke)
    c.setLineWidth(0.8)
    c.roundRect(x, y, w, h, r, fill=1, stroke=1)


def label(c, x, y, text, size=7.5, color=TEXT, bold=False, align="c"):
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    if align == "c":
        c.drawCentredString(x, y, text)
    elif align == "l":
        c.drawString(x, y, text)
    else:
        c.drawRightString(x, y, text)


def arrow(c, x1, y1, x2, y2, color=STEEL):
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(1.1)
    c.line(x1, y1, x2, y2)
    ang = math.atan2(y2 - y1, x2 - x1)
    s = 5
    a1 = ang + math.pi * 0.82
    a2 = ang - math.pi * 0.82
    path = c.beginPath()
    path.moveTo(x2, y2)
    path.lineTo(x2 + s * math.cos(a1), y2 + s * math.sin(a1))
    path.lineTo(x2 + s * math.cos(a2), y2 + s * math.sin(a2))
    path.close()
    c.drawPath(path, fill=1, stroke=0)


class ProofStack(Flowable):
    """What was actually proven, stacked from formal ISA down to a real pin."""

    def __init__(self, width):
        super().__init__()
        self._w = width
        self._h = 164

    def wrap(self, *a):
        return self._w, self._h

    def draw(self):
        c, w = self.canv, self._w
        layers = [
            (132, TEAL, WHITE, "k-induction  ·  54 named assertions  ·  1-SM GraphEngine, default CSRs"),
            (100, STEEL, WHITE, "Exhaustive 0..255 on the interpreter  ·  10 of 10 pairs"),
            (68, NAVY, WHITE, "Amaranth RTL pin traces = interpreter  ·  UART / SPI / I2C hello only"),
            (36, colors.HexColor("#3D5A40"), WHITE, "iverilog Hi tests exist on loom_engine  ·  not re-run after USB/CAN rewrite"),
            (4, AMBER, WHITE, "FPGA pin / USB-UART / flash / EEPROM / TAP  ·  not run"),
        ]
        for y, fill, tc, txt in layers:
            rbox(c, 8, y, w - 16, 26, fill, fill, 4)
            label(c, w / 2, y + 9, txt, 7.6, tc, True)


class DieVsSource(Flowable):
    def __init__(self, width):
        super().__init__()
        self._w = width
        self._h = 132

    def wrap(self, *a):
        return self._w, self._h

    def draw(self):
        c, w = self.canv, self._w
        bw = (w - 18) / 2
        rbox(c, 0, 8, bw, 116, TEAL_SOFT, TEAL, 6)
        label(c, bw / 2, 106, "CLOSED GDS  (runs/wokwi, tt_submission)", 8, TEAL, True)
        label(c, bw / 2, 88, "tt_um_loom_gpe instantiates loom_engine", 7.5, NAVY)
        label(c, bw / 2, 74, "1 state machine  ·  1 × 32-word imem", 8, NAVY, True)
        label(c, bw / 2, 58, "3,499 CMOS5L cells   623 FFs", 8, TEXT)
        label(c, bw / 2, 44, "56,492 sq um   ~8% of 6x4 tile area", 7.5, MUTED)
        label(c, bw / 2, 30, "Magic DRC 0  ·  LVS unique match", 7.5, MUTED)
        label(c, bw / 2, 16, "50 MHz  ·  slow setup slack +8.99 ns", 7.5, MUTED)

        rbox(c, bw + 18, 8, bw, 116, AMBER_SOFT, AMBER, 6)
        label(c, bw + 18 + bw / 2, 106, "CURRENT SOURCE  (src/project.v)", 8, AMBER, True)
        label(c, bw + 18 + bw / 2, 88, "tt_um_loom_gpe instantiates loom_chip", 7.5, NAVY)
        label(c, bw + 18 + bw / 2, 74, "2 state machines  ·  4 × 32-word imem", 8, NAVY, True)
        label(c, bw + 18 + bw / 2, 58, "synth 14,944 cells   2,412 FFs", 8, TEXT)
        label(c, bw + 18 + bw / 2, 44, "233,174 sq um   still under 6x4 area", 7.5, MUTED)
        label(c, bw + 18 + bw / 2, 30, "LibreLane P&R stopped in detailed route", 7.5, MUTED)
        label(c, bw + 18 + bw / 2, 16, "no GDS / DRC / LVS for this netlist", 7.5, MUTED)


def grid(data, col_widths):
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("ALIGN", (0, 0), (-1, 0), "LEFT"),
    ]
    for i in range(1, len(data)):
        style.append(("BACKGROUND", (0, i), (-1, i), LIGHT if i % 2 == 0 else WHITE))
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style))
    return t


def metric_strip(st):
    cells = [
        ("1-SM GDS", "closed @ 50 MHz<br/>DRC 0, LVS match"),
        ("54", "k-induction asserts<br/>ISA + FIFO/halt"),
        ("10 x 256", "interp codecs proven<br/>all registered pairs"),
        ("0", "FPGA / real-pin<br/>bring-up runs"),
    ]
    data = [[
        P(
            f"<para align='center'><b><font color='white' size='11'>{a}</font></b>"
            f"<br/><font color='#D5DEE8' size='7'>{b}</font></para>",
            st["cell"],
        )
        for a, b in cells
    ]]
    t = Table(data, colWidths=[126, 126, 126, 126])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, colors.HexColor("#2A4A6A")),
    ]))
    return t


def callout(text, st, fill=TEAL_SOFT, stroke=TEAL):
    t = Table([[P(text, st["call"])]], colWidths=[504])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fill),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.8, stroke),
    ]))
    return t


def status_table(st, rows, widths):
    head = [P(h, st["th"]) for h in rows[0]]
    data = [head]
    for row in rows[1:]:
        cells = [P(row[0], st["cellb"])]
        for i, val in enumerate(row[1:], start=1):
            sty = result_style(st, val) if i == len(row) - 1 else st["cell"]
            cells.append(P(val, sty))
        data.append(cells)
    return grid(data, widths)


def proof_table(st, rows, widths):
    """Last several columns are Yes/Partial/No."""
    head = [P(h, st["th"]) for h in rows[0]]
    data = [head]
    for row in rows[1:]:
        cells = []
        for i, val in enumerate(row):
            if i == 0:
                cells.append(P(val, st["cellb"]))
            elif is_status(val):
                cells.append(P(val, result_style(st, val)))
            else:
                cells.append(P(val, st["cell"]))
        data.append(cells)
    return grid(data, widths)


def build():
    st = S()
    story = []
    usable = 504

    story.append(Spacer(1, 58))
    story.append(
        P(
            "This note maps the Loom repo to the published Jane Street protocol-emulator "
            "ASIC criteria (10 Sep 2026). It records what was measured, what was formally "
            "proven, and what has not been run on a pin. It does not discuss trading "
            "payloads or architecture tutorials.",
            st["body"],
        )
    )
    story.append(
        P(
            "Source: https://blog.janestreet.com/protocol-emulator-asic-competition/  ·  "
            "top <font face='Courier'>tt_um_loom_gpe</font>  ·  tiles 6×4  ·  clock 50 MHz  ·  "
            "license Apache-2.0  ·  407 tests collected under <font face='Courier'>pytest tests</font>.",
            st["src"],
        )
    )
    story.append(
        callout(
            "<b>Status in one paragraph.</b> The design is a reprogrammable pin/time ISA, "
            "not a hardwired UART/SPI/I2C trio. A 1-state-machine CMOS5L GDS closed at 50 MHz "
            "with Magic DRC 0 and a unique LVS match. Current source instantiates a larger "
            "2-SM / 4-slot chip that has been synthesised but not taken to GDS. On the "
            "interpreter, all 10 registered TX/RX pairs are exhaustive codecs for bytes "
            "0..255 against independent spec languages (UART hello, UART 8N1, SPI mode-0 "
            "with CS, I2C open-drain, JTAG TMS TAP, SWD line-reset, PS/2 host byte, CAN "
            "stuffed CRC-15, USB LS NRZI, Ethernet MAC framing). USB and CAN time bits from "
            "a helper clock on pin2; that pin is not part "
            "of those buses. The ISA is k-induction proven on the 1-SM engine (54 named "
            "assertions). UART/SPI/I2C hello pin traces match Amaranth RTL (push-pull I2C, "
            "not the open-drain pair). Nothing has been run on an FPGA or a real peer device.",
            st,
        )
    )
    story.append(Spacer(1, 8))
    story.append(metric_strip(st))
    story.append(Spacer(1, 8))

    # ----- 1. Criteria -----
    story.append(P("1. Contest criteria, as published", st["h1"]))
    story.append(
        P(
            "Quoted requirements are from the contest page. Status is taken from this tree "
            "(plans, tests, LibreLane runs, formal log). “Partial” means the letter of the "
            "item is addressed in simulation or in a subset graph, not on silicon and not "
            "as a full PHY.",
            st["body"],
        )
    )

    crit = [
        ("Criterion", "What this repo has", "Status"),
        (
            "Open-source general-purpose protocol emulator ASIC",
            "16-bit pin/wait/delay/shift/fifo/jump/mov ISA. Protocols are TOML graphs in "
            "plans/, loaded into imem after tapeout. Engine core is forbidden from naming "
            "a protocol (loom check).",
            "Yes — as RTL/graphs",
        ),
        (
            "Not a UART + SPI + I2C block trio; new protocols after fabrication",
            "Host two-phase imem write + TX FIFO + run, documented in docs/info.md, tested "
            "in tests/test_host_load.py (Amaranth). Reprogram uart→spi→i2c on one interpreter "
            "object. Same engine, new words; no resynth.",
            "Yes — in simulation",
        ),
        (
            "Start with UART, SPI, and I2C",
            "UART 8N1; SPI mode-0 MOSI/SCK/CS; I2C open-drain START / 8 bits / ACK / STOP. "
            "All three proven 0..255 on the interpreter. Push-pull I2C hello graphs still "
            "exist and are not the I2C formal case.",
            "Yes — graphs + interp proof",
        ),
        (
            "Stretch: low-speed USB and 10 Mbit Ethernet",
            "USB LS: NRZI (0=toggle, 1=hold), stuff after six 1s, SYNC KJKJKJKK, EOP SE0 "
            "on D+/D−, timed from pin2. Ethernet: IEEE 802.3 MAC framing (seven 0x55 + "
            "0xD5 SFD + payload) on clock+data. Neither is an analog PHY.",
            "Partial — digital line language",
        ),
        (
            "Also named: JTAG, SWD, PS/2, CAN",
            "JTAG: TMS TAP (TLR via ≥5 TMS=1, then Shift-DR). SWD: ≥50 SWDIO=1 clocks then "
            "8 LSB. PS/2: host byte, odd parity, device ACK. CAN: SOF + both-polarity stuff "
            "through CRC-15 (0x4599) + ACK 0; proven 0..255 on the interpreter. Helper clock pin2.",
            "Partial — bit-level graphs, not full stacks",
        ),
        (
            "FPGA smoke of RTL before ASIC flow",
            "Named in the brief. Not run. No iCEBreaker / TT demo-board log in this tree.",
            "No",
        ),
        (
            "Formal methods",
            "Yosys sat k-induction of ISA one-step semantics + FIFO/halt/imem (54 named "
            "assertions). Log: Induction step proven: SUCCESS! (test/gen/formal.log). "
            "Harness is GraphEngine() default: 1 SM, 1 slot, clkdiv=1, wrap 0..31, sideset off.",
            "Yes — ISA, not protocols",
        ),
        (
            "Random constrained tests",
            "tests/test_random_jitter.py: UART baud error / edge jitter / runt starts; "
            "SPI clock asymmetry, gaps, MOSI noise while SCK low. Decoder is the graph, "
            "waveforms are synthesised, not taken from TX.",
            "Yes — UART/SPI interp",
        ),
        (
            "IHP 130 nm CMOS5L via Tiny Tapeout; start from CMOS5L Verilog template",
            "ttihp-verilog-template CMOS5L. info.yaml tiles 6x4, clock_hz 50000000, "
            "CLOCK_PERIOD 20. LibreLane run runs/wokwi completed through GDS.",
            "Yes",
        ),
        (
            "Area: 6×4 tiles (~0.7 mm², ~1k cells/tile ≈ 24k cell budget)",
            "Closed GDS (1 SM): 3,499 cells, 56,492 µm². Current 2-SM synth: 14,944 cells, "
            "233,174 µm². Both under the 6×4 budget. Imem is stdcell FFs, not SRAM.",
            "Yes — under budget",
        ),
        (
            "Full P&amp;R + timing at a declared clock",
            "1-SM GDS: setup/hold WNS 0 at 50 MHz; slow-corner setup slack +8.986 ns. "
            "Magic DRC COUNT 0. Netgen: Circuits match uniquely. KLayout DRC was skipped "
            "(RUN_KLAYOUT_DRC false). Slow corner: 8 max-slew, 37 max-fanout violations. "
            "2-SM/4-slot P&amp;R stopped in detailed routing; no GDS.",
            "Yes — 1-SM GDS only",
        ),
        (
            "Open source; build in public",
            "Apache-2.0. git remote: github.com/wsb1994/Gremlin-Board.",
            "Yes",
        ),
        (
            "Sign-up form / submit by 2027-01-18",
            "Neither form is in the repo. Deadline is in the future.",
            "Open",
        ),
    ]
    story.append(status_table(st, crit, [118, 286, 100]))
    story.append(P(
        "Table 1. Published contest items versus this tree. Status is not a score.",
        st["cap"],
    ))

    # ----- 2. Die vs source -----
    story.append(P("2. What closed GDS, versus what the source emits now", st["h1"]))
    story.append(
        P(
            "emit.py writes two engines into src/loom_engine.v: loom_engine (1 SM, 1 slot) "
            "and loom_chip (2 SM, 4 slots). The completed LibreLane GDS instantiated "
            "loom_engine (623 FFs matches 32×16-bit imem plus SM/FIFO/host state). "
            "src/project.v now instantiates loom_chip. Those are different netlists.",
            st["body"],
        )
    )
    story.append(DieVsSource(usable))
    story.append(P(
        "Figure 1. Closed CMOS5L GDS is the 1-SM engine. The 2-SM / 4-slot source has synth numbers only.",
        st["cap"],
    ))
    story.append(
        P(
            "k-induction, iverilog protocol tests, and the exhaustive ISA sweep all target "
            "GraphEngine() / loom_engine (1 SM, 1 slot). Dual-SM behaviour is covered by "
            "unit tests in tests/test_dual_sm.py (interpreter and Amaranth), not by the GDS "
            "and not by the k-induction harness.",
            st["body"],
        )
    )

    # ----- 3. Protocol paths -----
    story.append(P("3. Named protocols: what the graphs are", st["h1"]))
    story.append(
        P(
            "The brief lists UART, SPI, I2C as the start, USB LS and 10 Mbit Ethernet as "
            "stretch, and JTAG, SWD, PS/2, CAN as further examples. Every name has a graph "
            "pair in plans/. Assembled length is compile_plan word count / 32. The graph is "
            "not the full protocol unless the last column says so.",
            st["body"],
        )
    )
    proto = [
        ("Protocol", "Graphs (words)", "What the graph actually does", "Full protocol?"),
        (
            "UART",
            "uart_tx/rx 9/8, uart_8n1_* 9/15, uart_rx_frame 15",
            "8N1 on pin0, LSB first, 8 SM-cycles/bit. Production RX: centre sample, start verify, "
            "stop check, frame-error flag on pin1.",
            "Yes — 8N1 byte",
        ),
        (
            "SPI",
            "spi_tx 11, spi_rx 8",
            "Mode 0, MOSI=pin0, SCK=pin1, CS=pin2 active-low, MSB first.",
            "Partial — mode-0 byte with CS",
        ),
        (
            "I2C hello",
            "i2c_tx 15, i2c_rx 9",
            "Push-pull bit dance on SDA/SCL. Not the formal I2C case.",
            "No — cartoon",
        ),
        (
            "I2C open-drain",
            "i2c_od_tx 22, i2c_od_rx 12",
            "gpio_out stays 0; drive-0 is OE. START, 8 MSB, ACK 0, STOP. "
            "Golden slave is in tests/test_i2c_opendrain.py, not on the die.",
            "Partial — 1-byte master write",
        ),
        (
            "JTAG",
            "jtag_tx 31, jtag_shift 15",
            "TMS TAP: ≥5 TMS=1 (TLR), then Shift-DR, 8 TDI LSB, Update-DR.",
            "Partial — 8-bit Shift-DR, not IDCODE",
        ),
        (
            "SWD",
            "swd_tx 16, swd_rx 10",
            "≥50 clocks with SWDIO=1, then 8 LSB on SWCLK. No DPIDR parse.",
            "Partial — line-reset + byte, not DPIDR",
        ),
        (
            "PS/2",
            "ps2_tx 29, ps2_rx 14",
            "Host-clocked byte: start, 8 LSB, odd parity, stop, ACK 0.",
            "Partial — host byte, not a keyboard host",
        ),
        (
            "CAN",
            "can_tx 32, can_rx 32",
            "TX: SOF, 8 LSB, both-polarity stuff through CRC-15 (poly 0x4599), ACK 0, one clocked "
            "recessive; parks on pull. RX: destuff 5 identical of either polarity, then wait TX "
            "pin4 (CRC-phase) before the next SOF. Helper clock pin2.",
            "Partial — stuffed 1-byte data frame, not a CAN node",
        ),
        (
            "USB LS",
            "usb_tx 32, usb_rx 32",
            "NRZI (0=toggle, 1=hold), stuff after six 1s, SYNC KJKJKJKK, EOP SE0 on D+/D−. "
            "RX samples D+ against previous level on pin3. Helper bit-clock pin2 (not a USB wire).",
            "Partial — NRZI packet, not analog PHY",
        ),
        (
            "10 Mbit Ethernet",
            "eth_tx 32, eth_rx 13",
            "Seven 0x55 + 0xD5 SFD + payload on data+clock. Plan text: not 10BASE-T magnetics.",
            "Partial — 802.3 framing, not 10BASE-T",
        ),
    ]
    story.append(proof_table(st, proto, [78, 118, 218, 90]))
    story.append(P(
        "Table 2. Contest-named protocols versus the shipped graphs. “Full protocol?” is relative to the named standard, not to a byte round-trip.",
        st["cap"],
    ))

    # ----- 4. Formal per path -----
    story.append(P("4. Was each path formally proven?", st["h1"]))
    story.append(
        P(
            "Two different claims live in this repo. They are not interchangeable.",
            st["body_left"],
        )
    )
    story.append(
        P(
            "<b>1. ISA k-induction (RTL, protocol-agnostic).</b> "
            "generator/loom/formal.py. Yosys <font face='Courier'>sat -tempinduct</font>, "
            "54 named assertions: FIFO occupancy/pointers, halt freezes the SM, run blocks "
            "imem writes, and one-step semantics of NOP, JMP (all fields), WAIT, IN, OUT, "
            "FIFO pull/push, SET (all fields), MOV dests with payload ≤ 6 (including dest ^= Y). "
            "MOV payloads 7–11 (hidden 15-bit CRC, poly 0x4599) are unconstrained in that proof. "
            "Log ends “Induction step proven: SUCCESS!”. The harness ties csr_we=0, so clkdiv "
            "stays 1, wrap 0..31, sideset off. It does not mention UART, SPI, or I2C. It does "
            "not prove a protocol waveform. It is the 1-SM GraphEngine, not loom_chip.",
            st["body"],
        )
    )
    story.append(
        P(
            "<b>2. Protocol completeness (interpreter, finite alphabet).</b> "
            "generator/loom/formal_proto.py, invoked as <font face='Courier'>loom formal-proto</font>. "
            "For each registered TX/RX pair and every byte b in 0..255: TX(b) is a word of the "
            "spec language L; RX(spec(b))=b; RX(TX(b))=b; after one byte the SM sits on "
            "pull. Spec waves come from generator/loom/line_lang.py (SPECS), not from the TX "
            "graph. That is exhaustive model checking of an 8-bit FIFO engine on the "
            "<i>interpreter</i>, not k-induction of RTL. Measured this session: 10 of 10 pairs "
            "complete (see Table 3).",
            st["body"],
        )
    )
    story.append(
        callout(
            "<b>Composition, stated as a composition, not as a solver run.</b> If RTL "
            "implements the ISA (k-induction, 1 SM, default CSRs) and a graph is a codec on "
            "the interpreter (all 256 bytes), then RTL executing that graph is a codec "
            "<i>under those CSR defaults</i>. That argument is written in formal_proto.py. "
            "It has not been discharged as one formal property. Independent of that, "
            "Amaranth RTL pin traces were compared to the interpreter for UART/SPI/I2C "
            "hello only.",
            st,
            fill=AMBER_SOFT,
            stroke=AMBER,
        )
    )
    story.append(Spacer(1, 8))
    story.append(ProofStack(usable))
    story.append(P(
        "Figure 2. Proof and test layers. A layer does not imply the ones below it.",
        st["cap"],
    ))

    paths = [
        ("Path", "Exhaustive 0..255 interp", "Amaranth RTL pins", "Interpreter Hi", "k-ind of this waveform"),
        ("uart_tx / uart_rx", "Yes", "Yes (Hi trace)", "Yes (165 cyc)", "No"),
        ("uart_8n1_tx / uart_8n1_rx", "Yes", "No", "codec 0..255", "No"),
        ("spi_tx / spi_rx", "Yes", "Yes (Hi; graphs now have CS)", "Yes (76 cyc)", "No"),
        ("i2c_tx / i2c_rx (push-pull)", "No — not the formal case", "Yes (Hi trace)", "not the PAIRS pair", "No"),
        ("i2c_od_tx / i2c_od_rx", "Yes", "No", "Yes (142 cyc)", "No"),
        ("jtag_tx / jtag_shift", "Yes", "No", "Yes (164 cyc)", "No"),
        ("swd_tx / swd_rx", "Yes", "No", "Yes (385 cyc)", "No"),
        ("ps2_tx / ps2_rx", "Yes", "No", "Yes (166 cyc)", "No"),
        (
            "can_tx / can_rx",
            "Yes vs can_spec_wave",
            "No",
            "Yes (640 cyc)",
            "No",
        ),
        ("usb_tx / usb_rx", "Yes vs usb_spec_wave", "No", "Yes (566 cyc)", "No"),
        ("eth_tx / eth_rx", "Yes vs eth_spec_wave", "No", "Yes (554 cyc)", "No"),
        ("ISA step (all 8 opcodes)", "n/a", "golden snapshots", "2048 encodings × 7 stimuli (test exists)", "Yes — 1 SM"),
    ]
    story.append(proof_table(st, paths, [108, 148, 88, 72, 88]))
    story.append(P(
        "Table 3. Per-path evidence. “k-ind of this waveform” would mean a solver proof that "
        "the RTL pin trace is the protocol. That was not done for any protocol. ISA k-induction "
        "is the last row.",
        st["cap"],
    ))

    extra = [
        ("Other verification named by the brief", "Where", "Result"),
        (
            "Constrained-random UART/SPI pins",
            "tests/test_random_jitter.py (interpreter)",
            "Yes — those graphs",
        ),
        (
            "ASCII waveform expects (JS 2020 style)",
            "tests/expect/uart_hi.txt, spi_hi.txt",
            "Yes — UART/SPI hello",
        ),
        (
            "I2C open-drain ACK + stretch vs model",
            "tests/test_i2c_opendrain.py (interpreter)",
            "Yes — vs software slave",
        ),
        (
            "Host load two-phase imem + FIFO",
            "tests/test_host_load.py (Amaranth + wrapper model)",
            "Yes — simulation",
        ),
        (
            "iverilog Hi on loom_engine",
            "tests/test_verilog_sim.py (every PAIRS name). TB ties gpio_in to gpio_out (no pull-up / OE).",
            "Test exists — not re-run this session",
        ),
        (
            "Gate-level cocotb",
            "test/test.py",
            "Partial — idle only (run=0)",
        ),
        (
            "Non-default clkdiv / wrap / sideset in k-induction",
            "formal.py comments: covered by interp≡RTL tests, not by sat",
            "No — not in the proof",
        ),
        (
            "2-SM / 4-slot engine in k-induction or GDS",
            "formal harness GraphEngine(); GDS is loom_engine",
            "No",
        ),
    ]
    story.append(status_table(st, extra, [170, 214, 120]))
    story.append(P("Table 4. Other verification the contest page asked for by name.", st["cap"]))

    # ----- 5. Simulator / real use -----
    story.append(P("5. Is the simulator usable in a real scenario?", st["h1"]))
    story.append(
        P(
            "“Simulator” here is the cycle-accurate ISA interpreter (loom.interp) plus, "
            "where noted, Amaranth simulation and iverilog on generated Verilog. None of "
            "these models pads, cables, analog PHYs, or a real peer device. GPIO inputs are "
            "2-flop synchronised in RTL while running; the interpreter does not model that "
            "synchroniser. loom.stream.roundtrip uses a wired-AND pull-up so open-drain ACK "
            "(I2C, PS/2) can work in that helper; a raw pin does not.",
            st["body"],
        )
    )
    story.append(
        callout(
            "<b>What it is usable for.</b> Authoring a graph, checking that a TX/RX pair "
            "recovers every byte 0..255, locking an ASCII pin trace, and comparing "
            "interpreter vs Amaranth vs iverilog before tapeout. That is a real use in a "
            "design flow. It is not a protocol analyser, not a stand-in for an FPGA board, "
            "and not evidence that a USB-UART, SPI flash, I2C EEPROM, JTAG TAP, or SWD "
            "target would lock.",
            st,
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        P(
            "The contest’s stated job for the chip is hardware debugging and reverse "
            "engineering: bit-bang what is on the desk, within this die’s rates and 8 GPIO. "
            "At 50 MHz with 8 SM-cycles/bit, clkdiv=1 is a 6.25 Mbit/s class line; 115200 "
            "8N1 is inside the divider range (clkdiv ≈ 54). That is a cycle-budget fact, "
            "not a bring-up result.",
            st["body"],
        )
    )

    real = [
        ("Desk scenario", "Graph that would be loaded", "Simulator evidence", "Usable on a real pin today?"),
        (
            "UART 115200 8N1 to a USB-UART",
            "uart_8n1_tx / uart_8n1_rx",
            "Codec 0..255 on interp; jitter/runt tests on uart_rx_frame and uart_8n1_rx. "
            "RTL pin match is the hello pair, not 8n1.",
            "No — never driven off-chip",
        ),
        (
            "SPI mode-0 flash JEDEC ID (0x9F)",
            "spi_tx / spi_rx",
            "Byte codec 0..255 with CS. No flash in the formal suite.",
            "No — no flash",
        ),
        (
            "I2C EEPROM read, addr 0x50",
            "i2c_od_tx / i2c_od_rx",
            "Codec 0..255. Master write 0xA0 then 0x48 with ACK and stretch vs a software slave.",
            "No — model only",
        ),
        (
            "JTAG TAP IDCODE",
            "jtag_tx / jtag_shift",
            "8-bit Shift-DR after TLR, codec 0..255. A 32-bit IDCODE sequence is not the graph.",
            "No — cannot IDCODE",
        ),
        (
            "SWD line reset + DPIDR",
            "swd_tx / swd_rx",
            "Line-reset (≥50 SWDIO=1 clocks) + 8 data bits, codec 0..255. No DPIDR parse.",
            "No — cannot DPIDR",
        ),
        (
            "PS/2 keyboard byte",
            "ps2_tx / ps2_rx",
            "Host byte with odd parity and ACK, codec 0..255 on the interpreter.",
            "No — never a keyboard",
        ),
        (
            "Low-speed USB device/host",
            "usb_tx / usb_rx",
            "NRZI+stuff+SYNC+EOP codec 0..255 on interp. RX/TX use pin2 as a bit-clock a USB cable does not carry. No analog PHY.",
            "No — not a USB PHY; extra clock pin",
        ),
        (
            "10BASE-T Ethernet",
            "eth_tx / eth_rx",
            "Preamble/SFD/payload codec 0..255 on clock+data. Not Manchester, not magnetics.",
            "No — not 10BASE-T",
        ),
        (
            "CAN 2.0 at 125 kbit",
            "can_tx / can_rx",
            "Stuffed CRC-15 codec 0..255 on interp; Hi and PNG SHA-256 round-trip. Helper clock pin2. No analog PHY, no arbitration.",
            "No — not a CAN transceiver",
        ),
        (
            "Reprogram after fab (halt, load a new graph, run)",
            "any pair, same engine",
            "Interpreter reprogram test; host-load Amaranth test. Dual-SM UART TX+RX on internal GPIO in interp.",
            "No — no board",
        ),
    ]
    story.append(proof_table(st, real, [108, 100, 176, 120]))
    story.append(P(
        "Table 5. Real-scenario usability. “No” means this tree has not talked to that device, "
        "and/or the graph is not the protocol that device speaks.",
        st["cap"],
    ))
    story.append(
        P(
            "After fabrication of the closed 1-SM GDS, a host could in principle load "
            "uart_8n1 or spi or i2c_od and bit-bang those byte-level contracts on 8 GPIO, "
            "at rates the 50 MHz divider can hit. That is an architectural claim plus "
            "simulation. It has not been demonstrated. The 2-SM / 4-slot source would add "
            "concurrent graphs; that netlist has no GDS.",
            st["body"],
        )
    )

    # ----- 6. Remaining -----
    story.append(P("6. Remaining contest items", st["h1"]))
    remain = [
        ("Item", "Why it is still open"),
        ("Sign-up form on the contest page", "Required to receive the submission link. Not a commit."),
        ("Final submission by 2027-01-18", "Form is not on the page yet; nothing submitted."),
        ("FPGA smoke of UART Hi on a pin", "Named in the brief. No board log in this tree."),
        ("P&amp;R / GDS of the 2-SM / 4-slot netlist", "Synth fits 6×4; LibreLane stopped in detailed routing."),
        ("KLayout DRC", "Skipped on the closed 1-SM run (RUN_KLAYOUT_DRC false). Magic DRC was 0."),
        ("Gate-level UART Hi", "cocotb GATES=yes presently asserts only that run=0 after reset."),
        ("k-induction of loom_chip, clkdiv, wrap, sideset, CRC MOV", "Harness is 1-SM defaults; CRC MOV unconstrained."),
        ("End-to-end formal of a protocol waveform on RTL", "Not done for any named protocol."),
        ("CAN analog PHY / multi-node arbitration", "Interpreter codec is a 1-byte stuffed data frame on GPIO+clock."),
        ("Any T1–T8 desk test (USB-UART, W25, EEPROM, TAP, DPIDR)", "Simulation and models only."),
        ("8×4 tile", "Contest may offer it later. CMOS5L tooling in this tree defines 6×4."),
    ]
    data = [[P(remain[0][0], st["th"]), P(remain[0][1], st["th"])]]
    for a, b in remain[1:]:
        data.append([P(a, st["cellb"]), P(b, st["cell"])])
    story.append(grid(data, [200, 304]))
    story.append(P("Table 6. Open items relative to the published brief.", st["cap"]))

    story.append(
        callout(
            "<b>Bottom line against the brief.</b> Architecture matches: a PIO-class "
            "reprogrammable pin/time engine, open source, on the CMOS5L 6×4 template, "
            "with a timing-closed 1-SM GDS. UART, SPI (mode-0 with CS), and open-drain I2C "
            "graphs exist and are exhaustive codecs on the interpreter. Stretch USB and "
            "Ethernet are digital line languages (NRZI packet; 802.3 framing on clock+data), "
            "not analog PHYs, and those codecs are proven 0..255 on the interpreter. "
            "JTAG/SWD/PS/2/CAN graphs implement the named bit-level mechanics in 32 words and "
            "are proven the same way. Formal "
            "methods were applied to the ISA, not to each protocol path on RTL. The "
            "simulator is usable as a graph lab; it is not evidence of a real-desk protocol "
            "emulator until a pin test exists.",
            st,
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        P(
            "Rebuild: PYTHONPATH=generator python scripts/build_exec_summary.py. "
            "Evidence files: test/gen/formal.log, runs/wokwi (GDS), "
            "src/runs/loom-chip (2-SM synth), generator/loom/formal.py, "
            "generator/loom/formal_proto.py, docs/info.md.",
            st["src"],
        )
    )

    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=42,
        bottomMargin=42,
        title="Loom — Jane Street protocol-emulator ASIC, criteria status",
        author="Loom",
        subject="Factual mapping to the published contest criteria",
    )
    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    print(OUT)


if __name__ == "__main__":
    build()
