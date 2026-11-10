# Timing-focused LSM6DS3 companion acquisition

**Status: prototype committed; no hardware build/flash/measurement yet.** This adds a companion sketch for XIAO ESP32-S3 and a host recorder. The existing working Grove/Himax VTF1 camera firmware is deliberately unchanged.

## Hardware wiring — actual purple breakout

| LSM6DS3 pad | XIAO ESP32-S3 | GPIO | Function |
|---|---|---:|---|
| 3V3 | 3V3 | — | Regulated supply, verify breakout schematic |
| GND | GND | — | Common ground |
| SCL | D8 | 7 | SPI clock |
| SDA | D10 | 9 | MOSI |
| SA0 | D9 | 8 | MISO |
| CS | D3 | 4 | Chip select |
| INT1 | D0 | 1 | Gyro DRDY hardware capture |
| INT2 | D1 | 2 | Accel DRDY hardware capture |

Do not connect VIN, OCS, SCX or SDX for this test. Verify the breakout's SA0 strapping and 3V3 power topology first. XIAO ESP32-S3 Sense microSD may conflict with D8/D9/D10 pins. D2/GPIO3 was intentionally avoided because it is a JTAG-selection strapping pin; use D0/GPIO1 for INT1.

## Firmware build and run

1. Use Arduino-ESP32 3.x (ESP-IDF 5.x) and select Seeed XIAO ESP32S3 with USB CDC enabled.
2. Open companion/xiao_esp32s3_lsm6ds3_capture/xiao_esp32s3_lsm6ds3_capture.ino.
3. Flash; inspect the boot text for WHO_AM_I=0x69 and a measured capture clock.
4. Record with: python host/imu_capture.py --port COM5 --baud 921600 --seconds 60 --out logs/imu_capture.jsonl
5. Run native protocol tests with: python -m unittest discover -s tests -p test_imu_capture.py

The LSM6DS3 gyro and accelerometer run at 833 Hz; gyro ±1000 degrees/s and accel ±8 g. Each INT pin drives its own GPIO. The ESP32-S3 MCPWM capture timer **latches the edge in hardware**, before the interrupt handler executes. This avoids measuring a delayed ISR entry time. The task reads the matching six SPI register bytes and streams the sample with the captured timestamp. Queued events that have been overtaken by a newer sensor DRDY are discarded rather than paired with unrelated register data.

The ESP32-S3 MCPWM capture timer runs from the APB clock (typically 80 MHz; **12.5 ns ticks**). Its resolution is fixed to the capture source on this target; startup output reports actual configured clock. The 32-bit counter wraps in ~53.7 s at 80 MHz. Host code unwraps successive events assuming each gap is less than half a wrap, flags out-of-order events, and includes cumulative drops.

**12.5 ns timer quantization is NOT 12.5 ns absolute timestamp accuracy.** Pin synchronizer, sensor update latency, IMU filter delay, clock frequency error and camera–IMU clock synchronization dominate actual error. Raw sensor data is still uncalibrated.

## Companion IMU1 serial format

COBS-framed with 0x00 terminator; CRC16/CCITT-FALSE over 23 bytes, then a little-endian CRC:
- magic: ASCII IMU1 (4 bytes)
- kind: 0 for gyro, 1 for accel (uint8)
- seq: per transmitted sample (uint32 LE)
- captured DRDY ticks: MCPWM capture counter (uint32 LE)
- xyz raw measurements: three int16 LE
- cumulative dropped queued/stale events: uint32 LE
- CRC: uint16 LE

Output is a separate acquisition stream. Host receipt time is **not** the sensor event time. There is **no valid camera–IMU clock alignment yet**; do not treat this as a complete VIO solution.

## RP2350 versus STM32F401 versus current ESP32-S3

| Attribute | ESP32-S3 | RP2350 | STM32F401 |
|---|---|---|---|
| Hardware timestamp option | MCPWM capture latch | PIO cycle-counter program (custom) | TIM2/TIM5 32-bit input capture |
| Typical fine clock granularity | 80 MHz APB: 12.5 ns | PIO state-machine instruction-cycle timing | 84 MHz timer clock: ~11.9 ns when configured |
| ISR-independent timestamping | Yes | Yes, with carefully designed PIO | Yes |
| Output buffering | Driver callbacks + queue; DMA work possible | PIO FIFO + DMA | Timer capture DMA possible |
| Processor | Dual Xtensa LX7 | Dual Cortex-M33 or dual RISC-V Hazard3 | Single M4F |
| Advantage | Already wired, has native capture | Programmable sensor timing and sync I/O | Native hardware capture, simple and predictable |
| Limitations | RTOS/wireless interference, sample-read freshness | More PIO epoch/wrap engineering | Less CPU and RAM |

**The F401 DOES have hardware timestamping.** At an external input edge the timer copies its counter to a capture/compare register. It does not need a second core to do this. Configure free-running TIM2, two available input-capture channels on pins suitable for your exact package, and optionally capture-triggered DMA.

**RP2350 PIO can be excellent** for a custom deterministic multi-sensor acquisition protocol. It has 3 PIO blocks of 4 state machines each and DMA FIFOs. However the ordinary RP2350 timer default is 1 MHz, and a PIO state machine does not simply read a shared high-speed timestamp counter. A cycle-counting PIO scheme needs deliberate wrap handling, epoch correlation and verification. For just two DRDY edges, dedicated timer capture on ESP32-S3 or F401 is simpler.

## Next validation gates

1. Build and flash sketch using actual Arduino-ESP32 3.x board core.
2. Check sensor identity, readback, interrupt activity and both ~833 Hz output rates.
3. Record one minute with IMU stationary and rotating; check CRC, monotonic capture times, missing samples and dropped/stale events.
4. Compare DRDY edges, capture times and SPI acquisition timing using a logic analyzer.
5. Measure clock frequency/ppm error against reference oscillator, and correlate with the Grove camera clock using a physical sync signal or calibrated timing offset/drift model.
6. Implement FIFO-based burst recovery if serial or SPI load creates sample loss; never assume queued DRDY events retain old sensor register data.
7. Measure *actual* optical-flow/IMU time-alignment accuracy before claiming better VIO.

References:
- https://github.com/STMicroelectronics/lsm6ds3-pid/blob/master/lsm6ds3_reg.h
- https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-reference/peripherals/mcpwm.html
- https://www.st.com/resource/en/reference_manual/DM00096844.pdf
- https://www.raspberrypi.com/documentation/pico-sdk/hardware.html
- https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
