#!/usr/bin/env python3
"""Live Doom on the Qwenputer reference machine, with a watchable frame.

Same shakeout runner as port/run_ref.py, plus: every completed frame is
written to latest.png next to this script (stdlib PNG encoder, no deps),
where a static file server + index.html turn it into a live view.
"""
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from chipformer.rv import spec as S  # noqa: E402

S.RAM_WORDS = 1 << 19
S.DROM_WORDS = 3 << 19
S.DROM_BASE = 0x200000
S.ROM_BASE = 0x800000
S.SP_INIT = S.RAM_BASE + 4 * S.RAM_WORDS

from chipformer.rv import elf  # noqa: E402
from chipformer.rv.ref import Machine  # noqa: E402

ELF = HERE / "doom-big.elf"
WAD = HERE / "doom1.wad"

nm = subprocess.run(["/usr/bin/nm", "-g", str(ELF)], capture_output=True, text=True).stdout
# nm may not exist / ELF symbols are local; fall back to the known addresses
# from the VM build (same ELF, byte-identical).
FB, FC = 0xCA3A8, 0xD9DB8
for line in nm.splitlines():
    parts = line.split()
    if len(parts) == 3 and parts[2] == "qwen_screen":
        FB = int(parts[0], 16)
    if len(parts) == 3 and parts[2] == "qwen_frame_count":
        FC = int(parts[0], 16)

wad = WAD.read_bytes()
n_lumps, dir_off = struct.unpack_from("<II", wad, 4)
pal = None
for i in range(n_lumps):
    off, size, name = struct.unpack_from("<II8s", wad, dir_off + 16 * i)
    if name.rstrip(b"\0") == b"PLAYPAL":
        pal = wad[off:off + 768]
        break
assert pal


def write_png(path, w, h, rgb):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 6))
           + chunk(b"IEND", b""))
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(png)
    tmp.replace(path)


def main():
    prog = elf.program(str(ELF))
    m = Machine.from_program(prog)
    print("live: running, frames -> latest.png", flush=True)
    target_frames = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    max_steps = int(sys.argv[2]) if len(sys.argv) > 2 else 400_000_000
    resx = int(sys.argv[3]) if len(sys.argv) > 3 else 320
    resy = int(sys.argv[4]) if len(sys.argv) > 4 else 200
    last_fc = -1
    t0 = time.time()
    while not m.halted:
        m.run(200_000)
        fc = m.ram[FC >> 2]
        if fc != last_fc:
            last_fc = fc
            rgb = bytearray()
            for i in range(resx * resy):
                w32 = m.ram[(FB + i) >> 2]
                idx = (w32 >> (8 * ((FB + i) & 3))) & 0xFF
                rgb += pal[3 * idx:3 * idx + 3]
            write_png(HERE / "latest.png", resx, resy, bytes(rgb))
            print(f"[{time.time() - t0:6.1f}s] steps={m.steps:,} frames={fc}", flush=True)
        if fc >= target_frames or m.steps >= max_steps:
            break
    print(f"done: halted={m.halted} fault={m.fault} steps={m.steps:,} "
          f"frames={m.ram[FC >> 2]}", flush=True)


if __name__ == "__main__":
    main()
