# Third-party components

This repository combines project-authored build automation with a recovery
device-tree compatibility snapshot and upstream source projects fetched during
the build.

## OrangeFox Recovery Project

The build synchronizes OrangeFox Recovery Project source and vendor trees from
GitLab. Their files remain under their upstream licenses and copyright notices.

## TWRP / AOSP

OrangeFox's synchronization process uses the TWRP minimal Android source base.
Those projects retain their respective licenses.

## nubia SM8650 sources

The following public projects are hardware references:

- nubia-sm8650-devs/android_device_nubia_tiro
- nubia-sm8650-devs/android_device_nubia_sm8650-common
- nubia-sm8650-devs/android_kernel_nubia_sm8650
- nubia-sm8650-devs/android_kernel_nubia_sm8650-modules
- nubia-sm8650-devs/android_kernel_nubia_sm8650-devicetrees

## Compatibility blobs

`device/nubia/tiro/recovery/root` contains vendor/OEM binaries retained from the
known-good recovery userspace, primarily to preserve proven FBE decryption and
related recovery functionality. These binaries are not relicensed by this
project. Redistribution and use remain subject to the rights and terms of their
respective owners.
