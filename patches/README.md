# Source patching

The active source transformation is implemented by:

```text
scripts/patch_haptics.py
```

A scripted transformation is used instead of a fragile line-number-dependent
unified diff because the OrangeFox `fox_12.1` branch continues to receive
maintenance commits. The script validates the expected upstream code anchors,
refuses to continue if they are missing, and is idempotent.

The patch marker inserted into `bootable/recovery/minuitwrp/events.cpp` is:

```text
TIRO_INPUT_FF_HAPTICS
```

The workflow verifies that the marker exists and that the blocking
`AServiceManager_getService(kVibratorInstance.c_str())` call is no longer
present after patching.
