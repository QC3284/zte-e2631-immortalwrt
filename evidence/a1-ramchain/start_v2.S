.syntax unified
.arm
.section .text.start,"ax"
.global _start
_start:
    mov r4, sp          @ save vendor stack pointer (r4 is callee-saved)
    mov r5, lr          @ save vendor return address (r5 is callee-saved)
    ldr sp, =0x48000000
    bl stub_main        @ returns after restoring the UART config
    mov sp, r4
    mov lr, r5
    bx lr
1:  b 1b
