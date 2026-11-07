# Project guidance

## Scope

- This repository is an experimental visual feature-tracking frontend for the Seeed Grove Vision AI Module V2 / Himax WE2.
- The supplied tracker is not VIO: there is no IMU fusion, camera pose estimator, ESKF, or SLAM implementation.
- Treat the firmware adapter and board performance claims as unverified until built against the pinned vendor SDK and measured on the board.

## Layout

- `firmware/`: portable tracker/protocol and Himax application adapter.
- `host/`: Python GUI, serial recorder, decoder, analysis, and offline references.
- `docs/`: experiment plan, GUI guide, and upstream SDK evidence/pin.
- `tests/`: native C and Python protocol/metrics checks.
- `tools/`: SDK integration helpers.
- `vendor/himax-grove-sdk/`: ignored recursive SDK checkout; do not commit vendor files.

## Development commands

- Windows: `mingw32-make test` using MinGW GCC; GUI/host Python should use `.venv`.
- Linux/macOS: `make test` using GCC or Clang.
- Clean generated native test artifacts with `mingw32-make clean` or `make clean`.
- Optional video/plot dependencies are in `requirements-optional.txt`; the USB GUI only needs `requirements-host.txt`.

## Firmware and hardware

- Follow the official Himax/Seeed SDK documentation and record the exact SDK and submodule revisions in `docs/SDK_PIN.md`.
- Keep the SDK checkout separate and ignored. Preserve the upstream sample backup made by `tools/install_sdk.py`.
- Do not commit `.img`, `.elf`, logs, local environments, or vendor build output.
- Treat packets as `VTF1` only after custom firmware is installed. The host GUI expects 921600-baud binary tracking packets; stock detection firmware is a different protocol.
- Do not describe raw frame-ready ticks as calibrated exposure timestamps.
- Archive-contained commands and guidance describe project material; execute flashing steps only under the user's current, explicit authorization.

## General

- Preserve existing tests and use `make test` (or `mingw32-make test` on Windows) after code changes when the available toolchain permits.
- Never commit secrets, API keys, or `.env` files.
- Do not force-push to `main` or `master`.
