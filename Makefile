CC ?= cc
PYTHON ?= python
CFLAGS ?= -std=c11 -Wall -Wextra -Werror -O2

.PHONY: test clean sdk-prepare firmware firmware-image flash-firmware

SDK_DIR ?= vendor/himax-grove-sdk
SDK_BUILD_DIR = $(SDK_DIR)/EPII_CM55M_APP_S
FIRMWARE_IMAGE = $(SDK_DIR)/we2_image_gen_local/output_case1_sec_wlcsp/output.img
PORT ?= COM5

test: tests/native_smoke tests/native_sweep
	./tests/native_smoke
	./tests/native_sweep
	$(PYTHON) -m unittest discover -s tests -p 'test_*.py' -v
	$(PYTHON) host/record.py --input tests/sample_stream.bin --out tests/sample_record.jsonl
	$(PYTHON) host/analyze.py tests/sample_record.jsonl

tests/native_smoke: tests/native_smoke.c firmware/vt_tracker.c firmware/vt_packet.c firmware/vt_tracker.h firmware/vt_packet.h
	$(CC) $(CFLAGS) -Ifirmware tests/native_smoke.c firmware/vt_tracker.c firmware/vt_packet.c -o $@

tests/native_sweep: tests/native_sweep.c firmware/vt_tracker.c firmware/vt_tracker.h
	$(CC) $(CFLAGS) -Ifirmware tests/native_sweep.c firmware/vt_tracker.c -o $@

sdk-prepare:
	$(PYTHON) tools/install_sdk.py $(SDK_DIR)

firmware: sdk-prepare
	$(MAKE) -C $(SDK_BUILD_DIR) clean
	$(MAKE) -C $(SDK_BUILD_DIR) -j4

firmware-image: firmware
	$(PYTHON) tools/build_image.py --sdk $(SDK_DIR)

flash-firmware:
	$(PYTHON) tools/flash_firmware.py --sender $(SDK_DIR)/xmodem/xmodem_send.py --image $(FIRMWARE_IMAGE) --port $(PORT)

clean:
	$(PYTHON) -c "from pathlib import Path; [Path(p).unlink(missing_ok=True) for p in ('tests/native_smoke', 'tests/native_smoke.exe', 'tests/native_sweep', 'tests/native_sweep.exe', 'tests/sample_stream.bin', 'tests/sample_record.jsonl')]"
