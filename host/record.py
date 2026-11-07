#!/usr/bin/env python3
"""Record UART packets to JSONL and print live tracking diagnostics.

Examples:
  python host/record.py --port /dev/ttyACM0 --seconds 60 --out logs/test.jsonl
  python host/record.py --input tests/sample_stream.bin --out logs/replay.jsonl

pyserial is required only for --port.
"""
import argparse
import json
import os
import pathlib
import sys
import time
from protocol import PacketDecoder

def main():
    p=argparse.ArgumentParser()
    s=p.add_mutually_exclusive_group(required=True)
    s.add_argument('--port',help='Serial port')
    s.add_argument('--input',type=pathlib.Path,help='Previously recorded raw serial bytes')
    p.add_argument('--baud',type=int,default=921600)
    p.add_argument('--seconds',type=float,default=60)
    p.add_argument('--out',type=pathlib.Path,default=pathlib.Path('tracking.jsonl'))
    p.add_argument('--raw-out',type=pathlib.Path,help='Save raw serial stream (recommended)')
    args=p.parse_args()
    args.out.parent.mkdir(parents=True,exist_ok=True)
    if args.raw_out: args.raw_out.parent.mkdir(parents=True,exist_ok=True)
    decoder=PacketDecoder()
    last=None
    dropped=0
    first_at=None
    good=0
    with args.out.open('w') as output:
        with (args.raw_out.open('wb') if args.raw_out else open(os.devnull,'wb')) as rawout:
            if args.port:
                try: import serial
                except ImportError:
                    print('Install pyserial: pip install pyserial',file=sys.stderr);return 2
                stream=serial.Serial(args.port,args.baud,timeout=.2)
            else:
                stream=args.input.open('rb')
            with stream:
                start=time.monotonic()
                last_print=start
                while True:
                    if not args.input and time.monotonic()-start>=args.seconds:break
                    data=stream.read(4096 if args.input else 512)
                    if not data:
                        if args.input:break
                        continue
                    rawout.write(data)
                    # Host times are reception times and NOT camera exposure times.
                    recv_ns=time.time_ns()
                    for f in decoder.feed(data):
                        if last is not None:
                            gap=(f.sequence-last-1)&0xffffffff
                            if gap < 100000:dropped+=gap
                        last=f.sequence
                        if first_at is None:first_at=time.monotonic()
                        good+=1
                        output.write(json.dumps({'seq':f.sequence,'recv_ns':recv_ns,
                           'frame_ready_ticks':f.frame_ready_ticks,'process_ticks':f.process_ticks,
                           'tracked_ok':f.tracked_ok,'rejected':f.rejected,
                           'timestamp_kind':'frame_ready_unscaled_ticks_not_exposure',
                           'tracks':[[t.id,t.x,t.y,t.quality,t.age] for t in f.features]},
                           separators=(',',':'))+'\n')
                    if time.monotonic()-last_print>2:
                        now=time.monotonic()
                        rate=good/max(now-first_at,1e-6) if first_at else 0
                        print(f'valid={good} corrupt={decoder.bad} seq_gaps={dropped} '
                              f'approx_live_fps={rate:.1f}')
                        last_print=now
    print(f'Finished: {good} frames, {decoder.bad} malformed/noise packets, {dropped} sequence gaps')
    return 0 if good else 1

if __name__=='__main__':raise SystemExit(main())
