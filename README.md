# agy VA39 Binary Patch Notes

This directory contains a patched `agy` binary for AArch64 systems with a
39-bit user virtual address space.

## Problem

The original `agy` binary failed before normal startup because its embedded
TCMalloc build assumed a 48-bit virtual address space. On this Chromebook
environment, the process runs under a 39-bit virtual address limit, so
TCMalloc attempted to place internal metadata outside the usable VA range.

The original failure was:

```text
third_party/tcmalloc/internal/system_allocator.h:603] MmapAligned() failed - unable to allocate with tag (hint=0xdb700000000, size=1073741824, alignment=1073741824) - is something limiting address placement?
third_party/tcmalloc/internal/system_allocator.h:610] Note: the allocation may have failed because TCMalloc assumes a 48-bit virtual address space size; you may need to rebuild TCMalloc with TCMALLOC_ADDRESS_BITS defined to your system's virtual address space size
third_party/tcmalloc/arena.cc:61] CHECK in Alloc: FATAL ERROR: Out of memory trying to allocate internal tcmalloc data (bytes=131072, object-size=16384); is something preventing mmap from succeeding (sandbox, VSS limitations)?
```

There is no source tree here, so the fix was made by reading and patching the
stripped binary.

## Files

- `agy`: patched executable.
- `agy.orig`: backup of the original executable.
- `patch_agy_va39.py`: reproducible binary patcher that transforms `agy.orig`
  into the patched `agy`.

The binary is:

```text
ELF 64-bit LSB pie executable, ARM aarch64, dynamically linked, stripped
```

## Analysis Summary

The initial failure came from TCMalloc's `MmapAligned()` path. A conditional
GDB breakpoint on high-address `mmap()` calls showed attempts to map 1 GiB
regions with hints such as:

```text
x0 = 0x4ed800000000
x1 = 0x40000000
x3 = 0x100022
```

The relevant code lives in the `google_malloc` section. The allocator was
using a 3-bit tag in virtual address bits 42-44, which is valid for a 48-bit
address-space layout but invalid for VA39.

For VA39, the 3-bit tag must move down to bits 36-38. The randomized hint mask
also has to be constrained to the low 36 bits, otherwise generated pointers can
still escape the 39-bit range.

The first patch fixed the address-placement hints, but execution then failed
with:

```text
CHECK in ReportCorruptedFree: Attempted to free corrupted pointer ...
```

That indicated the allocation path and free/release path disagreed about where
the tag bits lived. The remaining free/release tag extraction and fast-path tag
masks were then patched to the same VA39 layout.

## Patch Details

The core transformation is:

- Move tag generation from `tag << 42` to `tag << 36`.
- Move tag extraction from `ubfx ..., #42, #3` to `ubfx ..., #36, #3`.
- Replace the 48-bit hint mask `0x000063ffffffffff` with `0x0000000fffffffff`.
- Replace tag masks for bits 42-44 with masks for bits 36-38.
- Replace tag-4 checks from `0x100000000000` to `0x4000000000`.

Important fixed offsets include:

```text
0x4A950B4  ubfx x8, x9, #42, #3    -> ubfx x8, x9, #36, #3
0x4A950E0  lsl  x28, x19, #42      -> lsl  x28, x19, #36
0x4A9511C  48-bit random hint mask  -> 36-bit random hint mask
0x4A951F4  48-bit random hint mask  -> 36-bit random hint mask
0x4A95320  48-bit random hint mask  -> 36-bit random hint mask
0x4A953A8  ubfx x0, x20, #42, #3   -> ubfx x0, x20, #36, #3
0x4A95500  ubfx x8, x8, #42, #3    -> ubfx x8, x8, #36, #3
0x4A9550C  lsl  x28, x19, #42      -> lsl  x28, x19, #36
```

Free/release tag extraction was also patched at:

```text
0x4A52150
0x4A54C90
0x4A55060
0x4A553C0
0x4A55810
0x4A55C60
0x4A56010
0x4A563E0
0x4A5E290
0x4A659B0
0x4A6D0D0
0x4AC1F84
```

Additional exact opcode replacements are applied across the `google_malloc`
section for fast-path masks and tag-4 checks:

```text
and x12, x19, #0x1c0000000000 -> and x12, x19, #0x7000000000
and x10, x19, #0x1c0000000000 -> and x10, x19, #0x7000000000
mov x13, #0x180000000000      -> mov x13, #0x6000000000
mov x12, #0x180000000000      -> mov x12, #0x6000000000
mov x10, #0x180000000000      -> mov x10, #0x6000000000
tst x0,  #0x180000000000      -> tst x0,  #0x6000000000
tst x2,  #0x180000000000      -> tst x2,  #0x6000000000
tag-4 check sequence          -> VA39 tag-4 check sequence
```

Patch counts from `patch_agy_va39.py`:

```text
and x12 tag mask: 8
and x10 tag mask: 8
mov x13 tag value: 10
mov x12 tag value: 8
mov x10 tag value: 9
tst x0 tag bits: 4
tst x2 tag bits: 6
tag4 mask/value sequence: 23
```

## Reapplying the Patch

To regenerate the patched binary from the original:

```bash
cp agy.orig agy
python3 patch_agy_va39.py
```

The patcher validates exact original bytes before modifying each fixed offset.
If a fixed byte sequence does not match, it exits with a mismatch error instead
of silently patching the wrong binary.

## Verification

The patched binary no longer fails with the TCMalloc VA48 message.

The intermediate corrupted-free failure was also fixed. After applying the full
patch, running with a writable temporary home directory reached normal CLI
initialization:

```bash
mkdir -p /tmp/agy-home
HOME=/tmp/agy-home ./agy
```

In this sandbox, the command exits because network socket creation is blocked,
not because of TCMalloc:

```text
Starting language server process with pid 2
Language server will attempt to listen on host localhost
CLI failed - listen tcp 127.0.0.1:0: socket: operation not permitted
```

That confirms the allocator initialization and early CLI startup have progressed
past the original VA48 failure.

The reproducibility check was:

```bash
mkdir -p /tmp/agy-va39-test
cp ./agy.orig /tmp/agy-va39-test/agy
cp ./patch_agy_va39.py /tmp/agy-va39-test/patch_agy_va39.py
(cd /tmp/agy-va39-test && python3 patch_agy_va39.py)
cmp -s /tmp/agy-va39-test/agy ./agy
```

The `cmp` check succeeded.

## Notes

This is a binary patch against this exact stripped `agy` build. It should not
be assumed to apply to another build unless the original bytes match.

The current directory's `.git` entry is not a normal usable Git repository in
this environment, so the work was documented with files rather than a commit.
