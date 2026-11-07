#include "vt_tracker.h"
#include "vt_packet.h"
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
/* Deterministic synthetic image translated by +2, +1 pixels. */
static vt_tracker_t s;
static uint8_t img0[VT_W*VT_H],img1[VT_W*VT_H];
static uint8_t buf[VT_PACKET_CAPACITY];
static unsigned x=1234567;
static uint8_t rnd(void){x^=x<<13;x^=x>>17;x^=x<<5;return (uint8_t)(x>>15);}
int main(void) {
    for(size_t i=0;i<sizeof(img0);i++)img0[i]=rnd();
    memset(img1,127,sizeof(img1));
    for(int y=1;y<VT_H;y++)for(int xx=2;xx<VT_W;xx++)img1[y*VT_W+xx]=img0[(y-1)*VT_W+xx-2];
    vt_init(&s);vt_process(&s,img0);
    if(s.count<20){fprintf(stderr,"Too few initial FAST features: %d\n",s.count);return 1;}
    vt_track_t old[VT_MAX_TRACKS];int n=s.count;memcpy(old,s.tracks,sizeof(old));
    vt_process(&s,img1);int matched=0,correct=0;
    for(int i=0;i<s.count;i++)for(int j=0;j<n;j++)if(s.tracks[i].id==old[j].id){
        matched++;
        if((int)s.tracks[i].x-(int)old[j].x==2 && (int)s.tracks[i].y-(int)old[j].y==1)correct++;
    }
    if(matched<15||correct<matched*8/10){
        fprintf(stderr,"Tracking failure: initial=%d matched=%d correct=%d\n",n,matched,correct);return 2;
    }
    size_t count=vt_make_packet(buf,sizeof(buf),&s,20,123456789,2233);
    if(count<50||buf[0]!=0||buf[count-1]!=0){fprintf(stderr,"packet error\n");return 3;}
    FILE *f=fopen("tests/sample_stream.bin","wb");
    if(!f){perror("sample_stream");return 4;}
    fputs("boot log text\n",f);
    fwrite(buf,1,count,f);fwrite(buf,1,count,f);
    fclose(f);
    printf("PASS native: initial=%d matched=%d correct=%d frame_packet=%zu bytes\n",n,matched,correct,count);
    return 0;
}
