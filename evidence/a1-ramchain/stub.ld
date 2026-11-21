ENTRY(_start)
SECTIONS
{
  . = 0x43000000;
  .text : {
    *(.text.start)
    *(.text*)
    *(.rodata*)
  }
  /DISCARD/ : {
    *(.ARM.exidx*)
    *(.ARM.extab*)
    *(.ARM.attributes)
    *(.comment)
    *(.note*)
    *(.eh_frame*)
  }
}
