"""ASCII wire traces for expect tests (Jane Street waveterm style)."""

from __future__ import annotations


def ascii_bits(name: str, bits: list[int], width: int = 80) -> str:
    body = "".join("█" if b & 1 else "·" for b in bits[:width])
    return f"{name:<4} {body}"


def ascii_bus(channels: dict[str, list[int]], width: int = 80) -> str:
    return "\n".join(ascii_bits(n, bits, width) for n, bits in channels.items()) + "\n"
