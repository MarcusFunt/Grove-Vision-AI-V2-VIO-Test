# Grove Vision AI Module V2 — Visual Frontend Feasibility Experiment

**Status (2026-11-07): PC-native tracker tests passed; custom firmware compiled with Arm GNU 14.2.Rel1, generated and flashed over COM5, and streams VTF1 tracking frames after reseating the OV5647 ribbon. A 15-second capture contained 118 frames in 14.52 seconds (~8.06 host-arrival fps), 74 median features, and zero sequence gaps.** There is deliberately **no VIO, ESKF, factor graph, IMU code, or historical fusion** in this package. Those will come *after* the camera frontend proves useful.

## Why this implementation

The [Himax public Grove Vision AI V2 SDK](https://github.com/HimaxWiseEyePlus/Seeed_Grove_Vision_AI_Module_V2) provides the verified sample [`hello_world_cmsis_cv`](https://github.com/HimaxWiseEyePlus/Seeed_Grove_Vision_AI_Module_V2/tree/main/EPII_CM55M_APP_S/app/scenario_app/hello_world_cmsis_cv) with an image-ready callback and 320x240 8-bit grayscale access via `app_get_raw_addr()`. The SDK also demonstrates 921600-baud UART writes via `send_result.cpp`. This experiment uses those interfaces, rather than the stock classification/detection result API. Seeed's public wiki also notes that stock firmware doesn't deliver simultaneous normal camera previews and results to a connected XIAO.

We start with a **FAST-like corners + SAD block matcher with forward/backward validation**. This is a low-compute, highly portable baseline, **not** a pyramidal Lucas–Kanade tracker. Its narrow search radius intentionally exposes whether more advanced optical flow will be required. The Cortex-M55's neural accelerator does not automatically accelerate classical optical flow.

## Contents

- `firmware/vt_tracker.[ch]` — deterministic, zero-heap native 320x240 sparse tracker (up to 96 persistent feature IDs)
- `firmware/vt_packet.[ch]` — compact binary packets, COBS framing, CRC-16/CCITT-FALSE
- `firmware/cvapp_hello_world_cmsis_cv.cpp` — Himax SDK integration adapter; compiled and flashed, with camera initialization still under investigation
- `tools/install_sdk.py` — copies the experiment into a *separate* cloned vendor SDK, preserving an original backup
- `host/record.py` — serial/byte-stream receiver, data logging, gap and CRC tracking
- `host/analyze.py` — output metrics; calibrated tick Hz optional
- `host/plot_tracks.py` — plot observed feature traces (not camera pose)
- `host/offline_opencv.py` — desktop reference with pyramidal Lucas–Kanade on videos/webcam
- `tests/` — native synthetic + protocol tests and generated replay data
- `docs/EXPERIMENT_PLAN.md` — procedure, pass/fail gates, caveats
- `docs/SDK_EVIDENCE.md` — links to exact upstream integration paths

## 1. Run without Grove hardware

Requires GCC or Clang, GNU make, and Python 3.10+. On Windows, `mingw32-make` with a MinGW GCC toolchain works with the included Makefile.

Create a local Python environment for the GUI and recorder:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-host.txt
```

Install the optional desktop video and plotting dependencies only when needed:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-optional.txt
```

```bash
mingw32-make test
.venv/Scripts/python.exe host/plot_tracks.py tests/sample_record.jsonl --min-length 2 --out tracks.png
```

On Linux/macOS, use `make test` and `.venv/bin/python` in place of the Windows commands above.

The synthetic image test shifts an image by +2,+1 pixels. The board tracker should retain at least 15 tracks and at least 80% of retained features should recover that exact integer translation. The generated packet is decoded, checksum checked, and passed through the recording and analysis pipeline.

Optional desktop feature-tracking reference (Python packages OpenCV and NumPy):

```bash
.venv/Scripts/python.exe host/offline_opencv.py /path/to/actual/test_video.mp4 --max-frames 600
```

The desktop KLT reference is **not** an MCU benchmark.

## 2. Install in a separate Himax SDK checkout

1. Make a separate checkout, following vendor SDK setup:

```powershell
git clone --recursive https://github.com/HimaxWiseEyePlus/Seeed_Grove_Vision_AI_Module_V2.git vendor/himax-grove-sdk
.venv\Scripts\python.exe tools\install_sdk.py vendor\himax-grove-sdk
```

The installer backs up the upstream adapter, frame-ready event source, SDK make configuration, and linker script; copies the experiment sources; selects `hello_world_cmsis_cv`; omits unused CMSIS-CV/DSP archives; deduplicates Windows source globs; suppresses the vendor's per-frame console line; and reduces the sample's 180 KiB heap reservation to 64 KiB for this small non-ML tracker. It keeps all changes inside the ignored SDK checkout.

2. Build with a GNU Arm Embedded toolchain. The current successful build used Arm GNU 14.2.Rel1; upstream documents 13.2.rel1. From the project root:

```powershell
mingw32-make PYTHON=.venv/Scripts/python.exe firmware-image
```

This runs the overlay installer, builds the SDK application, then invokes the bundled vendor image generator. The output is `vendor/himax-grove-sdk/we2_image_gen_local/output_case1_sec_wlcsp/output.img`; the SDK checkout and generated firmware are ignored by Git.

For a board update, install the XMODEM dependency, start the sender, then press Reset once when it prompts. Keep the board powered during transfer:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-flash.txt
mingw32-make PYTHON=.venv/Scripts/python.exe PORT=COM5 flash-firmware
```

The wrapper uses the SDK's documented 921600-baud XMODEM flow and forces UTF-8 output for the Windows progress bar. The available vendor recovery image is documented in [`docs/SDK_PIN.md`](docs/SDK_PIN.md) and may differ from the firmware currently on the board.

## 3. Hardware streaming

Connect serial according to the Seeed/Himax documentation (USB-C serial on many kits), verify the device is visible, then:

```bash
python -m pip install pyserial
python host/record.py --port /dev/ttyACM0 --baud 921600 --seconds 60 \
  --out logs/static.jsonl --raw-out logs/static.serial.bin
python host/analyze.py logs/static.jsonl --json logs/static_metrics.json
python host/plot_tracks.py logs/static.jsonl --out logs/static_tracks.png
```

Windows port example: `--port COM5`. The UART should not simultaneously be open in SenseCraft, a terminal, or other readers. If the module reports 0 valid packets, inspect whether the firmware boots, serial port/baud is correct, sensor is powered, camera ribbon direction is correct, and whether console messages mask the packets.

The first COM5 boot logged `CIS Init fail` after OV5647 I²C writes returned -60. Powering off and reseating the OV5647 ribbon resolved that probe failure. The final 15-second capture had 118 decoded frames, a median of 74 active features, zero sequence gaps, and one startup console-noise packet; per-frame text diagnostics were then removed from the UART stream.

`SystemGetTick()` is recorded as a **raw frame-ready-time tick** from the callback processing path, not a sensor exposure timestamp. The host's `recv_ns` is a *host receipt time*, not a hardware clock. Only pass `--tick-hz` after measuring the tick frequency on this device and firmware clock configuration.

## 4. Results and decision

See `docs/EXPERIMENT_PLAN.md`. The test should determine sensor-camera capture rate, processing budget, stable feature count, motion robustness, reliability, serial throughput, and whether exposure synchronization can realistically be improved. **Do not interpret feature coordinates or their change as orientation until a camera model, IMU calibration, and an actual VIO estimator exist.**

## Technical limits

- Single scale, integer optical flow, maximum ±6 pixels per frame (before motion prediction)
- 320x240 grayscale; default 96 features; 25-pixel SAD patch, cross-check
- No rolling-shutter compensation, no landmark triangulation, no RANSAC or geometric outlier rejection
- No image snapshots/ground-truth visual overlays in the device protocol yet; use a controlled fixture or additional recorded camera for ground-truth comparison
- No frame timestamps from sensor start-of-exposure; raw tick only
- Serial writes may block and reduce achievable FPS; diagnostic logs can add load
- Firmware reads upstream grayscale buffer and assumes vendor image stride/layout are unchanged
- The host's statistical report can quantify feature retention and timing but **cannot by itself establish tracking accuracy without ground truth**

## 5. Live desktop GUI over USB (NEW)

This package now includes a **single-window, lightweight Tkinter dashboard**, which you can use to check the hardware without running any VIO/Kalman-filter code. It needs Python, `tkinter` (generally bundled, sometimes `python3-tk`) and `pyserial`. **No OpenCV or Matplotlib is necessary for the GUI.**

```powershell
.venv\Scripts\python.exe host\gui.py
# Or preview without hardware:
.venv\Scripts\python.exe host\gui.py --demo static
# Or directly connect to a selected port:
.venv\Scripts\python.exe host\gui.py --port COM5
```

You can also launch `start_gui.bat` on Windows or `./start_gui.sh` on Linux/macOS. Connect the USB cable, choose the detected serial port, click **Connect**, and examine the live feature map, motion arrows, matched IDs, track retention, flow dispersion, feature count, USB packet loss and CRC status. Click **Show B/W footage** to request actual 160x120 grayscale camera frames in a separate window. Preview images share the tracking UART, so tracking throughput drops while this option is on. **Start 15 s stationary test** with the camera rigidly mounted to collect pixel-repeatability statistics. Sessions are automatically captured in `logs/gui_.../`, with decoded JSONL and raw serial bytes for hardware sessions; raw `.bin` logs can be replayed directly, including preview images when they were captured.

**For a complete explanation of graphs, metrics, limits and troubleshooting, read [`docs/GUI_GUIDE.md`](docs/GUI_GUIDE.md).** The GUI requires the experiment's binary `VTF1` firmware, not the original factory SenseCraft detection output. A stable plot is evidence of *internal consistency*, not proof of metrically accurate optical flow.
