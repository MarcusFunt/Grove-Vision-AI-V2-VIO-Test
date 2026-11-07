#ifndef VT_TRACKER_H
#define VT_TRACKER_H
#include <stdint.h>
#define VT_W 320
#define VT_H 240
#define VT_MAX_TRACKS 96

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {uint16_t id; uint16_t x; uint16_t y; uint8_t quality; uint8_t age;} vt_track_t;
typedef struct {
    uint8_t previous[VT_W * VT_H];
    vt_track_t tracks[VT_MAX_TRACKS];
    uint16_t count;
    uint16_t next_id;
    uint8_t initialized;
    uint32_t frames;
    uint32_t tracked_ok;
    uint32_t rejected;
} vt_tracker_t;
void vt_init(vt_tracker_t *s);
/* Input: contiguous 320x240 8-bit grayscale, stable throughout call. */
void vt_process(vt_tracker_t *s, const uint8_t *current);

#ifdef __cplusplus
}
#endif
#endif
