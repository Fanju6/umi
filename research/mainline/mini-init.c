/* SPDX-License-Identifier: MIT */
/*
 * Xiaomi umi / Linux 6.12 first-boot visibility stub.
 *
 * PID 1 in a tiny, entirely RAM-backed initramfs. Nothing is mounted
 * read/write except volatile proc/sys/devtmpfs; NO userdata or storage,
 * no Android init, no network, no device flashing, no automatic reboot.
 *
 * The repeated marker is designed for console/ramoops collection after
 * a developer manually returns to a separate TWRP recovery.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>

#define MARKER "UMI612-MINIMAL-INIT"

static void log_message(const char *message) {
    int fd = open("/dev/kmsg", O_WRONLY | O_CLOEXEC);
    if (fd >= 0) {
        (void)write(fd, "<6>" MARKER ": ", sizeof("<6>" MARKER ": ") - 1);
        (void)write(fd, message, strlen(message));
        (void)write(fd, "\n", 1);
        (void)close(fd);
    }
    fd = open("/dev/console", O_WRONLY | O_CLOEXEC | O_NOCTTY);
    if (fd >= 0) {
        (void)write(fd, MARKER ": ", sizeof(MARKER ": ") - 1);
        (void)write(fd, message, strlen(message));
        (void)write(fd, "\n", 1);
        (void)close(fd);
    }
}

int main(void) {
    (void)mkdir("/dev", 0755);
    (void)mkdir("/proc", 0555);
    (void)mkdir("/sys", 0555);

    (void)mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID, "");
    (void)mount("proc", "/proc", "proc", MS_NOSUID | MS_NOEXEC | MS_NODEV, "");
    (void)mount("sysfs", "/sys", "sysfs", MS_NOSUID | MS_NOEXEC | MS_NODEV, "");

    log_message("PID1 reached; storage remains untouched");
    for (;;) {
        log_message("heartbeat; kernel reached userspace");
        sleep(15);
    }
    return 0;
}
