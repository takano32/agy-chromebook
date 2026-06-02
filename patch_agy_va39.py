#!/usr/bin/env python3
from pathlib import Path


TARGET = Path("agy")
START = 0x4A3BB80
END = 0x4AD6784


def patch_at(data, off, old_hex, new_hex):
    old = bytes.fromhex(old_hex)
    new = bytes.fromhex(new_hex)
    got = data[off : off + len(old)]
    if got != old:
        raise SystemExit(
            f"mismatch at 0x{off:x}: got {got.hex()} expected {old.hex()}"
        )
    data[off : off + len(old)] = new


def replace_in_google_malloc(data, old_hex, new_hex, label):
    old = bytes.fromhex(old_hex)
    new = bytes.fromhex(new_hex)
    count = 0
    pos = START
    while True:
        found = data.find(old, pos, END)
        if found < 0:
            break
        data[found : found + len(old)] = new
        count += 1
        pos = found + len(new)
    print(f"{label}: {count}")


def main():
    data = bytearray(TARGET.read_bytes())

    # TCMalloc address-placement hints: move the 3-bit VA tag from bits 42-44
    # to bits 36-38 and constrain randomized hints to the 39-bit VA range.
    patch_at(data, 0x4A950B4, "28b16ad3", "289964d3")
    patch_at(data, 0x4A950E0, "7c5656d3", "7c6e5cd3")
    patch_at(data, 0x4A9511C, "0a80d3920a00e0f2", "ea8f40b21f2003d5")
    patch_at(data, 0x4A951F4, "0a80d3920a00e0f2", "ea8f40b21f2003d5")
    patch_at(data, 0x4A95320, "0a80d3920a00e0f2", "ea8f40b21f2003d5")
    patch_at(data, 0x4A953A8, "80b26ad3", "809a64d3")
    patch_at(data, 0x4A95500, "08b16ad3", "089964d3")
    patch_at(data, 0x4A9550C, "7c5656d3", "7c6e5cd3")

    # Free/release paths: extract the tag from bits 36-38.
    for off in (
        0x4A52150,
        0x4A54C90,
        0x4A55060,
        0x4A553C0,
        0x4A55810,
        0x4A55C60,
        0x4A56010,
        0x4A563E0,
        0x4A5E290,
        0x4A659B0,
        0x4A6D0D0,
    ):
        patch_at(data, off, "68b26ad3", "689a64d3")
    patch_at(data, 0x4AC1F84, "80b26ad3", "809a64d3")

    # Fast-path tag masks and tag-4 checks.
    replace_in_google_malloc(data, "6c0a5692", "6c0a5c92", "and x12 tag mask")
    replace_in_google_malloc(data, "6a0a5692", "6a0a5c92", "and x10 tag mask")
    replace_in_google_malloc(data, "0d00c3d2", "0d0cc0d2", "mov x13 tag value")
    replace_in_google_malloc(data, "0c00c3d2", "0c0cc0d2", "mov x12 tag value")
    replace_in_google_malloc(data, "0a00c3d2", "0a0cc0d2", "mov x10 tag value")
    replace_in_google_malloc(data, "1f0455f2", "1f045bf2", "tst x0 tag bits")
    replace_in_google_malloc(data, "5f0455f2", "5f045bf2", "tst x2 tag bits")
    replace_in_google_malloc(
        data,
        "e84b50b20900c2d20800c2f2",
        "0808c0d2080940b20908c0d2",
        "tag4 mask/value sequence",
    )

    TARGET.write_bytes(data)


if __name__ == "__main__":
    main()
