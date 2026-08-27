#!/usr/bin/env python3
"""Patch OrangeFox/TWRP minuitwrp for non-blocking Red Magic haptics.

The known-good recovery enables a Xiaomi AIDL vibrator instance. On tiro the
synchronous service lookup can block the GUI thread for about five seconds on
every tap. This patch:

1. Changes AIDL lookup from AServiceManager_getService() to the non-blocking
   AServiceManager_checkService() as a safety net.
2. Uses the native Nubia/Awinic continuous-mode sysfs node first. This path does
   not depend on haptic_ram.bin and therefore remains deterministic in recovery.
3. Keeps direct Linux input force-feedback as a secondary backend, with a
   persistent effect slot rather than delete/recreate on every tap.
4. Falls back to the existing generic sysfs paths last.

The device BoardConfig intentionally does not enable AIDL haptics. On tiro the
normal runtime order is Awinic continuous mode -> input FF -> generic sysfs.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

MARKER = "TIRO_INPUT_FF_HAPTICS"

HELPERS = r'''

#include <signal.h>
#include <time.h>

/* TIRO_INPUT_FF_HAPTICS / TIRO_AWINIC_CONT_HAPTICS
 *
 * The native Nubia haptic_hv driver exposes /sys/class/timed_output/vibrator/cont.
 * Its continuous mode does not require haptic_ram.bin, unlike RAM/FF_CONSTANT
 * playback in the AW8692x input framework. Recovery uses this path first and a
 * POSIX timer to stop the effect without sleeping on the GUI thread.
 *
 * Input force-feedback remains a secondary backend for kernels that do not
 * expose the Nubia sysfs node. Its single FF slot is kept and updated instead
 * of being erased/recreated on every UI event.
 */
#define TIRO_AWINIC_CONT_FILE "/sys/class/timed_output/vibrator/cont"

static timer_t tiro_cont_timer = {};
static bool tiro_cont_timer_ready = false;
static bool tiro_cont_logged = false;

static bool tiro_write_haptic_node(const char* path, const char* value) {
    int fd = open(path, O_WRONLY | O_CLOEXEC);
    if (fd < 0) return false;
    const size_t len = strlen(value);
    const ssize_t wrote = write(fd, value, len);
    close(fd);
    return wrote == static_cast<ssize_t>(len);
}

static void tiro_stop_awinic_cont(union sigval) {
    (void)tiro_write_haptic_node(TIRO_AWINIC_CONT_FILE, "0");
}

static bool tiro_init_cont_timer() {
    if (tiro_cont_timer_ready) return true;

    struct sigevent sev = {};
    sev.sigev_notify = SIGEV_THREAD;
    sev.sigev_notify_function = tiro_stop_awinic_cont;
    sev.sigev_value.sival_ptr = nullptr;

    if (timer_create(CLOCK_MONOTONIC, &sev, &tiro_cont_timer) != 0) {
        return false;
    }
    tiro_cont_timer_ready = true;
    return true;
}

static bool tiro_vibrate_awinic_cont(int timeout_ms) {
    if (timeout_ms <= 0 || access(TIRO_AWINIC_CONT_FILE, W_OK) != 0) return false;

    const int duration_ms = timeout_ms > 1000 ? 1000 : timeout_ms;

    // Nubia cont_store() stops the previous effect before starting continuous
    // mode, so writing 1 also gives rapid repeated taps a clean retrigger.
    if (!tiro_write_haptic_node(TIRO_AWINIC_CONT_FILE, "1")) return false;

    // Android/bionic supports SIGEV_THREAD timers, but keep a small bounded
    // synchronous stop as a recovery-only safety net if timer creation fails.
    // Normal UI feedback is ~50 ms; never block the GUI for more than 60 ms.
    if (!tiro_init_cont_timer()) {
        const int sync_ms = duration_ms > 60 ? 60 : duration_ms;
        usleep(static_cast<useconds_t>(sync_ms) * 1000U);
        (void)tiro_write_haptic_node(TIRO_AWINIC_CONT_FILE, "0");
        return true;
    }

    struct itimerspec its = {};
    its.it_value.tv_sec = duration_ms / 1000;
    its.it_value.tv_nsec = static_cast<long>(duration_ms % 1000) * 1000000L;
    if (its.it_value.tv_sec == 0 && its.it_value.tv_nsec == 0) {
        its.it_value.tv_nsec = 1000000L;
    }

    if (timer_settime(tiro_cont_timer, 0, &its, nullptr) != 0) {
        (void)tiro_write_haptic_node(TIRO_AWINIC_CONT_FILE, "0");
        return false;
    }

    if (!tiro_cont_logged) {
        LOGI("TIRO: using firmware-independent Awinic continuous haptics at %s\n",
             TIRO_AWINIC_CONT_FILE);
        tiro_cont_logged = true;
    }
    return true;
}

static int tiro_ff_fd = -2;       // -2: probe/reprobe, >=0: cached device
static int tiro_ff_effect_id = -1;
static int tiro_ff_effect_type = -1;

static bool tiro_ff_test_bit(unsigned int bit, const unsigned long* bits) {
    const unsigned int bits_per_long = sizeof(unsigned long) * 8U;
    return (bits[bit / bits_per_long] >> (bit % bits_per_long)) & 1UL;
}

static bool tiro_is_haptics_name(const char* name) {
    if (name == nullptr || *name == '\0') return false;

    char lower[256] = {};
    size_t i = 0;
    for (; name[i] != '\0' && i < sizeof(lower) - 1; ++i) {
        char c = name[i];
        lower[i] = (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
    }
    lower[i] = '\0';

    return strstr(lower, "haptic") != nullptr ||
           strstr(lower, "vibra") != nullptr ||
           strstr(lower, "awinic") != nullptr ||
           strstr(lower, "aw869") != nullptr;
}

static int tiro_open_input_ff_haptics() {
    if (tiro_ff_fd >= 0) return tiro_ff_fd;
    tiro_ff_fd = -2;

    DIR* dir = opendir("/dev/input");
    if (dir == nullptr) return -1;

    struct dirent* de = nullptr;
    while ((de = readdir(dir)) != nullptr) {
        if (strncmp(de->d_name, "event", 5) != 0) continue;

        char path[PATH_MAX] = {};
        snprintf(path, sizeof(path), "/dev/input/%s", de->d_name);
        int fd = open(path, O_RDWR | O_CLOEXEC);
        if (fd < 0) continue;

        char name[256] = {};
        if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0 || !tiro_is_haptics_name(name)) {
            close(fd);
            continue;
        }

        const unsigned int bits_per_long = sizeof(unsigned long) * 8U;
        unsigned long ev_bits[(EV_MAX + bits_per_long) / bits_per_long] = {};
        if (ioctl(fd, EVIOCGBIT(0, sizeof(ev_bits)), ev_bits) < 0 ||
            !tiro_ff_test_bit(EV_FF, ev_bits)) {
            close(fd);
            continue;
        }

        unsigned long ff_bits[(FF_MAX + bits_per_long) / bits_per_long] = {};
        if (ioctl(fd, EVIOCGBIT(EV_FF, sizeof(ff_bits)), ff_bits) < 0) {
            close(fd);
            continue;
        }

        if (tiro_ff_test_bit(FF_CONSTANT, ff_bits)) {
            tiro_ff_effect_type = FF_CONSTANT;
        } else if (tiro_ff_test_bit(FF_RUMBLE, ff_bits)) {
            tiro_ff_effect_type = FF_RUMBLE;
        } else {
            close(fd);
            continue;
        }

        tiro_ff_fd = fd;
        LOGI("Using input FF haptics device '%s' at %s (effect=%s)\n",
             name, path, tiro_ff_effect_type == FF_CONSTANT ? "FF_CONSTANT" : "FF_RUMBLE");
        break;
    }

    closedir(dir);
    return tiro_ff_fd >= 0 ? tiro_ff_fd : -1;
}

static void tiro_reset_ff_backend(int fd) {
    if (tiro_ff_effect_id >= 0) {
        struct input_event stop = {};
        stop.type = EV_FF;
        stop.code = static_cast<__u16>(tiro_ff_effect_id);
        stop.value = 0;
        (void)write(fd, &stop, sizeof(stop));
        (void)ioctl(fd, EVIOCRMFF, tiro_ff_effect_id);
    }
    tiro_ff_effect_id = -1;
    tiro_ff_effect_type = -1;
    if (fd >= 0) close(fd);
    tiro_ff_fd = -2;
}

static bool tiro_vibrate_input_ff(int timeout_ms) {
    int fd = tiro_open_input_ff_haptics();
    if (fd < 0 || timeout_ms <= 0) return false;

    struct ff_effect effect = {};
    effect.type = static_cast<__u16>(tiro_ff_effect_type);
    // Reuse the driver's only FF slot when one has already been allocated.
    effect.id = static_cast<__s16>(tiro_ff_effect_id);
    effect.replay.length = static_cast<__u16>(timeout_ms > 1000 ? 1000 : timeout_ms);
    effect.replay.delay = 0;

    if (tiro_ff_effect_type == FF_CONSTANT) {
        effect.u.constant.level = 0x5fff;
        effect.u.constant.envelope.attack_length = 0;
        effect.u.constant.envelope.fade_length = 0;
    } else {
        effect.u.rumble.strong_magnitude = 0x6fff;
        effect.u.rumble.weak_magnitude = 0x3fff;
    }

    if (ioctl(fd, EVIOCSFF, &effect) < 0) {
        LOGI("Input FF haptics: EVIOCSFF failed; using fallback haptics\n");
        tiro_reset_ff_backend(fd);
        return false;
    }
    tiro_ff_effect_id = effect.id;

    struct input_event play = {};
    play.type = EV_FF;
    play.code = static_cast<__u16>(tiro_ff_effect_id);
    play.value = 1;

    if (write(fd, &play, sizeof(play)) != static_cast<ssize_t>(sizeof(play))) {
        LOGI("Input FF haptics: play failed; using fallback haptics\n");
        tiro_reset_ff_backend(fd);
        return false;
    }
    return true;
}
'''


def patch_file(path: Path) -> bool:
    text = path.read_text()
    if MARKER in text:
        print(f"Haptics patch already present: {path}")
        return False

    changed = False

    # Safety net for any future device configuration that accidentally enables AIDL.
    old_lookup = "AServiceManager_getService(kVibratorInstance.c_str())"
    new_lookup = "AServiceManager_checkService(kVibratorInstance.c_str())"
    if old_lookup in text:
        text = text.replace(old_lookup, new_lookup, 1)
        changed = True
    elif new_lookup not in text:
        print("ERROR: Could not find AIDL vibrator service lookup.", file=sys.stderr)
        return False

    insert_after = '#define LEDS_HAPTICS_ACTIVATE_FILE\t"/sys/class/leds/vibrator/activate"\n'
    if insert_after not in text:
        print("ERROR: Could not find minuitwrp haptics definitions.", file=sys.stderr)
        return False
    text = text.replace(insert_after, insert_after + HELPERS + "\n", 1)
    changed = True

    generic = '''#else
    if (std::ifstream(LEDS_HAPTICS_ACTIVATE_FILE).good()) {
        write_to_file(LEDS_HAPTICS_DURATION_FILE, tout);
        write_to_file(LEDS_HAPTICS_ACTIVATE_FILE, "1");
    } else
        write_to_file(VIBRATOR_TIMEOUT_FILE, tout);
#endif'''
    replacement = '''#else
    if (tiro_vibrate_awinic_cont(timeout_ms)) {
        return 0;
    }
    if (tiro_vibrate_input_ff(timeout_ms)) {
        return 0;
    }
    if (std::ifstream(LEDS_HAPTICS_ACTIVATE_FILE).good()) {
        write_to_file(LEDS_HAPTICS_DURATION_FILE, tout);
        write_to_file(LEDS_HAPTICS_ACTIVATE_FILE, "1");
    } else
        write_to_file(VIBRATOR_TIMEOUT_FILE, tout);
#endif'''
    if generic not in text:
        print("ERROR: Could not find generic haptics fallback block.", file=sys.stderr)
        return False
    text = text.replace(generic, replacement, 1)
    changed = True

    if changed:
        path.write_text(text)
        print(f"Applied Tiro native-cont + persistent input-FF haptics patch: {path}")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("events_cpp", type=Path)
    args = parser.parse_args()

    if not args.events_cpp.is_file():
        print(f"ERROR: file not found: {args.events_cpp}", file=sys.stderr)
        return 2

    before = args.events_cpp.read_text()
    already = MARKER in before
    ok = patch_file(args.events_cpp)
    after = args.events_cpp.read_text()

    if already:
        return 0
    if not ok or MARKER not in after:
        return 1
    if "AServiceManager_getService(kVibratorInstance.c_str())" in after:
        print("ERROR: blocking AIDL lookup survived the patch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
