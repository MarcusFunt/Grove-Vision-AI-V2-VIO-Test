# Himax SDK pin and local build state

## Source pin

- Repository: <https://github.com/HimaxWiseEyePlus/Seeed_Grove_Vision_AI_Module_V2>
- Commit: `d3265e20d75fe20faccbf185d24454ad08b2fda8`
- Submodule `EPII_CM55M_APP_S/library/cmsis_cv/CMSIS-CV`: `286e282ef557bb86a0798bf2d38b50b045256144`
- Local clone: `vendor/himax-grove-sdk/` (ignored by Git)
- The clone was created recursively on 2026-11-07 from the upstream `main` checkout.

## Local SDK overlay

`tools/install_sdk.py` overlays the experimental adapter and portable tracker/protocol files into `hello_world_cmsis_cv`. It preserves the upstream C++ adapter, frame-ready event source, top-level `makefile`, scenario `.mk` file, linker script, and Windows wildcard helper as `.original` backups. It selects `APP_TYPE = hello_world_cmsis_cv`, removes unused CMSIS-CV/DSP library entries, suppresses the per-frame console line, and lowers the linker heap reservation to 64 KiB. The 180 KiB sample heap caused a linker stack/heap overlap with this app's 101 KiB static data footprint.

The current SDK make system compiles `vt_tracker.c` and `vt_packet.c` as normal scenario sources. The adapter must not `#include` those `.c` files. The vendor's source-discovery globs match both lowercase and uppercase extensions; on Windows these globs return the same files twice. The installer applies `sort` to those lists to prevent duplicate linker inputs.

The UART adapter uses `USE_DW_UART_0`, matching the SDK's console UART selection and sample UART API. Serial packets use 921600 baud.

## Recovery image

The recursive SDK checkout contains the vendor-provided `Seeed_SenseCraft_AI_2023_12_19T183401_402.img` image (487,424 bytes; SHA-256 `BE12866A8790415F6E14638C1EDD9F274BF8BF2EDB27E77BD3DE7CC95CB59957`). This is the available recovery image; it may not match the exact factory firmware currently installed on the board. Keep the file with the ignored SDK checkout and do not replace it with the experiment image.

## Toolchain

The upstream SDK instructions currently specify Arm GNU Toolchain 13.2.rel1 for Windows. The local machine has Arm GNU Toolchain 14.2.Rel1 installed, and the custom application has built with that compiler. This is a successful local build but differs from the vendor-documented compiler version.

## Build result

Build succeeded with Arm GNU 14.2.Rel1. The ELF reports 124,184 bytes used in the secure application ROM region and 101,484 bytes in the secure application data region. Vendor image generation succeeded; the current 311,296-byte output has SHA-256 `AFCA5DD35FA7BFD954A99C4708707E44D5BD695A20EF43257338A8B5FB678DA1`. The vendor signer regenerates certificate metadata, so a later image-generation run can produce a different digest for the same ELF.

The initial compile exposed and corrected the UART enum reference and C/C++ linkage declarations. The first link exposed the Windows duplicate-glob issue, Windows command-line length while archiving unused CMSIS-DSP, and the sample heap reservation overlapping static application data. The installer now deduplicates source globs, omits unused CMSIS-CV/DSP archives, and reduces the heap reservation from 180 KiB to 64 KiB.

The custom image was sent to COM5 through the vendor XMODEM updater. Its first boot printed the expected Arm GNU 14.2.1 and hello-world banner, then reported `dw_iic_write err_code:-60` and `CIS Init fail` during OV5647 setup. Powering off and reseating the ribbon resolved camera initialization.

The overlay now suppresses the SDK's per-frame UART debug line. The latest image was sent successfully using the XMODEM updater, and the board rebooted. A 15-second capture produced 118 decoded VTF1 frames in 14.52 seconds (~8.06 host-arrival fps), 74 median active features, and zero sequence gaps. Median host packet interval was 123.9 ms and p95 was 130.0 ms. The recorder saw one malformed/noise packet at startup; frame-ready text no longer appears once per frame. These numbers are an initial check, not ground-truth motion accuracy or a calibrated camera frame rate.
