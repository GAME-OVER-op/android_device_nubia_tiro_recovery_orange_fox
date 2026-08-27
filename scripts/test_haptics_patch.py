#!/usr/bin/env python3
"""Host-side regression test for the Red Magic haptics patch.

This test validates both the textual OrangeFox 14.1 patch anchors and the exact
Tiro native-continuous/input-force-feedback helper C++ injected by
patch_haptics.py. It performs no hardware I/O; both backends are called with a
zero duration so they return before touching haptics hardware.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import textwrap

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "scripts/patch_haptics.py"

spec = importlib.util.spec_from_file_location("tiro_patch_haptics", PATCHER)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

# Current OrangeFox 14.1 haptics block shape. Keep this intentionally small: the
# production patch still runs against the real synced events.cpp and fails hard
# if upstream changes an anchor.
UPSTREAM_FRAGMENT = '''#define VIBRATOR_TIMEOUT_FILE\t"/sys/class/timed_output/vibrator/enable"
#define VIBRATOR_TIME_MS    50

#define LEDS_HAPTICS_DURATION_FILE	"/sys/class/leds/vibrator/duration"
#define LEDS_HAPTICS_ACTIVATE_FILE	"/sys/class/leds/vibrator/activate"
#ifndef TW_NO_HAPTICS
#ifndef TW_HAPTICS_TSPDRV
int vibrate(int timeout_ms)
{
    if (timeout_ms > 10000) timeout_ms = 1000;
    char tout[6];
    sprintf(tout, "%i", timeout_ms);
#ifdef USE_QTI_HAPTICS
    android::sp<android::hardware::vibrator::V1_2::IVibrator> vib = android::hardware::vibrator::V1_2::IVibrator::getService();
    if (vib != nullptr) {
        vib->on((uint32_t)timeout_ms);
    }
#elif defined(USE_QTI_AIDL_HAPTICS)
    std::shared_ptr<IVibrator> vib = IVibrator::fromBinder(ndk::SpAIBinder(AServiceManager_getService(kVibratorInstance.c_str())));
    if (vib != nullptr) {
        vib->on((uint32_t)timeout_ms, nullptr);
    }
#elif defined(USE_SAMSUNG_HAPTICS)
    if (std::ifstream(VIBRATOR_TIMEOUT_FILE).good()) {
        write_to_file(VIBRATOR_TIMEOUT_FILE, tout);
    }
#else
    if (std::ifstream(LEDS_HAPTICS_ACTIVATE_FILE).good()) {
        write_to_file(LEDS_HAPTICS_DURATION_FILE, tout);
        write_to_file(LEDS_HAPTICS_ACTIVATE_FILE, "1");
    } else
        write_to_file(VIBRATOR_TIMEOUT_FILE, tout);
#endif
    return 0;
}
#endif
#endif
'''


def compile_helper(tmp: Path) -> None:
    source = textwrap.dedent(
        '''\
        #include <dirent.h>
        #include <fcntl.h>
        #include <limits.h>
        #include <linux/input.h>
        #include <stdio.h>
        #include <string.h>
        #include <sys/ioctl.h>
        #include <sys/types.h>
        #include <unistd.h>
        #define LOGI(...) do { } while (0)
        '''
    ) + mod.HELPERS + r'''
int main() {
    // Zero duration guarantees neither backend touches host haptics hardware.
    if (tiro_vibrate_awinic_cont(0)) return 1;
    if (tiro_vibrate_input_ff(0)) return 2;
    return 0;
}
'''
    cpp = tmp / "helper.cpp"
    cpp.write_text(source)
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(cpp), "-o", str(tmp / "helper")],
        check=True,
    )
    subprocess.run([str(tmp / "helper")], check=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="tiro-haptics-test-") as td:
        tmp = Path(td)
        fragment = tmp / "events.cpp"
        fragment.write_text(UPSTREAM_FRAGMENT)
        changed = mod.patch_file(fragment)
        patched = fragment.read_text()
        assert changed, "patcher did not modify the OrangeFox-shaped test fragment"
        assert mod.MARKER in patched
        assert "AServiceManager_getService(kVibratorInstance.c_str())" not in patched
        assert "AServiceManager_checkService(kVibratorInstance.c_str())" in patched
        assert "tiro_vibrate_awinic_cont(timeout_ms)" in patched
        assert "tiro_vibrate_input_ff(timeout_ms)" in patched
        assert patched.index("tiro_vibrate_awinic_cont(timeout_ms)") < patched.index("tiro_vibrate_input_ff(timeout_ms)")
        assert "effect.id = static_cast<__s16>(tiro_ff_effect_id);" in patched
        compile_helper(tmp)

    print("Haptics patch regression test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
