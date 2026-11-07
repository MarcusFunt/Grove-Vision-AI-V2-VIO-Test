#include "vt_tracker.h"
#include <string.h>
#include <limits.h>

/* Deliberately simple baseline: FAST-like corner detection and SAD patch
 * search with forward/backward check. Not a production pyramidal KLT.
 * All coordinates are integer pixels. No dynamic allocation. */
#define BORDER 9
#define SEARCH 6
#define RAD 2
#define GRID_X 16
#define GRID_Y 12
#define PATCH_N ((2*RAD+1)*(2*RAD+1))
#define MAX_AVERAGE_SAD 29
#define MIN_DIST2 64
static const int8_t ringx[16]={0,1,2,3,3,3,2,1,0,-1,-2,-3,-3,-3,-2,-1};
static const int8_t ringy[16]={-3,-3,-2,-1,0,1,2,3,3,3,2,1,0,-1,-2,-3};

static int corner_score(const uint8_t *im,int x,int y) {
    int center=im[y*VT_W+x]; int diff[16];
    for(int i=0;i<16;i++)diff[i]=im[(y+ringy[i])*VT_W+x+ringx[i]]-center;
    int best=0;
    for(int start=0;start<16;start++) {
        int bright=0,dark=0; int total_b=0,total_d=0;
        for(int k=0;k<9;k++) {
            int d=diff[(start+k)&15];
            if(d>20){bright++;total_b+=d-20;}
            if(d< -20){dark++;total_d+=-d-20;}
        }
        if(bright==9 && total_b>best)best=total_b;
        if(dark==9 && total_d>best)best=total_d;
    }
    return best;
}
static int sad(const uint8_t *a,const uint8_t *b,int ax,int ay,int bx,int by){
    int sum=0;
    for(int dy=-RAD;dy<=RAD;dy++) {
        int ia=(ay+dy)*VT_W+ax-RAD;
        int ib=(by+dy)*VT_W+bx-RAD;
        for(int dx=0;dx<2*RAD+1;dx++) {
            int d=(int)a[ia+dx]-(int)b[ib+dx];
            sum+=d<0?-d:d;
        }
    }
    return sum;
}
static int search(const uint8_t *from,const uint8_t *to,int x,int y,int *bx,int *by,int *cost){
    int best=INT_MAX, rx=0, ry=0;
    for(int dy=-SEARCH;dy<=SEARCH;dy++) {
        int ty=y+dy; if(ty<BORDER || ty>=VT_H-BORDER)continue;
        for(int dx=-SEARCH;dx<=SEARCH;dx++) {
            int tx=x+dx; if(tx<BORDER || tx>=VT_W-BORDER)continue;
            int e=sad(from,to,x,y,tx,ty);
            if(e<best){best=e;rx=tx;ry=ty;}
        }
    }
    if(best==INT_MAX)return 0;
    *bx=rx;*by=ry;*cost=best;
    return 1;
}
static int close_to_existing(const vt_tracker_t *s,int x,int y) {
    for(int k=0;k<s->count;k++) {
        int dx=x-(int)s->tracks[k].x;
        int dy=y-(int)s->tracks[k].y;
        if(dx*dx+dy*dy<MIN_DIST2)return 1;
    }
    return 0;
}
static void redetect(vt_tracker_t *s,const uint8_t *img) {
    const int tile_w=VT_W/GRID_X,tile_h=VT_H/GRID_Y;
    for(int gy=0;gy<GRID_Y && s->count<VT_MAX_TRACKS;gy++) {
        for(int gx=0;gx<GRID_X && s->count<VT_MAX_TRACKS;gx++) {
            int best=0,bx=0,by=0;
            int x0=gx*tile_w, y0=gy*tile_h;
            for(int y=y0+3;y<y0+tile_h-2;y+=2) {
                if(y<BORDER||y>=VT_H-BORDER)continue;
                for(int x=x0+3;x<x0+tile_w-2;x+=2) {
                    if(x<BORDER||x>=VT_W-BORDER)continue;
                    int score=corner_score(img,x,y);
                    if(score>best){best=score;bx=x;by=y;}
                }
            }
            if(best<70||close_to_existing(s,bx,by))continue;
            vt_track_t *t=&s->tracks[s->count++];
            t->id=++s->next_id; if(t->id==0)t->id=++s->next_id;
            t->x=(uint16_t)bx;t->y=(uint16_t)by;
            t->quality=(uint8_t)(best/8>255?255:best/8); t->age=1;
        }
    }
}
void vt_init(vt_tracker_t *s){ memset(s,0,sizeof(*s)); }
void vt_process(vt_tracker_t *s,const uint8_t *current) {
    if(!s->initialized){
        redetect(s,current);memcpy(s->previous,current,VT_W*VT_H);
        s->initialized=1; s->frames++;return;
    }
    uint16_t valid=0; s->tracked_ok=0; s->rejected=0;
    for(uint16_t i=0;i<s->count;i++) {
        vt_track_t t=s->tracks[i];
        int nx,ny,cost,backx,backy,backcost;
        if(!search(s->previous,current,t.x,t.y,&nx,&ny,&cost) ||
           cost > MAX_AVERAGE_SAD*PATCH_N ||
           !search(current,s->previous,nx,ny,&backx,&backy,&backcost) ||
           (backx-(int)t.x)*(backx-(int)t.x)+(backy-(int)t.y)*(backy-(int)t.y)>2) {
            s->rejected++;continue;
        }
        t.x=(uint16_t)nx; t.y=(uint16_t)ny;
        t.quality=(uint8_t)(255-(cost/PATCH_N>255?255:cost/PATCH_N));
        if(t.age<255)t.age++;
        s->tracks[valid++]=t; s->tracked_ok++;
    }
    s->count=valid;
    if(s->count<VT_MAX_TRACKS)redetect(s,current);
    memcpy(s->previous,current,VT_W*VT_H);
    s->frames++;
}
