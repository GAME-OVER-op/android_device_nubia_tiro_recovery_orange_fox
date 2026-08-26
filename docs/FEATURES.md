# Enabled Recovery Features

This project deliberately keeps the feature delta small. The current additions
are the upstream OrangeFox App Manager and OrangeFox root-module management.

## App Manager

`device/nubia/tiro/vendorsetup.sh` exports:

```sh
FOX_ENABLE_APP_MANAGER=1
```

OrangeFox documents the App Manager as disabled by default and warns that it
needs device testing on Android 11 and newer. On `tiro`, `/data` decryption is
already proven by the reference recovery, so the manager is enabled without
changing KeyMint, Gatekeeper, QSEE, FBE, fstab or package metadata manually.

Validation rules reject a tree that removes this flag or explicitly enables
`FOX_DISABLE_APP_MANAGER`.

## Root Module Manager

OrangeFox fox_14.1 includes root-module management for Magisk, APatch and
KernelSU-family installations. The device tree keeps these compatibility flags:

```sh
FOX_ENABLE_KERNELSU_SUPPORT=1
FOX_ENABLE_KERNELSU_NEXT_SUPPORT=1
FOX_ENABLE_SUKISU_SUPPORT=1
```

`FOX_DELETE_MAGISK_ADDON=1` is intentionally retained. It removes the bundled
Magisk installer addon, not the root-module manager. This avoids adding an
unrequested installer payload while preserving module rescue/management.

The module manager is intended for recovery/bootloop rescue. Destructive module
actions should still be tested on-device with a current backup.

## USB-OTG

No new OTG patch is applied. The known-good recovery already contains:

```text
/usb_otg  auto  /dev/block/sdg1  /dev/block/sdg  ... storage ... removable
```

so the existing path is preserved for hardware testing before any device-specific
USB changes are made.
