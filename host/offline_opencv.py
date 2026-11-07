#!/usr/bin/env python3
"""Desktop OpenCV reference on a real video/camera, not firmware performance.
Benchmark sparse pyramidal KLT independently so board tracking can be compared.
"""
import argparse, time, statistics
import cv2
import numpy as np

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('source',help='Video file path, or integer webcam index')
    ap.add_argument('--max-frames',type=int,default=600)
    ap.add_argument('--display',action='store_true')
    a=ap.parse_args()
    cap=cv2.VideoCapture(int(a.source) if a.source.isdigit() else a.source)
    if not cap.isOpened():raise SystemExit('Could not open source')
    prev=None; points=None;track_count=[];timings=[];frames=0
    try:
        while frames<a.max_frames:
            ret,frame=cap.read()
            if not ret:break
            im=cv2.cvtColor(cv2.resize(frame,(320,240)),cv2.COLOR_BGR2GRAY)
            t0=time.perf_counter_ns()
            if prev is None or points is None or len(points)<30:
                points=cv2.goodFeaturesToTrack(im,maxCorners=96,qualityLevel=.025,minDistance=8)
            else:
                nxt,st,err=cv2.calcOpticalFlowPyrLK(prev,im,points,None,
                            winSize=(15,15),maxLevel=2,
                            criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,25,.01))
                points=nxt[st.reshape(-1)!=0].reshape(-1,1,2) if nxt is not None else None
            track_count.append(len(points) if points is not None else 0)
            timings.append((time.perf_counter_ns()-t0)/1e6)
            if a.display:
                show=frame.copy();h,w=show.shape[:2]
                if points is not None:
                    for pt in points.reshape(-1,2):cv2.circle(show,(int(pt[0]*w/320),int(pt[1]*h/240)),3,(0,255,0),-1)
                cv2.imshow('Desktop reference (not Grove)',show)
                if cv2.waitKey(1)&255==27:break
            prev=im;frames+=1
    finally:cap.release();cv2.destroyAllWindows()
    print({'frames':frames,'median_track_count':statistics.median(track_count) if frames else 0,
           'median_desktop_processing_ms':statistics.median(timings) if frames else None,
           'note':'Desktop OpenCV performance cannot predict MCU performance.'})

if __name__=='__main__':main()
