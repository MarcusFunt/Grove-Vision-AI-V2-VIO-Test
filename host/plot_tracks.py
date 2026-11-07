#!/usr/bin/env python3
"""Plot 2D feature tracks in pixel space from recorded JSONL; no pose claims."""
import argparse,json
from collections import defaultdict
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('log',type=Path)
    p.add_argument('--out',type=Path,default=Path('tracks.png'))
    p.add_argument('--min-length',type=int,default=4)
    args=p.parse_args()
    import matplotlib.pyplot as plt
    paths=defaultdict(list)
    for line in args.log.read_text().splitlines():
        row=json.loads(line)
        for tid,x,y,q,age in row['tracks']:paths[tid].append((x,y))
    fig,ax=plt.subplots(figsize=(9,6))
    drawn=0
    for tid,points in paths.items():
        if len(points)<args.min_length:continue
        xs,ys=zip(*points)
        ax.plot(xs,ys,linewidth=.8,alpha=.5)
        drawn+=1
    ax.set_xlim(0,320);ax.set_ylim(240,0);ax.set_aspect('equal')
    ax.set_xlabel('x (image pixels)');ax.set_ylabel('y (image pixels)')
    ax.set_title(f'Sparse image tracks: {drawn} track IDs (not trajectory or VIO pose)')
    fig.tight_layout();fig.savefig(args.out,dpi=180)
    print('Wrote',args.out)
if __name__=='__main__':main()
