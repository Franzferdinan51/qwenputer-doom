#!/usr/bin/env python3
"""Shakeout runner: Doom on the fork's reference machine (ref.py Machine).

This is the repo's standard first check for any program -- the exact
semantics the in-weights circuit is verified against. It is NOT the
in-weights run; it proves the port itself works before the circuit work.

The grown memory map is applied by patching spec constants before the
machine is built (spec.py is parameterized; SP_INIT is derived, so it is
patched too):
  RAM  0x000000  2 MB | DROM 0x200000  6 MB | ROM 0x800000  256 KB
"""
import struct
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORK = Path.home() / "workspace/qwenputer-linux/experimental/riscv"
sys.path.insert(0, str(FORK))

from chipformer.rv import spec as S  # noqa: E402

S.RAM_WORDS = 1 << 19            # 2 MB of words... (words are 4 B: 524288 words)
S.DROM_WORDS = 3 << 19           # 6 MB
S.DROM_BASE = 0x200000
S.ROM_BASE = 0x800000
S.SP_INIT = S.RAM_BASE + 4 * S.RAM_WORDS

from chipformer.rv import elf  # noqa: E402
from chipformer.rv.ref import Machine  # noqa: E402

ELF = ROOT / "build/doom-big.elf"
WAD = ROOT / "build/doom1.wad"
FRAMES = ROOT / "build/frames"
FRAMES.mkdir(exist_ok=True)

# symbol addresses from the ELF
nm = subprocess.run(["riscv64-unknown-elf-nm", str(ELF)],
                    capture_output=True, text=True).stdout
sym = {}
for line in nm.splitlines():
    parts = line.split()
    if len(parts) == 3:
        sym[parts[2]] = int(parts[0], 16)
FB = sym["qwen_screen"]
FC = sym["qwen_frame_count"]
print(f"framebuffer @ {FB:#x}, frame_count @ {FC:#x}", flush=True)

# PLAYPAL first palette from the WAD, for frame dumps
wad = WAD.read_bytes()
n_lumps, dir_off = struct.unpack_from("<II", wad, 4)
pal = None
for i in range(n_lumps):
    off, size, name = struct.unpack_from("<II8s", wad, dir_off + 16 * i)
    if name.rstrip(b"\0") == b"PLAYPAL":
        pal = wad[off:off + 768]
        break
assert pal, "PLAYPAL not found"


def ram_byte(m, addr):
    w = m.ram[addr >> 2]
    return (w >> (8 * (addr & 3))) & 0xFF


def dump_frame(m, tag):
    px = bytes(ram_byte(m, FB + i) for i in range(320 * 200))
    with open(FRAMES / f"frame-{tag}.ppm", "wb") as f:
        f.write(b"P6\n320 200\n255\n")
        rgb = bytearray()
        for idx in px:
            rgb += pal[3 * idx:3 * idx + 3]
        f.write(rgb)
    print(f"  dumped frame {tag}", flush=True)


def main():
    prog = elf.program(str(ELF))
    m = Machine.from_program(prog)
    print(f"loaded: entry {prog.entry:#x}; running...", flush=True)
    target_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 130
    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 60_000_000
    dumped = set()
    t0 = time.time()
    last_out = 0
    while not m.halted:
        m.run(200_000)  # records (~instructions); tokens discarded
        fc = m.ram[FC >> 2]
        if len(m.out) > last_out:
            sys.stdout.write(m.out[last_out:].decode("ascii", "replace"))
            sys.stdout.flush()
            last_out = len(m.out)
        el = time.time() - t0
        print(f"[{el:6.1f}s] steps={m.steps:,} frames={fc} pc={m.pc:#x}", flush=True)
        if fc and fc % 10 == 0 and fc not in dumped:
            dump_frame(m, f"{fc:04d}")
            dumped.add(fc)
        if fc >= target_frames or m.steps >= max_steps:
            break
    print(f"halted={m.halted} fault={m.fault} exit={m.exit_code} "
          f"steps={m.steps:,} frames={m.ram[FC >> 2]}", flush=True)
    if m.ram[FC >> 2]:
        dump_frame(m, "final")
    print("console output:\n" + m.out.decode("ascii", "replace"), flush=True)


if __name__ == "__main__":
    main()
