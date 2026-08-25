#
# Copyright (C) 2023 The Android Open Source Project
#
# SPDX-License-Identifier: Apache-2.0
#

DEVICE_PATH := device/nubia/tiro

# Inherit from device.mk configuration
$(call inherit-product, $(DEVICE_PATH)/device.mk)

# Release name
PRODUCT_RELEASE_NAME := tiro

## Device identifier
PRODUCT_DEVICE := tiro
PRODUCT_NAME := twrp_tiro
PRODUCT_BRAND := nubia
PRODUCT_MODEL := NX769J
PRODUCT_MANUFACTURER := nubia

# Assert
TARGET_OTA_ASSERT_DEVICE := tiro,NX769J

# Theme
TW_STATUS_ICONS_ALIGN := center
#TW_Y_OFFSET := 99
#TW_H_OFFSET := -99

# Strongbox Device Decryption
TW_INCLUDE_OMAPI := true

# Build identification
TW_DEVICE_VERSION := tiro-NX769J-source
