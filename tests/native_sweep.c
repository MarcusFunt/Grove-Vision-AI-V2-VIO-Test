#include "vt_tracker.h"
#include <stdint.h>
#include <stdio.h>
#include <string.h>
static vt_tracker_t t;
static uint8_t base[VT_W*VT_H],moved[VT_W*VT_H];
static uint32_t rng=0x712387a;
static uint8_t next_random(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (uint8_t)(rng>>12);}
int main(void){
  for(size_t i=0;i<sizeof(base);i++)base[i]=next_random();
  puts("dx_px,dy_px,initial_tracks,tracked_ids,correct_displacement,correct_fraction");
  const int dxs[]={0,1,2,4,6,8,12};
  for(unsigned j=0;j<sizeof(dxs)/sizeof(dxs[0]);j++){
    int dx=dxs[j],dy=j==0?0:1;
    memset(moved,128,sizeof(moved));
    for(int y=dy;y<VT_H;y++)for(int x=dx;x<VT_W;x++)moved[y*VT_W+x]=base[(y-dy)*VT_W+(x-dx)];
    vt_init(&t);vt_process(&t,base);
    vt_track_t old[VT_MAX_TRACKS];uint16_t old_count=t.count;
    memcpy(old,t.tracks,sizeof(old));
    vt_process(&t,moved);
    int matched=0,correct=0;
    for(uint16_t k=0;k<t.count;k++)for(uint16_t l=0;l<old_count;l++)if(t.tracks[k].id==old[l].id){
      matched++;
      if((int)t.tracks[k].x-(int)old[l].x==dx &&
         (int)t.tracks[k].y-(int)old[l].y==dy)correct++;
    }
    printf("%d,%d,%u,%d,%d,%.3f\n",dx,dy,old_count,matched,correct,
           matched?((double)correct)/matched:0.);
  }
  return 0;
}
