# USB GUI guide — Grove Vision AI Module V2

## Quick start (Windows / Linux / macOS)

1. Install **Python 3.10+**. On some Linux systems also install `python3-tk`.
2. From the project root, create an environment and install the USB serial dependency:

   ```bash
   python -m venv .venv
   # Windows PowerShell
   .venv\Scripts\python.exe -m pip install -r requirements-host.txt
   .venv\Scripts\python.exe host/gui.py
   ```

   On Linux/macOS, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`. You can also double-click `start_gui.bat` on Windows or run `./start_gui.sh` on Linux/macOS.
3. Use **Refresh** to find the board's serial port, e.g. `COM5`, `/dev/ttyACM0`, `/dev/ttyUSB0`, or `/dev/cu.usbmodem*`. Select it and click **Connect**.
4. The GUI uses **921600 baud** and expects **custom VTF1 tracking firmware** from the companion `firmware/` directory. The stock Grove detection/classification firmware does *not* speak this protocol.
5. Wait for tracks to appear. Move the camera slowly in front of a textured scene; compare the visual arrows, feature count, matched IDs, motion scatter and packet health. Start with well-lit, detailed, nonrepetitive texture.
6. Click **Show B/W footage** to open a separate window with actual camera pixels. The preview is 160×120 grayscale and sends one image for every two tracking frames. It uses the same UART as tracking and lowers tracking rate while enabled. Click **Hide B/W footage** to stop it. Replays show images only when the raw recording was made with preview enabled.
7. Fix the camera rigidly and press **Start 15 s stationary test**. Do not touch the camera, mount or scene while it runs. Repeat in dim light and under strong light changes.
8. Click **Export report** for a summary JSON. Full session JSONL measurements are automatically saved under `logs/gui_.../frames.jsonl`. Hardware sessions also save `serial_raw.bin` for replay; preview images are included in the raw stream when enabled.

Run `python host/gui.py --demo static` to preview the GUI without hardware. The demo is clearly labeled and **must not** be reported as a real board measurement. `--demo motion` simulates coherent camera movement. Run `python host/gui.py --replay logs/.../serial_raw.bin` for replay. Use `python host/gui.py --port COM5` for direct launch with a configured port.

## What to look at

| Display | Interpretation |
|---|---|
| Feature map | 320×240 coordinate map. Dots are points, arrows are one-frame displacement (visually enlarged). Red indicates deviations from the frame's median displacement. The separate B/W footage window shows camera pixels. |
| B/W camera preview | Actual OV5647 grayscale pixels, area-downsampled to 160×120. UART bandwidth limits the preview and reduces tracking throughput while enabled. |
| Active tracks | Number of features in the current packet. A high count alone does not prove validity. |
| Matched IDs | Number of IDs also seen in the preceding frame. Measures track continuity. |
| Retention | Matched IDs divided by feature count in previous frame. Churn and occasional losses are expected; massive unexplained losses deserve attention. |
| Common motion | Median `(dx,dy)` displacement for matched tracks. A camera movement can make this nonzero even when tracking is correct. |
| Track agreement | Heuristic based on the median flow scatter. **Not an accuracy pass/fail**; rotation and parallax can cause legitimate scatter. |
| Motion scatter | Median residual distance from the frame's common motion. High values indicate disagreements, *but* real 3D parallax or rotation may cause legitimate nonuniform flow. |
| Image coverage | Fraction of 4×4 cells containing any tracked feature. Poor spatial distribution weakens geometry. |
| Observed host FPS | Approximate host-arrival frequency from decoded packets. USB buffering can distort it. |
| Device frame interval | Uncalibrated **raw device ticks** between frame-ready values, **not milliseconds**, and **not exposure times**. |
| Sequence gaps / CRC | Missing numbered packets and corrupt/invalid protocol frames. Mixed console text may register invalid packets. |
| Stationary RMS jitter | For stable IDs observed in at least five frames: RMS of tracked pixel position around its temporal mean. Median/p95 across qualifying tracks. Any genuine camera motion invalidates the stationary assumption. |

**Important:** The tracker is an integer-pixel patch matcher. Stationary jitter can read 0.0 px even though actual subpixel noise or systematic tracking error exists. A consistent but *incorrect* optical-flow field can have near-zero scatter. Ground-truth tests, video-based inspection and independent camera timing validation remain necessary before claiming suitability for VIO.

## Diagnostic checklist

**No USB port shown:** Install pyserial, check USB cable and OS device permissions/drivers. On Linux you may need membership in the `dialout` group and to log in again. Close SenseCraft, serial terminals and other serial readers before opening the port.

**Port opens, but zero packets:** Confirm the custom experimental firmware boots; check its UART log for camera initialization errors, then verify the camera ribbon, module compatibility, and power. The GUI requires VTF1 COBS-framed binary messages. This board's first COM5 run returned OV5647 I²C no-ACK (-60); powering off and reseating the camera ribbon resolved it.

**Many CRC errors:** Check baud, mixed debug logs, transport wiring and power. Raw bytes are preserved in `serial_raw.bin`; replay them to reproduce the issue.

**Low FPS:** First turn off **Show B/W footage**; preview uses substantial UART bandwidth. Without preview, try fewer features or less verbose firmware logging, examine block-match computation and UART throughput, and confirm the sample retriggers camera capture *after* processing/transmission. USB packet timing does not equal capture timing.

**Flow is chaotic while static:** Check mounting stability, lighting/flicker, camera focus, blurred image, repeated visual patterns, poor low-level camera capture, and track-ID recycling. Repeat at a known textured target.

**Flow collapses during fast motion:** First prototype has only a ±6 pixel search radius and no multiscale optical flow. This is an **algorithm limitation**, not proof the Himax chip is unsuitable.

## Experimental status

The host-side GUI demo is visually verified, and the metric logic has passed synthetic and packet-replay checks. A 15-second hardware capture produced 118 decoded frames in 14.52 seconds, with zero sequence gaps and 74 median features. The per-frame SDK text log is now suppressed, leaving one startup noise packet in that capture. Motion accuracy, long-duration reliability, timestamp precision, and sustained performance remain unmeasured. The GUI does not run ESKF, VIO, SLAM or historical state correction; those are future phases.
