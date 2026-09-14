"""Write 1-bit pin traces as VCD. No protocol knowledge."""

from __future__ import annotations

from pathlib import Path


def write_vcd(
    path: str | Path,
    channels: dict[str, list[int]],
    timescale: str = "1 us",
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = list(channels)
    if not names:
        raise ValueError("no channels")
    n = len(channels[names[0]])
    if any(len(channels[k]) != n for k in names):
        raise ValueError("channel lengths differ")
    ids = [chr(33 + i) for i in range(len(names))]  # ! " # ...
    prev: list[int | None] = [None] * len(names)
    lines = [
        "$timescale %s $end" % timescale,
        "$scope module loom $end",
    ]
    for ident, name in zip(ids, names):
        lines.append(f"$var wire 1 {ident} {name} $end")
    lines += ["$upscope $end", "$enddefinitions $end"]
    for t in range(n):
        changed = False
        chunk = [f"#{t}"]
        for i, name in enumerate(names):
            bit = int(channels[name][t]) & 1
            if bit != prev[i]:
                chunk.append(f"{bit}{ids[i]}")
                prev[i] = bit
                changed = True
        if changed:
            lines.extend(chunk)
    path.write_text("\n".join(lines) + "\n")
    return path
