#!/usr/bin/env python3
"""Evaluate real capture logs. Captured tick rate must be measured externally."""
import argparse, json, math, statistics
from collections import defaultdict
from pathlib import Path

def pct(xs,p):
    if not xs:return None
    a=sorted(xs)
    return a[min(len(a)-1,round((len(a)-1)*p))]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('log',type=Path)
    ap.add_argument('--tick-hz',type=float,help='Calibrated SystemGetTick frequency; do not guess')
    ap.add_argument('--json',type=Path,help='Save metrics as JSON')
    a=ap.parse_args()
    records=[json.loads(s) for s in a.log.read_text().splitlines() if s.strip()]
    if len(records)<2:raise SystemExit('Need two or more frames')
    samples=records
    n=[len(r['tracks']) for r in samples]
    ids=defaultdict(int)
    for r in samples:
        for t in r['tracks']:ids[t[0]]+=1
    recv_intervals=[(b['recv_ns']-a['recv_ns'])/1e9 for a,b in zip(samples,samples[1:])
                    if b['recv_ns']>a['recv_ns']]
    ticks=[b['frame_ready_ticks']-a['frame_ready_ticks'] for a,b in zip(samples,samples[1:])
           if b['frame_ready_ticks']>a['frame_ready_ticks']]
    process_ticks=[r['process_ticks'] for r in samples]
    recv_elapsed=(samples[-1]['recv_ns']-samples[0]['recv_ns'])/1e9
    metrics={'frames':len(samples), 'mean_feature_count':statistics.mean(n),
       'min_feature_count':min(n),'median_feature_count':statistics.median(n),
       'median_track_lifetime_frames_observed':statistics.median(ids.values()),
       'track_lifetime_p90_frames_observed':pct(list(ids.values()),.90),
       'median_tracked_survivors':statistics.median(r['tracked_ok'] for r in samples),
       'median_rejected':statistics.median(r['rejected'] for r in samples),
       'host_arrival_fps':(len(samples)-1)/recv_elapsed if recv_elapsed>0 else None,
       'median_host_arrival_interval_ms':1000*statistics.median(recv_intervals) if recv_intervals else None,
       'mean_host_arrival_interval_ms':1000*statistics.mean(recv_intervals) if recv_intervals else None,
       'p95_host_arrival_interval_ms':1000*pct(recv_intervals,.95) if recv_intervals else None,
       'median_device_interval_ticks':statistics.median(ticks) if ticks else None,
       'mean_device_interval_ticks':statistics.mean(ticks) if ticks else None,
       'p95_device_interval_ticks':pct(ticks,.95) if ticks else None,
       'device_interval_cv_pct':100*statistics.pstdev(ticks)/statistics.mean(ticks) if ticks else None,
       'timestamp_caveat':'Frame-ready ticks are not calibrated exposure timestamps. Host receive times contain serial buffering jitter.'}
    if a.tick_hz:
        metrics['approx_device_fps_from_ready_ticks']=a.tick_hz*len(ticks)/sum(ticks) if ticks else None
        metrics['median_tracker_compute_ms']=1000*statistics.median(process_ticks)/a.tick_hz
        metrics['mean_tracker_compute_ms']=1000*statistics.mean(process_ticks)/a.tick_hz
        metrics['p95_tracker_compute_ms']=1000*pct(process_ticks,.95)/a.tick_hz
        metrics['p99_tracker_compute_ms']=1000*pct(process_ticks,.99)/a.tick_hz
        metrics['max_tracker_compute_ms']=1000*max(process_ticks)/a.tick_hz
    print(json.dumps(metrics,indent=2))
    if a.json:a.json.write_text(json.dumps(metrics,indent=2)+'\n')

if __name__=='__main__':main()
