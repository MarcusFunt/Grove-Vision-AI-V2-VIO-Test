#ifndef VT_PACKET_H
#define VT_PACKET_H
#include "vt_tracker.h"
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
/* COBS-delimited binary packet: 0x00 + COBS(payload+CRC16) + 0x00.
 * raw VTF1 packet, little endian:
 * magic[4], version u8, timestamp_kind u8, n u16, seq u32,
 * frame_ready_ticks u64, processing_ticks u32, tracked_ok u16,
 * rejected u16, {id u16,x u16,y u16,quality u8,age u8}[n], crc16 u16
 * timestamp_kind=1: frame-ready time in SYSTEM TICKS, NOT exposure time. */
#define VT_PACKET_CAPACITY 1024
#define VT_PREVIEW_WIDTH (VT_W / 2)
#define VT_PREVIEW_HEIGHT (VT_H / 2)
#define VT_PREVIEW_PIXELS (VT_PREVIEW_WIDTH * VT_PREVIEW_HEIGHT)
#define VT_PREVIEW_RAW_SIZE (17U + VT_PREVIEW_PIXELS + 2U)
#define VT_PREVIEW_PACKET_CAPACITY (VT_PREVIEW_RAW_SIZE + VT_PREVIEW_RAW_SIZE / 254U + 4U)
size_t vt_make_packet(uint8_t *out,size_t capacity,const vt_tracker_t *s,
                      uint32_t seq,uint64_t ready_ticks,uint32_t processing_ticks);
/* VTI1 COBS-framed grayscale preview, area-downsampled to half resolution. */
size_t vt_make_preview_packet(uint8_t *out,size_t capacity,const uint8_t *image,
                              uint32_t seq);
#ifdef __cplusplus
}
#endif
#endif
