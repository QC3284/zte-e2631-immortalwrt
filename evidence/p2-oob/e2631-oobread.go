// e2631-oobread: read raw OOB bytes of an MTD NAND partition, read-only.
// Usage: e2631-oobread <mtd-device> <page-count> <out-file> [normal|raw]
// "raw" sets the per-fd MTDFILEMODE to MTD_FILE_MODE_RAW before reading the
// OOB, which disables the on-die ECC engine for this descriptor (no flash write).
package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"syscall"
	"unsafe"
)

const (
	memReadOOB64 = 0xC0184D16 // _IOWR('M', 22, struct mtd_oob_buf64)
	memReadOOB   = 0xC00C4D04 // _IOWR('M',  4, struct mtd_oob_buf)
	mtdFileMode  = 0x4D13     // _IO('M', 19)
	fileModeRaw  = 3          // MTD_FILE_MODE_RAW
)

type mtdOobBuf64 struct {
	start  uint64
	pad    uint32
	length uint32
	usrPtr uint64
}

type mtdOobBuf struct {
	start  uint32
	length uint32
	ptr    uintptr
}

func readFile(p string) string {
	b, err := os.ReadFile(p)
	if err != nil {
		return "?"
	}
	return strings.TrimSpace(string(b))
}

func main() {
	if len(os.Args) < 4 {
		fmt.Fprintf(os.Stderr, "usage: %s <mtd-device> <page-count> <out-file> [normal|raw]\n", os.Args[0])
		os.Exit(2)
	}
	dev := os.Args[1]
	pages, err := strconv.Atoi(os.Args[2])
	if err != nil || pages <= 0 {
		fmt.Fprintln(os.Stderr, "bad page count")
		os.Exit(2)
	}
	out := os.Args[3]
	modeReq := "normal"
	if len(os.Args) >= 5 {
		modeReq = os.Args[4]
	}
	base := dev
	if i := strings.LastIndex(dev, "/"); i >= 0 {
		base = dev[i+1:]
	}
	sys := "/sys/class/mtd/" + base
	writesize, _ := strconv.Atoi(readFile(sys + "/writesize"))
	oobsize, _ := strconv.Atoi(readFile(sys + "/oobsize"))
	if writesize <= 0 {
		writesize = 2048
	}
	if oobsize <= 0 {
		oobsize = 64
	}
	f, err := os.OpenFile(dev, os.O_RDONLY, 0)
	if err != nil {
		fmt.Fprintln(os.Stderr, "open:", err)
		os.Exit(1)
	}
	defer f.Close()
	if modeReq == "raw" {
		_, _, errno := syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), uintptr(mtdFileMode), uintptr(fileModeRaw))
		if errno != 0 {
			fmt.Fprintf(os.Stderr, "MTDFILEMODE raw failed: %v (errno %d)\n", errno, int(errno))
			os.Exit(1)
		}
		fmt.Fprintln(os.Stderr, "MTDFILEMODE set to MTD_FILE_MODE_RAW (ECC engine disabled for this fd)")
	}
	buf := make([]byte, oobsize)
	all := make([]byte, 0, pages*oobsize)
	readMode := "none"
	for p := 0; p < pages; p++ {
		var errno syscall.Errno
		if readMode == "none" || readMode == "64" {
			req := mtdOobBuf64{start: uint64(p * writesize), length: uint32(oobsize), usrPtr: uint64(uintptr(unsafe.Pointer(&buf[0])))}
			_, _, errno = syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), uintptr(memReadOOB64), uintptr(unsafe.Pointer(&req)))
			if errno == 0 {
				readMode = "64"
			}
		}
		if errno != 0 || readMode == "legacy" {
			req2 := mtdOobBuf{start: uint32(p * writesize), length: uint32(oobsize), ptr: uintptr(unsafe.Pointer(&buf[0]))}
			_, _, errno = syscall.Syscall(syscall.SYS_IOCTL, f.Fd(), uintptr(memReadOOB), uintptr(unsafe.Pointer(&req2)))
			if errno == 0 {
				readMode = "legacy"
			}
		}
		if errno != 0 {
			fmt.Fprintf(os.Stderr, "ioctl page %d failed: %v (errno %d)\n", p, errno, int(errno))
			os.Exit(1)
		}
		all = append(all, buf...)
	}
	if err := os.WriteFile(out, all, 0o644); err != nil {
		fmt.Fprintln(os.Stderr, "write:", err)
		os.Exit(1)
	}
	fmt.Fprintf(os.Stderr, "fileMode=%s ioctl=%s wrote %d bytes (%d pages x %d B OOB) to %s\n", modeReq, readMode, len(all), pages, oobsize, out)
}
