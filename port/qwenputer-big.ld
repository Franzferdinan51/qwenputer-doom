/* Grown Qwenputer map for Doom (design target; the circuit recompile that
   makes these sizes real in the weights is the route-1 work item -- the
   bases move vs the stock map, which core.py/ref.py must follow):
     RAM  0x000000  2 MB   data / bss / heap / stack (framebuffer + zone live here)
     DROM 0x200000  6 MB   read-only data: engine tables + the WAD (4.0 MB shareware)
     ROM  0x800000  256 KB code (the stock trace format's hard cap: 16-bit anchors)
   crt0 expects the host/snapshot to set sp to the top of RAM (0x200000). */
ENTRY(_start)
MEMORY
{
  RAM (rw) : ORIGIN = 0x100, LENGTH = 0x1FFF00
  DROM (r) : ORIGIN = 0x200000, LENGTH = 6M
  ROM (rx) : ORIGIN = 0x800000, LENGTH = 256K
}
SECTIONS
{
  .text : { *(.text.init) *(.text .text.*) } > ROM
  .rodata : {
    *(.rodata .rodata.* .srodata .srodata.*)
    *(.init_array .init_array.* .fini_array .fini_array.* .eh_frame .eh_frame_hdr)
  } > DROM
  .data : { *(.data .data.* .sdata .sdata.*) } > RAM
  .tdata : { __tls_base = .; *(.tdata .tdata.*) } > RAM
  .tbss : { *(.tbss .tbss.*) } > RAM
  .bss : {
    . = . + SIZEOF(.tbss);
    *(.bss .bss.* .sbss .sbss.*) *(COMMON)
    . = ALIGN(16);
    __heap_start = .;
  } > RAM
  __heap_end = 0x1F0000;  /* 64 KB of stack above the heap */
  _end = __heap_start;
}
