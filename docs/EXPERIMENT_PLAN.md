# Hardware validation protocol and go/no-go rubric

**Research question:** Can this specific camera+Himax firmware sustain reliable, timestampable, high-quality *visual feature tracks* useful for later visual-inertial estimation?

## Native synthetic sweep already observed

The portable baseline recovered displacement exactly in this deterministic textured-image test at 0, 1, 2, 4 and 6 horizontal pixels per frame, while no original track IDs survived at 8 or 12 pixels per frame. This is expected from a ±6 pixel search radius, **not evidence about the Grove camera or CPU**. It is also not a substitute for actual scene/video testing.

## Phase 0: software-only

- Run `make test` (portable C image-shift and protocol tests).
- Run the desktop OpenCV `offline_opencv.py` on videos representing intended vehicle use; save those videos.
- Inspect SDK build/flash docs, camera ribbon orientation, and how to restore factory image.

## Phase 1: static fixture, 60 seconds

- Mount camera rigidly facing a scene with many nonrepeated features (printed AprilTag board or richly textured poster) at a known distance; keep illumination constant.
- Record 60 seconds to raw and JSONL, no other serial readers.
- Measure frame count, camera frame-ready timestamp intervals, stable feature IDs, drops and dropped/corrupt packets.
- Keep camera still; many tracked feature pixels should remain within a few pixels. This does **not** establish subpixel error without independently measured ground truth.
- Repeat with low texture, low light, overexposure and changing light to identify failure conditions.

## Phase 2: known motion and speed sweep

- Translate horizontally/vertically using a fixture with known displacement. Capture 0.5/1/2/4/6/8/12 px per frame equivalents where feasible, varying camera distance and velocity.
- For pixel-ground-truth, use a calibrated pattern/recorded video from a reference camera and evaluate projected motion; do not treat the programmed motor command as precise actual optical flow.
- Rotate yaw/pitch/roll with a measured turntable or calibrated encoder, plus high-contrast scenes and motion blur. Compare downstream feature data to ground-truth projected points with lens calibration.
- Collect a 3-5 minute continuous run to measure dropouts/reboots and feature-track persistence.

## Phase 3: timestamp and communications audit

- Verify actual timestamp semantics in the sensor driver, ideally capture start-of-exposure or exposure midpoint.
- Measure clock frequency by stable external time reference (or logic analyzer/GPIO toggles synchronized with frame event). `--tick-hz` is only valid after this.
- Measure time from camera exposure / frame-ready signal to UART packet completion using a logic analyzer. A serial packet receipt time measured on a desktop includes USB latency.
- Repeat with reduced feature count, high feature count, verbose logging on/off and UART bandwidth variations to distinguish algorithm cost from serial backpressure.
- Monitor whether the app triggers the next camera capture only *after* serial transfer; this baseline does, creating a self-throttling capture pipeline.

## Recommended, explicitly provisional feasibility gates

These are initial engineering targets for *small low-speed robots*, not published module performance specifications and not UAV safety criteria.

| Metric | First-pass target | How to validate |
|---|---:|---|
| Device frame output rate | ≥20 fps sustained (30 preferred) | Calibrated device-ready timestamps, not host chunk reads |
| Device rate variability | 95th-percentile frame interval <2x median | Device-ready timestamps |
| Features under rich texture | ≥40 active, spread across image | Observed packets + spatial coverage |
| Long-lived feature tracks | ≥20 tracks surviving 0.5 s | Stable IDs and calibrated fps |
| Tracking pixel accuracy | Median <1.5 px under supported displacement | Independent projected ground truth |
| Packet CRC corruption | 0 in a clean 5-min test | Raw serial stream + decoder |
| Packet loss | <1% in clean 5-min test | Sequence numbers |
| Headroom for faster motion | Re-evaluate at ±6 px/frame or more | Compare to desktop KLT and motion sweep |
| VIO-suitable timing | Exposure timestamp or calibrated offset with bounded jitter | Hardware sync/logic analyzer |

Failures in the first run may be caused by the crude integer block matcher, not the processor itself. If tracking fails but the device clearly has CPU headroom, benchmark a multiscale KLT next. If board cannot provide reliable frame timestamps or camera frame rate, that is a stronger reason to switch visual hardware.

## Benchmark interpretation

- Native `make test` demonstrates deterministic packet/tracker logic on a computer only.
- A frame-ready timestamp helps characterize cadence, not absolute visual-inertial alignment.
- Feature count and lifespan alone do not guarantee geometric correctness; repetitive patterns may yield long-lived but wrong tracks.
- A packet delivered every 33 ms does not guarantee 33 ms *latency*, because capture, processing and serial buffering are separate.
- The OV5647 camera has rolling shutter; fast-turn tests will reveal potential distortion, but no compensation exists in this prototype.

## Decision and next stage

**Accept as a frontend candidate** only if the hardware demonstrates sufficient tracked-feature quality, rate, bounded jitter, stable operation and a plausible path to calibrated exposure timestamps. Otherwise, compare against a global-shutter camera on another MCU/SBC.

After passing this experiment, the *next separate project phase* may define a time-synchronized feature-track interface for MSCKF or a local fixed-lag smoother. ESKF feedback / historical optimization is **deliberately out of scope**.
