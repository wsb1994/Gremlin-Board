"""Graph stores: where a compiled plan lives until the engine is reprogrammed.

On-chip working set is instruction memory. Larger graphs page in from an
external medium. Media are named by how you attach them, not by protocol
blocks inside the engine.
"""

from __future__ import annotations

from typing import Protocol


class GraphStore(Protocol):
    name: str

    def write(self, graph_id: str, blob: bytes) -> None: ...

    def read(self, graph_id: str) -> bytes: ...


class MemoryStore:
    """Stand-in for an attached RAM/flash chip."""

    name = "memory_chip"

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def write(self, graph_id: str, blob: bytes) -> None:
        self._data[graph_id] = blob

    def read(self, graph_id: str) -> bytes:
        return self._data[graph_id]


class SdStore(MemoryStore):
    """Stand-in for an SD card holding graph pages."""

    name = "sd_card"


class UsbStore(MemoryStore):
    """Stand-in for a USB host streaming graph pages."""

    name = "usb_host"


STORES = (MemoryStore, SdStore, UsbStore)
