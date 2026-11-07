"""Sensor-independent monitoring of VTF1 feature-track streams.

All values in pixel coordinates / raw ticks. Do NOT interpret as 3D motion,
calibrated camera latency, camera pose, or absolute tracking accuracy.
"""
from __future__ import annotations

from collections import deque, defaultdict
from dataclasses import dataclass
import math
import statistics
import time
from typing import Optional


def median(values):
    return statistics.median(values) if values else None


def percentile(values, p):
    if not values:
        return None
    sorted_values = sorted(values)
    index = (len(sorted_values)-1)*p
    lo = math.floor(index)
    hi = math.ceil(index)
    return sorted_values[lo]*(hi-index) + sorted_values[hi]*(index-lo) if lo != hi else sorted_values[lo]


@dataclass
class LivePoint:
    x: int
    y: int
    dx: float = 0.0
    dy: float = 0.0
    residual: float = 0.0
    quality: int = 0
    age: int = 0
    matched: bool = False


class Monitor:
    def __init__(self):
        self.reset()

    def reset(self):
        self.previous = None
        self.previous_at = None
        self.latest = None
        self.latest_points = {}
        self.frames = 0
        self.crc_errors = 0
        self.sequence_gaps = 0
        self.sequence_resets = 0
        self.first_at = None
        self.last_at = None
        self.history = deque(maxlen=600)
        self.frame_intervals = deque(maxlen=240)
        self.device_tick_intervals = deque(maxlen=240)
        self.last_metrics = {}

    def update(self, frame, received_at=None):
        if received_at is None:
            received_at = time.monotonic()
        previous = self.previous
        elapsed = (received_at-self.previous_at) if self.previous_at is not None else None
        if elapsed is not None and elapsed > 0:
            self.frame_intervals.append(elapsed)
        if previous is not None:
            gap = (frame.sequence-previous.sequence-1) & 0xffffffff
            if gap < 100000:
                self.sequence_gaps += gap
            elif frame.sequence != previous.sequence:
                self.sequence_resets += 1
            tick_delta = frame.frame_ready_ticks-previous.frame_ready_ticks
            if tick_delta > 0:
                self.device_tick_intervals.append(tick_delta)
        if self.first_at is None:
            self.first_at = received_at
        self.last_at = received_at
        self.frames += 1
        old = {t.id:t for t in previous.features} if previous is not None else {}
        current = {t.id:t for t in frame.features}
        matched_ids = [id_ for id_ in current if id_ in old]
        dxs = [current[k].x-old[k].x for k in matched_ids]
        dys = [current[k].y-old[k].y for k in matched_ids]
        dx, dy = median(dxs), median(dys)
        residuals = [math.hypot(a-dx,b-dy) for a,b in zip(dxs,dys)] if dx is not None else []
        step_motions = [math.hypot(a,b) for a,b in zip(dxs,dys)]
        cell_count = len({(min(t.x//80,3), min(t.y//60,3)) for t in frame.features if t.x>=0 and t.y>=0})
        points = {}
        for t in frame.features:
            if t.id in old and dx is not None:
                a=t.x-old[t.id].x; b=t.y-old[t.id].y
                points[t.id] = LivePoint(t.x,t.y,a,b,math.hypot(a-dx,b-dy),t.quality,t.age,True)
            else:
                points[t.id] = LivePoint(t.x,t.y,quality=t.quality,age=t.age)
        # This is *observed packet* FPS, based on HOST chunk receive times,
        # and may be distorted by buffering and packet batching.
        recent = list(self.history)[-89:]
        fps = (len(recent)/(received_at-recent[0]['t'])) if recent and received_at>recent[0]['t'] else None
        metrics = dict(t=received_at, n=len(frame.features), matched=len(matched_ids),
                       retention=(len(matched_ids)/max(len(old),1)) if previous else None,
                       flow_x=dx,flow_y=dy,flow_px=math.hypot(dx,dy) if dx is not None else None,
                       scatter_px=median(residuals),p95_residual_px=percentile(residuals,.95),
                       step_px=median(step_motions),quality=median([t.quality for t in frame.features]),
                       coverage=cell_count/16,device_interval_ticks=self.device_tick_intervals[-1] if self.device_tick_intervals else None,
                       fps_host=fps, seq=frame.sequence, process_ticks=frame.process_ticks)
        self.latest = frame
        self.latest_points = points
        self.last_metrics = metrics
        self.previous = frame
        self.previous_at = received_at
        self.history.append(metrics)
        return metrics

    def summary(self):
        samples = list(self.history)
        m = self.last_metrics
        return dict(source_warning='Feature consistency only; no image ground truth or absolute VIO accuracy.',
                    timestamp_warning='Device ticks not calibrated; host receive times suffer USB/serial buffering.',
                    frames=self.frames,crc_errors=self.crc_errors,sequence_gaps=self.sequence_gaps,
                    sequence_resets=self.sequence_resets,
                    host_observed_fps=m.get('fps_host'),
                    median_features=median([v['n'] for v in samples]),
                    median_matches=median([v['matched'] for v in samples]),
                    median_retention=median([v['retention'] for v in samples if v['retention'] is not None]),
                    median_flow_dispersion_px=median([v['scatter_px'] for v in samples if v['scatter_px'] is not None]),
                    p95_flow_dispersion_px=percentile([v['scatter_px'] for v in samples if v['scatter_px'] is not None],.95),
                    median_device_interval_ticks=median(list(self.device_tick_intervals)),
                    median_host_chunk_interval_ms=1000*median(list(self.frame_intervals)) if self.frame_intervals else None)


class StationaryTest:
    """User-declared *stationary* experiment. No automatic motion inference.

    During genuine camera motion, 'jitter' is not a sensor-accuracy metric.
    """
    def __init__(self, seconds=15.0, started_at=None):
        self.seconds=float(seconds)
        self.started_at=time.monotonic() if started_at is None else started_at
        self.frames=0
        self.tracks=defaultdict(list)
        self.flows=[]
        self.scatters=[]
        self.matches=[]
        self.feature_counts=[]
        self.step_motions=[]
        self.sequence_gaps_at_start=None
        self.crc_at_start=None

    def observe(self, frame, metrics):
        self.frames += 1
        for t in frame.features:
            self.tracks[t.id].append((t.x,t.y))
        if metrics['flow_px'] is not None:
            self.flows.append(metrics['flow_px'])
        if metrics['scatter_px'] is not None:
            self.scatters.append(metrics['scatter_px'])
        if metrics['step_px'] is not None:
            self.step_motions.append(metrics['step_px'])
        self.matches.append(metrics['matched'])
        self.feature_counts.append(metrics['n'])

    def results(self, min_track_frames=5):
        rms=[]
        drifts=[]
        for pts in self.tracks.values():
            if len(pts)<min_track_frames:
                continue
            mx=statistics.mean(p[0] for p in pts)
            my=statistics.mean(p[1] for p in pts)
            rms.append(math.sqrt(statistics.mean((x-mx)**2+(y-my)**2 for x,y in pts)))
            drifts.append(math.hypot(pts[-1][0]-pts[0][0],pts[-1][1]-pts[0][1]))
        return dict(duration_requested_s=self.seconds,frames=self.frames,
                    qualifying_feature_ids=len(rms),
                    median_feature_rms_px=median(rms),
                    p95_feature_rms_px=percentile(rms,.95),
                    median_first_last_shift_px=median(drifts),
                    median_frame_step_px=median(self.step_motions),
                    p95_frame_step_px=percentile(self.step_motions,.95),
                    median_common_motion_px=median(self.flows),
                    median_flow_scatter_px=median(self.scatters),
                    median_feature_count=median(self.feature_counts),
                    median_matched_features=median(self.matches),
                    interpretation='Pixel repeatability during a user-declared stationary test, NOT calibrated absolute tracking accuracy.')
