/* Experimental replacement for the upstream hello_world_cmsis_cv cvapp file.
 * Camera setup and frame-ready events remain in the unmodified upstream
 * hello_world_cmsis_cv.c. Do not call this production firmware.
 */
#include <stdint.h>
#include <string.h>
#include "WE2_device.h"
#include "board.h"
#include "WE2_core.h"
#include "hx_drv_uart.h"
#include "cisdp_sensor.h"
#include "cvapp_hello_world_cmsis_cv.h"
#include "vt_tracker.h"
#include "vt_packet.h"

static vt_tracker_t tracker;
static uint8_t packet[VT_PACKET_CAPACITY];
static uint8_t preview_packet[VT_PREVIEW_PACKET_CAPACITY];
static uint32_t seqno=0;
static DEV_UART *serial_port=0;
static uint8_t preview_enabled=0;
static uint8_t preview_divider=0;
static uint8_t preview_command_state=0;

static void poll_preview_command(void) {
    if(!serial_port)return;
    char incoming[16];
    int32_t count=serial_port->uart_read_nonblock(incoming,sizeof(incoming));
    if(count<=0)return;
    if(count>(int32_t)sizeof(incoming))count=(int32_t)sizeof(incoming);
    for(int32_t i=0;i<count;i++) {
        uint8_t value=(uint8_t)incoming[i];
        if(preview_command_state==0) {
            if(value==0xa5)preview_command_state=1;
        } else if(preview_command_state==1) {
            preview_command_state=(value==0x5a)?2:(value==0xa5?1:0);
        } else {
            if(value==1) {
                preview_enabled=1;
                preview_divider=0;
            } else if(value==0) {
                preview_enabled=0;
                preview_divider=0;
            }
            preview_command_state=0;
        }
    }
}

static void uart_write_all(const uint8_t *data,size_t length) {
    if(!serial_port)return;
    for(size_t pos=0;pos<length;) {
        size_t chunk=(length-pos<8)?length-pos:8;
        int32_t written=serial_port->uart_write(data+pos,(uint32_t)chunk);
        if(written<=0||(size_t)written>chunk)break;
        pos+=(size_t)written;
    }
}

/* Upstream examples use SystemGetTick with a 24-bit downcounter plus wrap count.
 * This is a FRAME-READY APPROXIMATION. It is NOT an exposure timestamp.
 * The tick frequency must be calibrated on actual board. */
static uint64_t get_ticks(void) {
    uint32_t down=0,loops=0;
    SystemGetTick(&down,&loops);
    return (((uint64_t)loops)<<24)+(uint64_t)(0xffffffu-(down&0xffffffu));
}
extern "C" void cv_hello_world_cmsis_cv_init() {
    vt_init(&tracker);
    /* SDK console is configured on UART 0; use its public enum directly. */
    serial_port=hx_drv_uart_get_dev(USE_DW_UART_0);
    serial_port->uart_open(UART_BAUDRATE_921600);
}
extern "C" int cv_hello_world_cmsis_cv_run() {
    poll_preview_command();
    uint64_t ready=get_ticks();
    const uint8_t *image=(const uint8_t *)app_get_raw_addr();
    vt_process(&tracker,image);
    uint64_t done=get_ticks();
    uint64_t delta=done>=ready?done-ready:0;
    uint32_t elapsed=delta>0xffffffffu?0xffffffffu:(uint32_t)delta;
    uint32_t current_seq=seqno++;
    size_t n=vt_make_packet(packet,sizeof(packet),&tracker,current_seq,ready,elapsed);
    if(n)uart_write_all(packet,n);
    if(preview_enabled) {
        if(++preview_divider>=2) {
            preview_divider=0;
            size_t preview_size=vt_make_preview_packet(preview_packet,sizeof(preview_packet),image,current_seq);
            if(preview_size)uart_write_all(preview_packet,preview_size);
        }
    }
    /* Capture is rearmed only after processing/transmission; this baseline
     * intentionally measures resulting frame-rate ceiling. */
    sensordplib_retrigger_capture();
    return 0;
}
