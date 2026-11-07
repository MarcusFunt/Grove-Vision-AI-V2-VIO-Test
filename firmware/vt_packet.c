#include "vt_packet.h"
#include <string.h>
#define RAW_MAX 900
static uint8_t preview_raw[VT_PREVIEW_RAW_SIZE];
static uint16_t crc16(const uint8_t *p,size_t n) {
    uint16_t crc=0xffff;
    for(size_t i=0;i<n;i++) {
        crc^=(uint16_t)p[i]<<8;
        for(int b=0;b<8;b++)crc=(crc&0x8000)?(uint16_t)((crc<<1)^0x1021):(uint16_t)(crc<<1);
    }
    return crc;
}
static void u16(uint8_t *b,size_t *n,uint16_t v){b[(*n)++]=(uint8_t)v;b[(*n)++]=(uint8_t)(v>>8);}
static void u32(uint8_t *b,size_t *n,uint32_t v){for(int i=0;i<4;i++)b[(*n)++]=(uint8_t)(v>>(8*i));}
static void u64(uint8_t *b,size_t *n,uint64_t v){for(int i=0;i<8;i++)b[(*n)++]=(uint8_t)(v>>(8*i));}
static size_t cobs(uint8_t *dst,size_t max,const uint8_t *src,size_t n) {
    if(max<2)return 0;
    size_t code_index=0,write=1;uint8_t code=1;
    for(size_t i=0;i<n;i++) {
        if(src[i]==0) {
            dst[code_index]=code;
            if(write>=max)return 0;
            code_index=write++;code=1;
        } else {
            if(write>=max)return 0;
            dst[write++]=src[i];code++;
            if(code==0xff) {
                dst[code_index]=code;
                if(write>=max)return 0;
                code_index=write++;code=1;
            }
        }
    }
    dst[code_index]=code;
    return write;
}
size_t vt_make_packet(uint8_t *out,size_t capacity,const vt_tracker_t *s,
                      uint32_t seq,uint64_t ready_ticks,uint32_t processing_ticks) {
    uint8_t raw[RAW_MAX];size_t n=0;
    if(!out||!s||s->count>VT_MAX_TRACKS||capacity<VT_PACKET_CAPACITY)return 0;
    memcpy(raw,"VTF1",4);n=4;
    raw[n++]=1;raw[n++]=1;
    u16(raw,&n,s->count);u32(raw,&n,seq);u64(raw,&n,ready_ticks);
    u32(raw,&n,processing_ticks);u16(raw,&n,(uint16_t)s->tracked_ok);
    u16(raw,&n,(uint16_t)s->rejected);
    for(uint16_t i=0;i<s->count;i++) {
        const vt_track_t *t=&s->tracks[i];
        u16(raw,&n,t->id);u16(raw,&n,t->x);u16(raw,&n,t->y);
        raw[n++]=t->quality;raw[n++]=t->age;
    }
    if(n+2>RAW_MAX)return 0;
    u16(raw,&n,crc16(raw,n));
    out[0]=0;
    size_t len=cobs(out+1,capacity-2,raw,n);
    if(!len)return 0;
    out[len+1]=0;
    return len+2;
}

size_t vt_make_preview_packet(uint8_t *out,size_t capacity,const uint8_t *image,
                              uint32_t seq) {
    if(!out||!image||capacity<VT_PREVIEW_PACKET_CAPACITY)return 0;
    size_t n=0;
    memcpy(preview_raw,"VTI1",4);n=4;
    preview_raw[n++]=1;
    u16(preview_raw,&n,VT_PREVIEW_WIDTH);
    u16(preview_raw,&n,VT_PREVIEW_HEIGHT);
    u32(preview_raw,&n,seq);
    u32(preview_raw,&n,VT_PREVIEW_PIXELS);
    for(uint16_t y=0;y<VT_PREVIEW_HEIGHT;y++) {
        const uint8_t *row0=image+(size_t)(2U*y)*VT_W;
        const uint8_t *row1=row0+VT_W;
        for(uint16_t x=0;x<VT_PREVIEW_WIDTH;x++) {
            size_t sx=(size_t)2U*x;
            uint16_t sum=(uint16_t)row0[sx]+row0[sx+1U]+row1[sx]+row1[sx+1U];
            preview_raw[n++]=(uint8_t)((sum+2U)/4U);
        }
    }
    u16(preview_raw,&n,crc16(preview_raw,n));
    out[0]=0;
    size_t len=cobs(out+1,capacity-2,preview_raw,n);
    if(!len)return 0;
    out[len+1]=0;
    return len+2;
}
