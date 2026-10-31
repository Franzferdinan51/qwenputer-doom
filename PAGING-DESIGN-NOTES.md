# Route 2 (host = memory controller) — design recon notes

Started 2026-10-31 while the Batman Executor2 feasibility check runs.
Route picked by Juno at Duckets' delegation: stock verified circuit,
host pages memory; all computation stays in the weights.

## What the executor actually is (from the fork clone)

- `chipformer/rv/tritonexec.py` — Executor2 (305 lines): the circuit's step
  as fused Triton kernels, one per sublayer, **under one CUDA graph**.
  Weights kept as sparse CSR rows. `Executor2(c, batch).step(x)` advances
  the whole circuit one token, in place. Same semantics as
  `fastexec.Executor` (the IR's arithmetic in fp32, exact).
- `chipformer/rv/chat.py` — RvChat driver: the firmware ELF is "a state
  snapshot written into the chip"; on start, `self.ex.load_init()` sets each
  head's state to its init (snapshot injected via hf.inject). So ROM/DROM/
  RAM-init live in per-head state tensors, loaded once at start.
- The host drives the circuit token by token (records from the trace
  format) and reads predicted tokens back — loads/stores complete INSIDE
  a step; the host never sees an address. There is no MMIO trap for data.

## The hard problem, stated precisely

- The stock circuit's address decoding is compiled in: RAM 32 KB, DROM
  128 KB, ROM 256 KB at fixed bases. A guest EA outside those regions
  faults; the high address bits are simply not decoded by the RAM heads
  (n_ram_heads = RAM_WORDS >> 8).
- Therefore "paging" cannot be transparent to the guest. The guest (or a
  shim under it) must cooperate: big memory reached through a window +
  bank selection, Game-Boy-MBC style — OR the circuit must grow (route 1).
- Precedent to investigate: spec.py's TEXT region (TEXT_ADDR/TEXT_ROW/
  TEXT_ROWS, Machine.text / text_word()) — a host-maintained region the
  machine reads specially. If the circuit side (core.py) merges a
  host-provided region at read time, a live host window may be
  mechanistically possible; if TEXT is baked into the snapshot only,
  it is not.

## Findings 2026-10-31 (second pass) — ROUTE CORRECTED

Reading ref.py's record() and core.py killed pure route 2:

- **Stores are invisible to the host.** An SW record is ONE token
  (`ST{w4}`, w4 = a single bit of the word index). Addr/value live in the
  circuit's residual state, never in the token stream. The stream is a
  commitment format, not a bus trace — the host can neither snoop stores
  nor service loads. Loads resolve ram -> drom -> text entirely inside.
- **The only host data-input channel is the P3 bridge** (bridge.py): text
  captured between <tool_call> tags into the TEXT buffer, machine parked/
  resumed around it. That is a chat/tool harness feature. firmware.py
  runs are snapshot + decoding (or Executor2 token driving); putchar is
  the only output, there is no general mid-run host memory channel.
- **RAM cannot be host-served at all**: random-access pointers everywhere
  in a C engine; even the digit-file ops wrap `ea mod 32 KB`. And the
  framebuffer alone (64 KB) is 2x the stock RAM.

**Corrected plan (Juno's call, supersedes the route-2 pick): recompile
the chip layers with the grown memory map** — RAM 2 MB, DROM 6 MB, ROM
stays 256 KB at its stock base if the compiler allows (else the port's
0x800000). This is the same operation that created the Qwenputer itself
(11 compiler-computed layers prepended to an untouched Qwen): the ISA,
the trace format, the CPU core logic and the proven Doom binary do not
change; only the memory geometry in the compiled layers grows.
Bridge-served DROM remains a fallback for DROM only if DROM growth
specifically fails; it cannot substitute for RAM.

Open: does compile.py parameterize RAM_WORDS/DROM_WORDS cleanly (spec.py
constants feed core.py geometry — T4B target, n_ram_heads = RAM_WORDS>>8),
and what does a 64x RAM do to circuit size / Executor2 VRAM on 16 GB?

## Findings 2026-10-31 (third pass) — what the recompile actually involves

- core.py:375 hard-asserts the stock ROM geometry (ROM_BASE == 1<<18,
  ROM_WORDS == 1<<16). ~~ROM stays stock; third linker map with ROM @
  0x40000.~~ **DISPROVEN 2026-10-31 by the linker itself**: a circuit.ld
  with RAM 2 MB @ 0 + ROM @ 0x40000 fails — .text [0x40000,0x790FF]
  overlaps .bss [0xEBB8,0xD9DDF]. The stock bases only work at stock
  sizes; a grown RAM swallows the stock DROM/ROM bases. CONSEQUENCE:
  the circuit keeps the PROVEN big map (RAM 2 MB @ 0, DROM 6 MB @
  0x200000, ROM 256 KB @ 0x800000) and the core.py rework includes
  re-basing ROM: the hard assert, the EA[18] bad-jump check (~core.py:986)
  and the region-decode bit fields move to the new geometry. The anchor
  payloads are ROM-base-relative word indices, so the trace FORMAT
  survives unchanged. doom-big.elf is already the exact circuit binary —
  no third map, no relink.
- RAM/DROM geometry is spec-parameterized in shape (n_ram_heads =
  RAM_WORDS >> 8 at core.py:827; DROM loops over DROM_WORDS >> 11 at :861;
  snapshot at :1238-1262 sizes rom/drom/ram from spec) — BUT the load/store
  path decodes regions from fixed EA bit fields (head literals built from
  EA[2:6] and EA[14:...] slices). Stock layout: RAM 15 bits, DROM bit 17,
  ROM bit 18. A 2 MB RAM (21 bits) + DROM at bit 21 collides with those
  fixed decode bits. The real work is a bounded redesign of the EA
  bit-field layout in core.py (+ matching spec.py constants and ref.py
  region checks), NOT a whole new compiler.
- Verification net exists in-repo: execcheck.py (circuit vs ref
  equivalence), riscv-tests via the normal program suite, and the ref
  shakeout frames as the end-to-end oracle (frame 10 title PNG md5
  25058fbf6fe4e79348621bdf634cbe20 — deterministic across engines).
- FPS side-quest (for the ref-machine live view only): Rv32 (untraced,
  flat dict memory) vs Machine (traced) benchmark running on the Mac;
  dict-per-byte loads may not beat the traced word-list RAM — measure,
  don't assume. Resolution drop is the other multiplier (compile-time
  DOOMGENERIC_RESX/RESY in build.sh).

## Open questions for the next work block

1. core.py: how are RAM reads/writes and TEXT reads implemented in the
   circuit IR? Which parts are snapshot-baked vs live state tensors?
2. Executor2's state tensors: are RAM rows separately addressable from
   Python between CUDA-graph replays (load_init implies some write path
   exists)? If yes, a bank-swap between steps is possible IF the guest
   signals bank changes observably (e.g. a store to a magic address
   appears as a token the host can watch for — check the trace format
   for store records carrying EAs).
3. What does a store record look like in the token stream — does the
   host see (addr, value) for every store? (ref.Machine.record commits
   state per record; the circuit predicts the same records, so the host
   driving token-by-token may be able to OBSERVE stores even though it
   cannot intercept loads.)
4. If loads can't be serviced live, the fallback shape: guest-side
   banking library — Doom port variant that keeps hot data (framebuffer,
   zone) in the native 32 KB... doesn't fit (framebuffer alone is 64 KB).
   Alternative fallback: windowed DROM only (WAD reads are sequential-ish
   and lump-granular — the port already funnels ALL WAD access through
   QW_Read; a banked DROM window is a small, contained change), plus
   route-1 growth ONLY for RAM (32 KB -> 2 MB is the smaller compile).

## Concrete change list for the recompile (from reading core.py L7-L9)

Geometry as compiled today:
- RAM (core.py ~L820): wi = EA[14:2]; key head = (EA[14], EA[5:2]),
  value head EA[6], row EA[13:7] (128 rows). n_ram_heads = RAM_WORDS>>8
  = 32. The head-literal formula already generalizes in shape:
  hl = lits_of(EA[2:6], h&15) + lits_of(EA[14:14+bitlen-1], h>>4) — for
  2048 heads it consumes EA[14:21]. BUT the EA vector itself is built
  capped at bit 14 (`EA = [r[i] + eab[i] if i < 15 else r[i] ...]`) —
  must extend to bit 22.
- DROM (~L855): wi = EA[16:2] at base 0x20000; heads = DROM_WORDS>>11
  = 16, hl = EA[13:17]; rows EA[6:12], value head EA[12], half EA[5],
  word EA[2:5]. Hand-laid slices — for 6 MB (768 heads, wi = EA[22:2]
  over base 0x200000) these slices must be re-laid consistently.
- TEXT select: tsel = EA[15] + ~EA[11:15] — collides with a 2 MB RAM's
  address bits; the load-value region mux (to locate: after the RAM/
  DROM/TEXT sections) keys on region bits and must be redesigned with
  the new layout.
- Region decode LOCATED (core.py ~:909, pass 4): in_ram =
  AND(~EA[15:32]) i.e. EA < 0x8000; in_drom = AND(~EA[18:32], EA[17])
  i.e. [0x20000, 0x40000); in_text from tsel + ~EA[16:32]. Grown map:
  in_ram = AND(~EA[21:32]); in_drom = two AND terms ORed —
  [0x200000, 0x400000) (EA[21], ~EA[22], ~EA[23:32]) plus
  [0x400000, 0x800000) (EA[22], ~EA[23:32]) — 6 MB is not a power of
  two, so no single conjunction works; the DSL's t_and sums (see
  oor_ld ~:980) cover this. TEXT_ADDR 0x8000 sits inside the grown
  RAM: the P3 text buffer must be dropped for the Doom firmware
  build (text=False) or relocated above ROM.
- Worktree ready: ~/workspace/qwenputer-circuit (branch
  circuit-grown-map at upstream HEAD f07a0b2, clean) — the main
  clone's uncommitted Linux work is untouched by circuit edits.
- Fetch/anchor: ROM_BASE assert (core.py:375), EA[18] bad-jump check
  (~:986) -> EA[23] for ROM @ 0x800000.
- spec.py: RAM_WORDS 8192 -> 524288, DROM_WORDS 32768 -> 1572864,
  DROM_BASE -> 0x200000, ROM_BASE -> 0x800000 (SP_INIT derives).
- ref.py needs nothing (arithmetic region checks; proven by shakeout).
  Digit-op ram_byte wraps mod 32 KB by design; Doom never uses them.
- Cost driver to measure at compile time: RAM tables 32 -> 2048, DROM
  tables 16 -> 768. Chip nonzero count (stock ~1M) will grow roughly
  with table count in those sections; measure nnz from the IR before
  any HF export, and Executor2 step cost scales with it.
- Verification: execcheck.py circuit-vs-ref on test programs RELINKED
  to the new map (stock test ELFs are stock-map), then Doom frame 10
  vs the md5 oracle 25058fbf6fe4e79348621bdf634cbe20.

## Numbers to design against

- Doom port: code 228 KB (fits ROM cap), RAM ~0.9-2 MB, DROM 4.3 MB.
- Executor2 on L4: ~3,699 instr/s per upstream. Doom: ~0.5-1.3M instr
  per rendered frame on the ref machine -> minutes per frame regardless
  of route. The artifact is correctness/purity, not speed.
