# Architecture

## Design principle

The project is a source build, but its first target is behavioral equivalence
with a recovery that is already proven on the hardware.

```text
Known-good recovery userspace
        |
        +-- proven FBE / KeyMint / Gatekeeper / QSEE chain
        +-- proven fstab and recovery init
        +-- proven 100 MiB header-v4/LZ4 image layout
        |
        +-- replace only problematic haptics path
                     |
                     +-- direct qcom-hv-haptics input FF
                     +-- non-blocking fallback behavior
```

## Recovery image

The recovery image contains no kernel. This follows both the known-good image
and modern SM8650 recovery layout:

```make
BOARD_BOOT_HEADER_VERSION := 4
BOARD_KERNEL_PAGESIZE := 4096
BOARD_RAMDISK_USE_LZ4 := true
BOARD_EXCLUDE_KERNEL_FROM_RECOVERY_IMAGE := true
BOARD_RECOVERYIMAGE_PARTITION_SIZE := 104857600
```

## Decryption

Enabled build features include:

```make
TW_INCLUDE_CRYPTO := true
TW_INCLUDE_CRYPTO_FBE := true
TW_INCLUDE_FBE_METADATA_DECRYPT := true
BOARD_USES_QCOM_FBE_DECRYPTION := true
TW_USE_FSCRYPT_POLICY := 2
BOARD_USES_METADATA_PARTITION := true
```

The recovery root also contains the already validated QTI KeyMint,
Gatekeeper/QSEE userspace and `prepdecrypt.sh` chain.

## Haptics

The old Xiaomi AIDL haptics compile flags are intentionally absent. Haptics are
not globally disabled. The patched generic minuitwrp backend discovers a Linux
input FF haptics device and caches its fd. This keeps the GUI thread independent
from vendor Binder service startup.
