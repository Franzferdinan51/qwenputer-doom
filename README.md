# Doom on Qwenputer

Doom (doomgeneric) ported to the **Qwenputer** — the RV32IM+Zba CPU compiled
into the weights of a Qwen3.5-4B model
([divagr1925/Qwen3.5-4B-Qwenputer](https://huggingface.co/divagr1925/Qwen3.5-4B-Qwenputer)).

The target is the CPU *inside the model*: every instruction executed by the
transformer circuit, no host CPU emulating the guest, no bootstrapped
hardware. This repo holds the game port, the machine sizing, and the
verification harness.

## Status

**Proven (2026-10-31):** the port boots and plays on the project's reference
machine (`ref.py`) — the executable spec the in-weights circuit is verified
against instruction-for-instruction. 60M instructions, zero faults: title
screen, menu navigation via scripted input, E1M1 loaded and rendering.

![Title screen rendered by the guest CPU](docs/title.png)
![E1M1 rendered by the guest CPU](docs/e1m1.png)

**Next:** the in-weights circuit run on Executor2 (Triton). The game fits the
circuit's constraints with room to spare on code; the memory map has to grow
(see below). Two ways to grow it are on the table — recompiling the circuit
with a Doom-sized map, or keeping the stock verified circuit and letting the
host executor act purely as a memory controller (banked DROM/RAM). Either
way, all computation stays in the weights.

## The machine Doom needs (measured, not guessed)

| Region | Stock circuit | This port | Notes |
|---|---|---|---|
| ROM (code) | 256 KB @ 0x40000 | **228 KB** @ 0x800000 | fits the circuit's hard 256 KB cap — the trace format's anchors are 16-bit |
| RAM | 32 KB | **2 MB** @ 0x0 | 320×200 framebuffer (64 KB) + 512 KB zone cache + engine statics |
| DROM (read-only data) | 128 KB | **6 MB** @ 0x200000 | engine tables (105 KB) + the WAD |

On the stock map the link overflows RAM by 860 KB — the framebuffer alone is
twice the stock RAM. The growth is in the *map*, not the CPU: RV32IM+Zba,
`ecall` putchar/exit, and the CSR stubs are all stock.

## Layout

- `port/` — the port sources:
  - `doomgeneric_qwenputer.c` — platform layer: static framebuffer, a frame
    clock (one rendered frame = one 35 Hz tic), scripted input keyed by
    frame number
  - `w_file_qwenputer.c` — WAD file class reading lumps zero-copy from DROM
  - `stubs.c` — filesystem stubs (opens fake-succeed: the WAD lives in DROM,
    config/savegames are skipped by design)
  - `src/i_system.c` — overlay with a static 512 KB zone (no heap growth)
  - `qwenputer-big.ld` — the grown memory map above
  - `env/` — crt0/syscalls/linker scripts vendored from the Qwenputer fork's
    rv env, so this repo builds standalone
  - `build.sh` — `build.sh [big|stock]` (stock fails the link, on purpose:
    it's the size proof)
  - `run_ref.py` — reference-machine shakeout: runs `doom-big.elf`, dumps
    rendered frames as PPM from guest RAM
- `docs/` — frames captured from the reference-machine run
- `doomgeneric/` — upstream doomgeneric (fetched by `get-doomgeneric.sh`,
  GPL-2.0, © id Software / Chocolate Doom contributors)

## Build & shakeout

```sh
sudo apt install gcc-riscv64-unknown-elf picolibc-riscv64-unknown-elf
./get-doomgeneric.sh
# Supply your own shareware DOOM1.WAD v1.9 (4,196,020 bytes,
# MD5 f0cefca49926d00903cf57551d901abe) as build/doom1.wad —
# e.g. Debian's doom-wad-shareware package ships exactly that file.
./port/build.sh big
python3 port/run_ref.py 130 60000000   # needs the qwenputer fork's rv package on the path
```

## Credits

- Qwenputer: divagr1925 — the CPU-in-weights design this builds on
- doomgeneric: ozkl; Doom © id Software
- Port: Duckets + Juno 🦆
