#!/usr/bin/env python3
"""Patch OrangeFox/TWRP minuitwrp for non-blocking Red Magic haptics.

The known-good recovery enables a Xiaomi AIDL vibrator instance. On tiro the
synchronous service lookup can block the GUI thread for about five seconds on
every tap. This patch:

1. Changes AIDL lookup from AServiceManager_getService() to the non-blocking
   AServiceManager_checkService() as a safety net.
2. Adds a direct Linux input force-feedback backend.
3. Uses the FF backend before legacy sysfs haptics in the generic path.

The device BoardConfig intentionally does not enable AIDL haptics, so the normal
runtime path is input FF -> sysfs fallback. qcom-hv-haptics on SM8650 exposes
FF_CONSTANT and is the preferred target.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

MARKER = "TIRO_INPUT_FF_HAPTICS"

HELPERS = r'''

/* TIRO_INPUT_FF_HAPTICS
 *
 * Recovery only needs short UI feedback. Driving the kernel input FF device
 * directly avoids a synchronous dependency on a vendor Binder HAL. The fd is
 * discovered once and then cached. Failure is non-fatal and falls back to the
 * legacy sysfs path.
 */
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

        // qcom-hv-haptics exposes FF_CONSTANT. Prefer it when available.
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
    // Keep -2 when nothing matched so a haptics device that registers later
    // can be discovered by a subsequent tap without blocking the UI thread.
    return tiro_ff_fd >= 0 ? tiro_ff_fd : -1;
}

static void tiro_stop_old_ff_effect(int fd) {
    if (tiro_ff_effect_id < 0) return;

    struct input_event stop = {};
    stop.type = EV_FF;
    stop.code = static_cast<__u16>(tiro_ff_effect_id);
    stop.value = 0;
    (void)write(fd, &stop, sizeof(stop));
    (void)ioctl(fd, EVIOCRMFF, tiro_ff_effect_id);
    tiro_ff_effect_id = -1;
}

static bool tiro_vibrate_input_ff(int timeout_ms) {
    int fd = tiro_open_input_ff_haptics();
    if (fd < 0 || timeout_ms <= 0) return false;

    tiro_stop_old_ff_effect(fd);

    struct ff_effect effect = {};
    effect.type = static_cast<__u16>(tiro_ff_effect_type);
    effect.id = -1;
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
        close(fd);
        tiro_ff_fd = -2;
        tiro_ff_effect_id = -1;
        return false;
    }

    struct input_event play = {};
    play.type = EV_FF;
    play.code = static_cast<__u16>(effect.id);
    play.value = 1;

    if (write(fd, &play, sizeof(play)) != static_cast<ssize_t>(sizeof(play))) {
        LOGI("Input FF haptics: play failed; using fallback haptics\n");
        (void)ioctl(fd, EVIOCRMFF, effect.id);
        close(fd);
        tiro_ff_fd = -2;
        tiro_ff_effect_id = -1;
        return false;
    }

    tiro_ff_effect_id = effect.id;
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
        print(f"Applied non-blocking input-FF haptics patch: {path}")
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
