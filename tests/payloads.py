"""Byte payloads. The engine moves bytes; these are the messages on the wire."""

from __future__ import annotations

import struct
import zlib


def png_1x1(rgb: tuple[int, int, int] = (255, 0, 128)) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes(rgb)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def gif_1x1() -> bytes:
    # 1x1 GIF87a, two-color, one pixel
    return bytes.fromhex(
        "47494638376101000100800100ffffff0000002c000000000100010000020144003b"
    )


def json_nbbo() -> bytes:
    return (
        b'{"sym":"AAPL","bid":192.41,"ask":192.43,'
        b'"bid_sz":200,"ask_sz":150,"ts":1710000000123}'
    )


def json_book() -> bytes:
    return (
        b'{"t":"book","s":"ES","b":[[5000.25,12],[5000.00,8]],'
        b'"a":[[5000.50,10],[5000.75,4]]}'
    )


def json_fill() -> bytes:
    return b'{"t":"fill","oid":"x9k2","px":192.42,"qty":100,"side":"B"}'


def fix_new_order() -> bytes:
    # SOH-separated FIX 4.2 NewOrderSingle (body not checksum-valid; bytes matter)
    return (
        b"8=FIX.4.2\x019=52\x0135=D\x0149=JS\x0156=EXCH\x01"
        b"55=AAPL\x0154=1\x0138=100\x0144=192.42\x0110=000\x01"
    )


def csv_tick() -> bytes:
    return b"AAPL,192.41,192.43,200,150,1710000000123\n"


def packed_tick() -> bytes:
    # sym_id, bid_ticks, ask_ticks, bid_sz, ask_sz, ts_ns
    return struct.pack(">IHHIIQ", 0x4141504C, 19241, 19243, 200, 150, 1710000000123)


PAYLOADS: dict[str, bytes] = {
    "hello": b"Hi",
    "png_1x1": png_1x1(),
    "gif_1x1": gif_1x1(),
    "json_nbbo": json_nbbo(),
    "json_book": json_book(),
    "json_fill": json_fill(),
    "fix_new_order": fix_new_order(),
    "csv_tick": csv_tick(),
    "packed_tick": packed_tick(),
}

PROTOCOLS = ("uart", "spi", "i2c")
