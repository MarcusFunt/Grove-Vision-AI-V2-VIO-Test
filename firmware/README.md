# Grove firmware experiment (initial board bring-up)

This is a custom camera-tracking replacement for Himax's existing `hello_world_cmsis_cv` example, not a standalone firmware image. It relies on the exact upstream example whose `cvapp_hello_world_cmsis_cv.cpp` reads a 320x240 grayscale frame from `app_get_raw_addr()` and whose frame-ready callback invokes `cv_hello_world_cmsis_cv_run()`.

The algorithm is a portable, modest-compute **FAST-like corner + integer SAD-search / forward-backward tracking baseline**. It is deliberately NOT marketed as a pyramidal Lucas-Kanade implementation. It will fail for >6 px frame-to-frame movement, significant blur, strong rotation, drastic lighting shifts, and complex scenes; those failures are the point of the initial experiment.

`cvapp_hello_world_cmsis_cv.cpp` replaces the upstream source of the same name; the other four `.h/.c` files are copied beside it. The SDK build compiles the `.c` files as separate sources, so the adapter does not include them. `tools/install_sdk.py` applies the overlay, backs up the upstream adapter and SDK make configuration, selects this scenario, and omits unused CMSIS-CV/DSP archives.

Important: derived `frame_ready_ticks` is NOT an exposure timestamp, and its tick frequency is not claimed to be calibrated. The experiment can measure throughput, tracking survival, and clock-interval consistency. It CANNOT yet establish trustworthy VIO timing or end-to-end latency without an external ground truth/synchronization setup.

UART is presumed to be the console UART configured to 921600 baud by the upstream SDK. Boot/debug logs may appear before packet delimiter boundaries. The receiver explicitly resynchronizes using zero delimiters + CRC + magic. The SDK uses `DBG_LESS_INFO` for a frame-ready message, so serial logging can be an appreciable extra overhead. Ensure no other program shares this UART.

The GUI can request an optional `VTI1` camera preview over the same UART. Preview packets contain a 160x120 8-bit grayscale image, area-downsampled from the camera's 320x240 frame. The firmware sends one preview image for every two tracker frames only while the GUI requests it. A frame is about 19.2 KiB before framing, so enabling preview uses substantial UART bandwidth and lowers the tracking rate. The feature is opt-in and has no throughput cost while disabled.

The application compiled with Arm GNU 14.2.Rel1 and was flashed to COM5 using the SDK XMODEM updater. Its first boot found no I²C acknowledgment from OV5647 (-60); after powering off and reseating the ribbon, camera initialization succeeded and the board emitted VTF1 frames. A follow-up build suppresses the vendor's per-frame text log so it no longer interleaves with binary packets.

An initial 15-second capture contained 118 frames in 14.52 seconds (~8.06 host-arrival fps), with zero sequence gaps and 74 median active features. Still unverified: motion accuracy against ground truth, long-duration reliability, grayscale buffer coherency, calibrated exposure timing, and sustained performance under varied lighting and motion. Do not interpret the initial capture as a VIO accuracy result.
