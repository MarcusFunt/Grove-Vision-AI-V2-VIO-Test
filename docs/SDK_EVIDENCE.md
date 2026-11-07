# Upstream evidence and integration assumptions

Research checked against public source on 2026-11-07.

## Confirmed by vendor example source

- Official SDK: https://github.com/HimaxWiseEyePlus/Seeed_Grove_Vision_AI_Module_V2
- 320x240 grayscale image extraction: `EPII_CM55M_APP_S/app/scenario_app/hello_world_cmsis_cv/cvapp_hello_world_cmsis_cv.cpp`: sample makes an `arm_cv_image_gray8_t`, sets `width=320`, `height=240`, `pData=(uint8_t*)app_get_raw_addr()`.
- Camera-ready path: `.../hello_world_cmsis_cv/hello_world_cmsis_cv.c` calls `cv_hello_world_cmsis_cv_run()` in the `EVT_INDEX_XDMA_FRAME_READY` callback, and configures `SENSORDPLIB_PATH_INT_INP_HW5X5_JPEG` / `APP_DP_RES_YUV640x480_INP_SUBSAMPLE_2X`.
- Subsequent capture trigger: the vendor `cvapp_hello_world_cmsis_cv.cpp` calls `sensordplib_retrigger_capture()` at the end of processing.
- Serial: `.../hello_world_cmsis_cv/send_result.cpp` uses `hx_drv_uart_get_dev((USE_DW_UART_E)CONSOLE_UART_ID)` and `uart_open(UART_BAUDRATE_921600)`.
- Vendor install/build instruction: `README.md`, scenario selected with `APP_TYPE = hello_world_cmsis_cv`, GNU Arm toolchain, `we2_image_gen_local` step.
- In the pinned SDK build, the scenario `.c` files are compiled separately; the adapter must not include `vt_tracker.c` or `vt_packet.c` directly.
- The sample defines `CONSOLE_UART_ID` as 0 in `send_result.h`; the adapter uses the SDK enum `USE_DW_UART_0` directly.
- Vendor camera config: `.../hello_world_cmsis_cv/hello_world_cmsis_cv.mk` selects `cis_ov5647`.
- Official camera support page: https://wiki.seeedstudio.com/Grove-vision-ai-v2-camera-supported/
- Official module wiki: https://wiki.seeedstudio.com/grove_vision_ai_v2/
- Official SDK includes `hello_world_cmsis_cv` working examples for Gaussian/Canny operations and UART image export; these should be used as reference when changing buffer/camera configuration.

## Inference that MUST be validated on actual board

1. C++ adapter compiling against the precise installed SDK revision and compiler flags.
2. Grayscale frame being DMA-coherent at read time.
3. `SystemGetTick` counter/wrap semantics, stability under clock scaling, and ticks-per-second.
4. Whether the frame-ready callback is close enough to frame capture for intended latency measurement (it is **not** the exposure timestamp).
5. Image rate under blocking UART transmission and recapture-after-processing.
6. Source of serial output: console pin routing and how to disable verbose print messages.
7. Raw OV5647 exposure time, rolling-shutter motion distortion, autofocus/focus and lighting settings.

## Why the code uses a portable baseline rather than an NPU model

Neural-network accelerators target supported quantized networks, not automatically a FAST/KLT/OpenCV tracking primitive. A native SAD/FAST-like implementation makes measurements understandable and gives a reproducible first feasibility test. If feature retention fails, the next experiment should test pyramidal KLT or learned features, not claim the module is intrinsically incapable.
