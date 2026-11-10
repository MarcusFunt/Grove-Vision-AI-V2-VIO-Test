/*
 * LSM6DS3 four-wire SPI + hardware-captured INT1/INT2.
 * Board: Seeed XIAO ESP32-S3, Arduino-ESP32 3.x (ESP-IDF 5.x).
 *
 * Experimental firmware. Not flight-qualified; no common camera clock yet.
 * The MCPWM capture peripheral latches edge time BEFORE the callback runs.
 */
#include <Arduino.h>
#include <SPI.h>
#include <cstring>
#include "driver/mcpwm_cap.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "esp_err.h"

namespace {
constexpr int PIN_SCK = 7;       // XIAO D8
constexpr int PIN_MISO = 8;      // XIAO D9 -> breakout SA0
constexpr int PIN_MOSI = 9;      // XIAO D10 -> breakout SDA
constexpr int PIN_CS = 4;        // XIAO D3
constexpr int PIN_GYRO_DRDY = 3; // XIAO D2 -> INT1
constexpr int PIN_ACC_DRDY = 2;  // XIAO D1 -> INT2
constexpr uint32_t SPI_HZ = 4000000;
constexpr uint8_t WHO_AM_I = 0x0F;
constexpr uint8_t CTRL1_XL = 0x10;
constexpr uint8_t CTRL2_G = 0x11;
constexpr uint8_t CTRL3_C = 0x12;
constexpr uint8_t CTRL4_C = 0x13;
constexpr uint8_t INT1_CTRL = 0x0D;
constexpr uint8_t INT2_CTRL = 0x0E;
constexpr uint8_t OUTX_L_G = 0x22;
constexpr uint8_t OUTX_L_XL = 0x28;
constexpr size_t PAYLOAD_SIZE = 25; // magic(4),kind(1),seq(4),ticks(4),xyz(6),drops(4),crc(2)

struct Edge {
  uint32_t ticks;
  uint8_t kind; // 0=gyro on INT1, 1=accel on INT2
};
QueueHandle_t edge_queue = nullptr;
mcpwm_cap_timer_handle_t cap_timer = nullptr;
mcpwm_cap_channel_handle_t cap_gyro = nullptr, cap_acc = nullptr;
uint8_t channel_ids[2] = {0, 1};
volatile uint32_t missed_edge_queue = 0;
uint32_t sequence = 0;

uint8_t spiRead(uint8_t addr) {
  SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE3));
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(addr | 0x80u);
  const uint8_t value = SPI.transfer(0xFF);
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();
  return value;
}
void spiWrite(uint8_t addr, uint8_t value) {
  SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE3));
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(addr & 0x7Fu);
  SPI.transfer(value);
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();
}
void readAxes(uint8_t start, int16_t axes[3]) {
  SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE3));
  digitalWrite(PIN_CS, LOW);
  SPI.transfer(start | 0x80u);
  uint8_t b[6];
  for (uint8_t &v : b) v = SPI.transfer(0xFF);
  digitalWrite(PIN_CS, HIGH);
  SPI.endTransaction();
  for (int i = 0; i != 3; ++i) {
    axes[i] = static_cast<int16_t>(static_cast<uint16_t>(b[i*2]) |
                                   (static_cast<uint16_t>(b[i*2+1]) << 8));
  }
}

bool IRAM_ATTR onCapture(mcpwm_cap_channel_handle_t,
                         const mcpwm_capture_event_data_t *e, void *context) {
  Edge ev = {e->cap_value, *static_cast<uint8_t *>(context)};
  BaseType_t woken = pdFALSE;
  if (xQueueSendFromISR(edge_queue, &ev, &woken) != pdTRUE) {
    ++missed_edge_queue;
  }
  return woken == pdTRUE;
}

void add16(uint8_t *p, size_t pos, uint16_t v) {
  p[pos] = static_cast<uint8_t>(v);
  p[pos+1] = static_cast<uint8_t>(v >> 8);
}
void add32(uint8_t *p, size_t pos, uint32_t v) {
  for (int k=0;k<4;k++) p[pos+k] = static_cast<uint8_t>(v >> (8*k));
}
uint16_t crc16(const uint8_t *p, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i=0;i<len;i++) {
    crc ^= static_cast<uint16_t>(p[i]) << 8;
    for (int b=0;b<8;b++) crc = (crc & 0x8000u) ? (crc << 1) ^ 0x1021u : crc << 1;
  }
  return crc;
}
size_t cobsEncode(const uint8_t *src, size_t len, uint8_t *dst) {
  size_t write = 1, code_pos = 0;
  uint8_t code = 1;
  for (size_t i=0;i<len;i++) {
    if (src[i]==0) {
      dst[code_pos] = code;
      code_pos = write++;
      code = 1;
    } else {
      dst[write++] = src[i];
      if (++code==0xFF) {
        dst[code_pos] = code;
        code_pos = write++;
        code = 1;
      }
    }
  }
  dst[code_pos] = code;
  dst[write++] = 0;
  return write;
}
void sendSample(const Edge &e, const int16_t xyz[3]) {
  uint8_t p[PAYLOAD_SIZE] = {'I','M','U','1'};
  p[4] = e.kind;
  add32(p, 5, sequence++);
  add32(p, 9, e.ticks);
  for (size_t i=0;i<3;i++) add16(p, 13+i*2, static_cast<uint16_t>(xyz[i]));
  add32(p, 19, missed_edge_queue);
  add16(p, 23, crc16(p, 23));
  uint8_t packet[PAYLOAD_SIZE + 4];
  const size_t bytes = cobsEncode(p, sizeof(p), packet);
  Serial.write(packet, bytes); // Never inside the capture ISR.
}
void initCapture() {
  edge_queue = xQueueCreate(64, sizeof(Edge));
  if (!edge_queue) { Serial.println("ERROR: queue allocation"); abort(); }

  mcpwm_capture_timer_config_t timer_cfg = {};
  timer_cfg.group_id = 0;
  timer_cfg.clk_src = MCPWM_CAPTURE_CLK_SRC_DEFAULT;
  timer_cfg.resolution_hz = 0; // ESP32-S3 always uses APB capture clock.
  ESP_ERROR_CHECK(mcpwm_new_capture_timer(&timer_cfg, &cap_timer));

  mcpwm_capture_channel_config_t cfg = {};
  cfg.prescale = 1;
  cfg.flags.pos_edge = true;
  cfg.flags.neg_edge = false;
  cfg.gpio_num = PIN_GYRO_DRDY;
  ESP_ERROR_CHECK(mcpwm_new_capture_channel(cap_timer, &cfg, &cap_gyro));
  cfg.gpio_num = PIN_ACC_DRDY;
  ESP_ERROR_CHECK(mcpwm_new_capture_channel(cap_timer, &cfg, &cap_acc));

  mcpwm_capture_event_callbacks_t callbacks = {};
  callbacks.on_cap = onCapture;
  ESP_ERROR_CHECK(mcpwm_capture_channel_register_event_callbacks(cap_gyro, &callbacks, &channel_ids[0]));
  ESP_ERROR_CHECK(mcpwm_capture_channel_register_event_callbacks(cap_acc, &callbacks, &channel_ids[1]));

  ESP_ERROR_CHECK(mcpwm_capture_timer_enable(cap_timer));
  ESP_ERROR_CHECK(mcpwm_capture_channel_enable(cap_gyro));
  ESP_ERROR_CHECK(mcpwm_capture_channel_enable(cap_acc));
  ESP_ERROR_CHECK(mcpwm_capture_timer_start(cap_timer));

  uint32_t resolution = 0;
  ESP_ERROR_CHECK(mcpwm_capture_timer_get_resolution(cap_timer, &resolution));
  Serial.printf("# capture_clock_hz=%lu; 32-bit counter wraps; not camera-synchronized\n",
                static_cast<unsigned long>(resolution));
}
bool initSensor() {
  const uint8_t id = spiRead(WHO_AM_I);
  if (id != 0x69) {
    Serial.printf("# ERROR WHO_AM_I=0x%02x (expected 0x69)\n", id);
    return false;
  }
  // Block-data-update + auto-increment + four-wire SPI. Disable secondary I2C interface.
  spiWrite(CTRL3_C, 0x44);
  spiWrite(CTRL4_C, 0x04);
  // 833 Hz gyro, ±1000 dps; 833 Hz accelerometer, ±8 g.
  spiWrite(CTRL1_XL, 0x7C);
  spiWrite(CTRL2_G, 0x78);
  // Independent active-high push-pull DRDY: INT1=gyro, INT2=accel.
  spiWrite(INT1_CTRL, 0x02);
  spiWrite(INT2_CTRL, 0x01);
  const bool ok = spiRead(CTRL3_C)==0x44 && spiRead(CTRL1_XL)==0x7C &&
                  spiRead(CTRL2_G)==0x78 && spiRead(INT1_CTRL)==0x02 &&
                  spiRead(INT2_CTRL)==0x01;
  Serial.printf("# LSM6DS3=%s; gyro=833Hz +/-1000dps; accel=833Hz +/-8g\n",
                ok ? "configured" : "register verification failed");
  return ok;
}
}  // namespace

void setup() {
  Serial.begin(921600);
  delay(500);
  pinMode(PIN_CS, OUTPUT);
  digitalWrite(PIN_CS, HIGH);
  SPI.begin(PIN_SCK, PIN_MISO, PIN_MOSI, PIN_CS);
  // Sensor output defaults to push-pull active high. No internal pulls needed.
  initCapture();
  if (!initSensor()) {
    while (true) delay(1000);
  }
}

void loop() {
  Edge e;
  if (xQueueReceive(edge_queue, &e, pdMS_TO_TICKS(1000)) == pdTRUE) {
    int16_t xyz[3];
    readAxes(e.kind==0 ? OUTX_L_G : OUTX_L_XL, xyz);
    sendSample(e, xyz);
  }
}
