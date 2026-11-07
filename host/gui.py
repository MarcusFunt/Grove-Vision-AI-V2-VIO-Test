#!/usr/bin/env python3
"""Grove V2 feature-stream dashboard. USB UART, no VIO/ESKF required.

Dependencies: Python 3.10+, tkinter (system package), pyserial for USB.
Run: python host/gui.py
Also supports an unmistakably simulated demo without hardware.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
import json
import math
from pathlib import Path
import queue
import random
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from metrics import Monitor, StationaryTest
from protocol import CameraImage, Frame, StreamDecoder, Track

ROOT = Path(__file__).resolve().parents[1]
BG = '#111826'
SURFACE = '#192337'
PANEL = '#202c40'
LINE = '#34445d'
TEXT = '#f1f5fa'
MUTED = '#a5b4ca'
CYAN = '#59d5ed'
GREEN = '#63ddb2'
AMBER = '#ffcb76'
RED = '#ff7b88'
DEMO_STATIC = '[DEMO] Stationary synthetic features'
DEMO_MOTION = '[DEMO] Moving synthetic features'
PREVIEW_ON = b'\xa5\x5a\x01'
PREVIEW_OFF = b'\xa5\x5a\x00'
GRAY_COLORS = tuple(f'#{value:02x}{value:02x}{value:02x}' for value in range(256))


def serial_ports():
    try:
        from serial.tools import list_ports
        return [(p.device, p.description) for p in list_ports.comports()]
    except ImportError:
        return []


class SourceWorker(threading.Thread):
    """Only serial I/O and decoding run off the Tk thread."""
    def __init__(self, source, messages, stop, raw_path=None, replay_path=None, command_queue=None):
        super().__init__(daemon=True)
        self.source=source
        self.messages=messages
        self.stop=stop
        self.raw_path=raw_path
        self.replay_path=replay_path
        self.command_queue=command_queue
        self.decoder=StreamDecoder()
        self.last_bad=0

    def _publish(self, raw, received_at, recv_ns):
        for packet in self.decoder.feed(raw):
            if isinstance(packet,CameraImage):
                self.messages.put(('image',packet))
            else:
                self.messages.put(('frame',packet,received_at,recv_ns))
        if self.last_bad != self.decoder.bad:
            self.messages.put(('bad',self.decoder.bad))
            self.last_bad=self.decoder.bad

    def _demo(self):
        rnd=random.Random(72721)
        # Most tracks last, some churn. Absolute coordinates are integer pixels.
        points={i:(rnd.uniform(28,292),rnd.uniform(25,215)) for i in range(75)}
        t0=time.monotonic()
        frame=0
        next_at=t0
        while not self.stop.is_set():
            now=time.monotonic()
            if now<next_at:
                self.stop.wait(next_at-now)
                continue
            next_at += 1/30
            if next_at<now-0.25:
                next_at=now
            moving = self.source==DEMO_MOTION
            dx = 1.9+0.5*math.sin(frame/30) if moving else 0.0
            dy = 0.6*math.cos(frame/17) if moving else 0.0
            obs=[]
            new_points={}
            for id_,(x,y) in points.items():
                nx=x+dx; ny=y+dy
                if nx<15 or nx>305 or ny<15 or ny>225:
                    nx=rnd.uniform(20,300); ny=rnd.uniform(20,220)
                    # Don't publish same ID across an artificial discontinuity.
                    id_ = (1000 + frame*80 + id_) % 60000
                new_points[id_] = (nx,ny)
                if rnd.random()<0.025:
                    continue
                mx=nx+rnd.gauss(0,0.27)
                my=ny+rnd.gauss(0,0.27)
                if rnd.random()<.012:
                    mx+=rnd.choice([-4,4]); my+=rnd.choice([-4,4])
                obs.append(Track(id_,int(round(mx)),int(round(my)),rnd.randint(70,100),min(frame,255)))
            points=new_points
            ticks=int((now-t0)*1000000)
            f=Frame(frame,ticks,5000+frame%13*50,len(obs),0,1,tuple(obs))
            self.messages.put(('frame',f,now,time.time_ns()))
            frame+=1
        self.messages.put(('done',None))

    def _replay(self):
        data=self.replay_path.read_bytes()
        d=StreamDecoder()
        frames=d.feed(data)
        if not frames:
            raise RuntimeError('No valid VTF1 or VTI1 packets in the selected raw file.')
        for packet in frames:
            if self.stop.wait(1/30):break
            if isinstance(packet,CameraImage):
                self.messages.put(('image',packet))
            else:
                self.messages.put(('frame',packet,time.monotonic(),time.time_ns()))
        self.messages.put(('done',None))

    def _serial(self):
        try:
            import serial
        except ImportError as exc:
            raise RuntimeError('pyserial is not installed. Run: python -m pip install pyserial') from exc
        # Capture *all* bytes, not only valid packets, for later investigation.
        with serial.Serial(self.source, 921600, timeout=0.15) as port:
            with self.raw_path.open('wb') as rawfile:
                while not self.stop.is_set() or (self.command_queue and not self.command_queue.empty()):
                    if self.command_queue:
                        while True:
                            try:command=self.command_queue.get_nowait()
                            except queue.Empty:break
                            port.write(command)
                            port.flush()
                    if self.stop.is_set():break
                    data=port.read(4096)
                    if not data:continue
                    now=time.monotonic()
                    recv_ns=time.time_ns()
                    rawfile.write(data)
                    self._publish(data,now,recv_ns)
        self.messages.put(('done',None))

    def run(self):
        try:
            if self.source in (DEMO_STATIC,DEMO_MOTION):
                self._demo()
            elif self.replay_path:
                self._replay()
            else:
                self._serial()
        except Exception as exc:
            self.messages.put(('error',str(exc)))


class Dashboard:
    def __init__(self,root):
        self.root=root
        self.root.title('Grove V2  /  Visual Track Lab')
        self.root.geometry('1190x810')
        self.root.minsize(930,650)
        self.root.configure(bg=BG)
        self.monitor=Monitor()
        self.queue=queue.Queue()
        self.stop=None
        self.worker=None
        self.source_name='None'
        self.session_dir=None
        self.logfile=None
        self.stationary=None
        self.stationary_result=None
        self.last_frame_wall=None
        self.ports={}
        self.source_kind=None
        self.command_queue=None
        self.preview_enabled=False
        self.preview_window=None
        self.preview_canvas=None
        self.preview_photo=None
        self.preview_status_var=None
        self._init_style()
        self._build()
        self.refresh_ports()
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(50,self._poll)

    def _init_style(self):
        st=ttk.Style()
        st.theme_use('clam')
        st.configure('.',font=('Segoe UI',10),background=BG,foreground=TEXT)
        st.configure('TFrame',background=BG)
        st.configure('Panel.TFrame',background=SURFACE)
        st.configure('TLabel',background=BG,foreground=TEXT)
        st.configure('Muted.TLabel',background=BG,foreground=MUTED)
        st.configure('Panel.TLabel',background=SURFACE,foreground=TEXT)
        st.configure('PanelMuted.TLabel',background=SURFACE,foreground=MUTED)
        st.configure('TButton',background=PANEL,foreground=TEXT,bordercolor=LINE,focuscolor=LINE,padding=(11,7))
        st.map('TButton',background=[('active','#344762'),('pressed','#263850')])
        st.configure('TCombobox',fieldbackground='#263248',background=PANEL,foreground=TEXT,
                     arrowcolor=CYAN,insertcolor=TEXT)
        st.map('TCombobox',fieldbackground=[('readonly','#263248')],foreground=[('readonly',TEXT)])
        st.configure('Horizontal.TProgressbar',background=GREEN,troughcolor=LINE)

    def _build(self):
        main=ttk.Frame(self.root,padding=16)
        main.pack(fill='both',expand=True)
        tk.Label(main,text='VISUAL TRACK LAB',bg=BG,fg=TEXT,font=('Segoe UI',20,'bold')).pack(anchor='w')
        tk.Label(main,text='USB feature-stream diagnostics  •  live 2D tracks, repeatability, motion scatter and packet health',
                 bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',pady=(0,13))

        toolbar=ttk.Frame(main)
        toolbar.pack(fill='x',pady=(0,10))
        ttk.Label(toolbar,text='Source').pack(side='left',padx=(0,7))
        self.port_var=tk.StringVar()
        self.combo=ttk.Combobox(toolbar,textvariable=self.port_var,width=38)
        self.combo.pack(side='left',padx=(0,6))
        ttk.Button(toolbar,text='Refresh',command=self.refresh_ports).pack(side='left',padx=3)
        self.connect_button=ttk.Button(toolbar,text='Connect',command=self.toggle_connection)
        self.connect_button.pack(side='left',padx=3)
        ttk.Button(toolbar,text='Replay .bin',command=self.replay_raw).pack(side='left',padx=3)
        self.preview_button=ttk.Button(toolbar,text='Show B/W footage',command=self.toggle_camera_preview,state='disabled')
        self.preview_button.pack(side='left',padx=3)
        ttk.Button(toolbar,text='Export report',command=self.export_report).pack(side='right',padx=3)

        self.banner_var=tk.StringVar(value='Select a USB serial port (or demo) and click Connect.')
        tk.Label(main,textvariable=self.banner_var,bg='#26344b',fg=CYAN,anchor='w',padx=12,pady=8).pack(fill='x',pady=(0,10))

        body=ttk.Frame(main)
        body.pack(fill='both',expand=True)
        body.columnconfigure(0,weight=2,uniform='body')
        body.columnconfigure(1,weight=1,uniform='body')
        body.rowconfigure(0,weight=1)
        left=ttk.Frame(body,style='Panel.TFrame',padding=10)
        right=ttk.Frame(body,style='Panel.TFrame',padding=12)
        left.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        right.grid(row=0,column=1,sticky='nsew')

        tk.Label(left,text='Feature map  •  320 × 240 px',font=('Segoe UI',11,'bold'),bg=SURFACE,fg=TEXT,anchor='w').pack(fill='x')
        tk.Label(left,text='Colored dots are tracked positions; short lines are changes since the previous frame. Not camera video.',
                 bg=SURFACE,fg=MUTED,anchor='w',font=('Segoe UI',9),wraplength=610,justify='left').pack(fill='x',pady=(0,6))
        self.feature_canvas=tk.Canvas(left,bg='#0e1624',highlightthickness=0,borderwidth=0)
        self.feature_canvas.pack(fill='both',expand=True)
        self.feature_canvas.bind('<Configure>',lambda _:self._draw_map())

        tk.Label(right,text='LIVE DIAGNOSTICS',font=('Segoe UI',12,'bold'),bg=SURFACE,fg=TEXT,anchor='w').pack(fill='x',pady=(0,10))
        self.metric_vars={}
        fields=[('features','Active tracks'),('matched','Matched IDs'),('retention','Retention vs previous'),
                ('flow','Common motion'),('scatter','Motion scatter'),('agreement','Track agreement'),('coverage','Image coverage'),
                ('rate','Observed host rate'),('timing','Device frame interval'),
                ('drops','Sequence gaps / CRC')]
        for key,label in fields:
            line=ttk.Frame(right,style='Panel.TFrame')
            line.pack(fill='x',pady=2)
            tk.Label(line,text=label,bg=SURFACE,fg=MUTED,font=('Segoe UI',9)).pack(side='left')
            var=tk.StringVar(value='—')
            tk.Label(line,textvariable=var,bg=SURFACE,fg=TEXT,font=('Consolas',10,'bold')).pack(side='right')
            self.metric_vars[key]=var
        tk.Frame(right,bg=LINE,height=1).pack(fill='x',pady=11)
        tk.Label(right,text='STATIONARY REPEATABILITY TEST',bg=SURFACE,fg=TEXT,font=('Segoe UI',10,'bold')).pack(anchor='w')
        tk.Label(right,text='Keep the camera rigidly fixed. Test measures image-coordinate jitter; no physical ground truth is assumed.',
                 bg=SURFACE,fg=MUTED,wraplength=330,justify='left',font=('Segoe UI',9)).pack(anchor='w',pady=(3,8))
        self.test_btn=ttk.Button(right,text='Start 15 s stationary test',command=self.toggle_stationary)
        self.test_btn.pack(fill='x')
        self.progress=ttk.Progressbar(right,mode='determinate',maximum=100)
        self.progress.pack(fill='x',pady=8)
        self.result_var=tk.StringVar(value='No stationary test recorded yet.')
        tk.Label(right,textvariable=self.result_var,bg=SURFACE,fg=GREEN,wraplength=330,justify='left',font=('Segoe UI',10)).pack(anchor='w')
        tk.Label(right,text='A low scatter value alone does NOT prove optical-flow accuracy; many tracks can agree on the wrong motion.',
                 bg=SURFACE,fg=AMBER,wraplength=330,justify='left',font=('Segoe UI',8)).pack(side='bottom',anchor='w',pady=(7,0))

        graphs=ttk.Frame(main)
        graphs.pack(fill='x',pady=(10,0))
        graphs.columnconfigure(0,weight=1)
        graphs.columnconfigure(1,weight=1)
        self.count_graph=tk.Canvas(graphs,bg=SURFACE,height=125,highlightthickness=0)
        self.flow_graph=tk.Canvas(graphs,bg=SURFACE,height=125,highlightthickness=0)
        self.count_graph.grid(row=0,column=0,sticky='ew',padx=(0,6))
        self.flow_graph.grid(row=0,column=1,sticky='ew',padx=(6,0))
        self.count_graph.bind('<Configure>',lambda _:self._draw_graphs())
        self.flow_graph.bind('<Configure>',lambda _:self._draw_graphs())

        self.footer_var=tk.StringVar(value='No measurements yet. USB serial requires the custom VTF1 firmware, not stock detection firmware.')
        tk.Label(main,textvariable=self.footer_var,bg=BG,fg=MUTED,font=('Segoe UI',9),anchor='w',wraplength=1140,justify='left').pack(fill='x',pady=(9,0))

    def refresh_ports(self):
        selected=self.port_var.get()
        ports=serial_ports()
        self.ports={f'{p}  —  {desc}':p for p,desc in ports}
        options=list(self.ports)+[DEMO_STATIC,DEMO_MOTION]
        self.combo.configure(values=options)
        if selected and (selected in options or selected.startswith('/') or selected.upper().startswith('COM')):
            self.port_var.set(selected)
        elif ports:
            self.port_var.set(next(iter(self.ports)))
        else:
            self.port_var.set(DEMO_STATIC)
        if not ports and self.worker is None:
            self.banner_var.set('No USB ports detected. Demo works without hardware. For USB install pyserial and check the device connection.')

    def _new_session(self,source,replay_path=None):
        if self.worker and self.worker.is_alive():
            return
        self.monitor.reset()
        self.stationary=None
        self.stationary_result=None
        self.result_var.set('No stationary test recorded yet.')
        self.progress['value']=0
        self.test_btn.configure(text='Start 15 s stationary test')
        self.source_name=source if not replay_path else f'REPLAY: {replay_path.name}'
        self.queue=queue.Queue()
        self.stop=threading.Event()
        safe='demo' if source in (DEMO_STATIC,DEMO_MOTION) else 'replay' if replay_path else 'usb'
        self.source_kind=safe
        self.preview_enabled=False
        self._close_preview_window()
        self.preview_button.configure(text='Show B/W footage',state='disabled' if safe=='demo' else 'normal')
        self.command_queue=queue.Queue() if safe=='usb' else None
        self.session_dir=ROOT/'logs'/('gui_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+safe)
        try:
            self.session_dir.mkdir(parents=True,exist_ok=False)
            self.logfile=(self.session_dir/'frames.jsonl').open('w',encoding='utf-8',buffering=1)
        except OSError as exc:
            messagebox.showerror('Cannot record session',str(exc))
            return
        raw_path=self.session_dir/'serial_raw.bin' if safe=='usb' else None
        self.worker=SourceWorker(source,self.queue,self.stop,raw_path=raw_path,replay_path=replay_path,
                                 command_queue=self.command_queue)
        self.worker.start()
        self.last_frame_wall=time.monotonic()
        self.connect_button.configure(text='Disconnect')
        self.banner_var.set(('DEMO ONLY — synthetic tracks, not hardware evidence.' if safe=='demo' else
                             'REPLAY — data from file, not a live USB measurement.' if safe=='replay' else
                             'LIVE USB — capturing feature packets and raw serial data.') + f'   Logs: {self.session_dir.name}')
        self.footer_var.set('Session data are automatically saved in '+str(self.session_dir))

    def toggle_connection(self):
        if self.worker is not None:
            self.disconnect()
            return
        choice=self.port_var.get().strip()
        if not choice:
            messagebox.showinfo('Select source','Choose a serial device or demo mode.')
            return
        source=self.ports.get(choice,choice)
        self._new_session(source)

    def replay_raw(self):
        if self.worker is not None:
            self.disconnect()
        path=filedialog.askopenfilename(title='Replay captured VTF1 raw serial file',filetypes=[('Raw serial packets','*.bin'),('All files','*.*')])
        if path:
            self._new_session('REPLAY',Path(path))

    def disconnect(self):
        if self.stationary is not None:
            self._finish_stationary()
        if self.preview_enabled and self.source_kind=='usb' and self.command_queue:
            self.command_queue.put(PREVIEW_OFF)
        self.preview_enabled=False
        self._close_preview_window()
        if self.stop is not None:
            self.stop.set()
        self.worker=None
        self.stop=None
        if self.logfile:
            self.logfile.flush()
            self.logfile.close()
            self.logfile=None
        self.stationary=None
        self.connect_button.configure(text='Connect')
        self.test_btn.configure(text='Start 15 s stationary test')
        self.preview_button.configure(text='Show B/W footage',state='disabled')
        self.banner_var.set(f'Disconnected. {self.monitor.frames} received frames. Logs: {self.session_dir}')

    def toggle_stationary(self):
        if self.stationary is not None:
            self._finish_stationary()
        else:
            if self.worker is None:
                messagebox.showinfo('Not connected','Connect to a USB device or a demo source first.')
                return
            self.stationary=StationaryTest(seconds=15)
            self.stationary.sequence_gaps_at_start=self.monitor.sequence_gaps
            self.stationary.crc_at_start=self.monitor.crc_errors
            self.stationary_result=None
            self.test_btn.configure(text='Finish stationary test early')
            self.progress['value']=0
            self.result_var.set('Collecting... Keep camera fixed for 15 seconds.')

    def _finish_stationary(self):
        if self.stationary is None:return
        result=self.stationary.results()
        result['source']=self.source_name
        result['test_sequence_gaps']=self.monitor.sequence_gaps-self.stationary.sequence_gaps_at_start
        result['test_crc_errors']=self.monitor.crc_errors-self.stationary.crc_at_start
        self.stationary_result=result
        self.stationary=None
        self.test_btn.configure(text='Start 15 s stationary test')
        self.progress['value']=100
        rms=result['median_feature_rms_px']
        if rms is None:
            self.result_var.set('Insufficient persistent feature IDs. Try better lighting/texture and repeat.')
        else:
            label='DEMO ONLY · ' if 'DEMO' in self.source_name else ''
            self.result_var.set(f"{label}{result['frames']} frames, {result['qualifying_feature_ids']} persistent IDs\n"
                                f"Median pixel jitter: {rms:.2f} px RMS\n"
                                f"P95 jitter: {result['p95_feature_rms_px']:.2f} px RMS\n"
                                f"Median flow scatter: {result['median_flow_scatter_px']:.2f} px" if result['median_flow_scatter_px'] is not None else
                                f'{label}Median pixel jitter: {rms:.2f} px RMS')
        if self.session_dir:
            try:
                (self.session_dir/'stationary_test.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            except OSError:pass

    def toggle_camera_preview(self):
        if self.preview_enabled:
            if self.source_kind=='usb' and self.command_queue:
                self.command_queue.put(PREVIEW_OFF)
            self.preview_enabled=False
            self.preview_button.configure(text='Show B/W footage')
            self._close_preview_window()
            return
        if self.worker is None:
            messagebox.showinfo('Not connected','Connect to the Grove camera or replay a recording made with preview enabled.')
            return
        if self.source_kind=='demo':
            messagebox.showinfo('No camera image','The demo only generates synthetic feature tracks; it has no camera footage.')
            return
        self.preview_enabled=True
        self._open_preview_window()
        self.preview_button.configure(text='Hide B/W footage')
        if self.source_kind=='usb' and self.command_queue:
            self.command_queue.put(PREVIEW_ON)
            self.preview_status_var.set('Requesting live 160×120 grayscale frames. UART preview lowers tracking rate.')
        else:
            self.preview_status_var.set('Replay: waiting for recorded camera-image packets. Older captures contain tracks only.')

    def _open_preview_window(self):
        if self.preview_window and self.preview_window.winfo_exists():
            self.preview_window.lift()
            return
        self.preview_window=tk.Toplevel(self.root)
        self.preview_window.title('Grove V2 · Black and white camera')
        self.preview_window.geometry('720x570')
        self.preview_window.configure(bg=BG)
        tk.Label(self.preview_window,text='LIVE CAMERA · GRAYSCALE',bg=BG,fg=TEXT,
                 font=('Segoe UI',13,'bold')).pack(anchor='w',padx=16,pady=(14,3))
        tk.Label(self.preview_window,text='160×120 area-downsampled preview · transmitted every second tracking frame',
                 bg=BG,fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=16)
        self.preview_status_var=tk.StringVar(value='Waiting for a camera image...')
        tk.Label(self.preview_window,textvariable=self.preview_status_var,bg=BG,fg=CYAN,
                 font=('Segoe UI',9),anchor='w').pack(fill='x',padx=16,pady=(5,8))
        self.preview_canvas=tk.Canvas(self.preview_window,width=640,height=480,bg='#05080d',
                                      highlightthickness=1,highlightbackground=LINE)
        self.preview_canvas.pack(padx=16,pady=(0,14))
        self.preview_window.protocol('WM_DELETE_WINDOW',self.toggle_camera_preview)

    def _close_preview_window(self):
        if self.preview_window:
            try:
                if self.preview_window.winfo_exists():self.preview_window.destroy()
            except tk.TclError:pass
        self.preview_window=None
        self.preview_canvas=None
        self.preview_photo=None
        self.preview_status_var=None

    def _render_camera_image(self,image):
        if not self.preview_enabled or not self.preview_window or not self.preview_canvas:
            return
        try:
            photo=tk.PhotoImage(width=image.width,height=image.height)
            rows=[]
            for y in range(image.height):
                start=y*image.width
                rows.append('{'+ ' '.join(GRAY_COLORS[value]
                                           for value in image.pixels[start:start+image.width]) +'}')
            photo.put(' '.join(rows),to=(0,0))
            scale=max(1,min(4,640//image.width,480//image.height))
            if scale>1:photo=photo.zoom(scale,scale)
            self.preview_photo=photo
            self.preview_canvas.delete('all')
            self.preview_canvas.create_image(320,240,image=photo,anchor='center')
            if self.preview_status_var:
                self.preview_status_var.set(f'Live camera frame {image.sequence} · {image.width}×{image.height} grayscale')
        except (tk.TclError,ValueError) as exc:
            if self.preview_status_var:self.preview_status_var.set(f'Could not render camera frame: {exc}')

    def _poll(self):
        try:
            processed=0
            while processed<350:
                try: msg=self.queue.get_nowait()
                except queue.Empty:break
                processed+=1
                kind=msg[0]
                if kind=='frame':
                    f,at,ns=msg[1:]
                    metrics=self.monitor.update(f,at)
                    self.last_frame_wall=time.monotonic()
                    if self.logfile:
                        try:
                            self.logfile.write(json.dumps({
                                'seq':f.sequence,'recv_ns':ns,
                                'frame_ready_ticks':f.frame_ready_ticks,'process_ticks':f.process_ticks,
                                'tracked_ok':f.tracked_ok,'rejected':f.rejected,
                                'timestamp_kind':'frame_ready_unscaled_ticks_not_exposure',
                                'tracks':[[t.id,t.x,t.y,t.quality,t.age] for t in f.features]},separators=(',',':'))+'\n')
                        except OSError as exc:self.footer_var.set('Log write error: '+str(exc))
                    if self.stationary:self.stationary.observe(f,metrics)
                elif kind=='bad':self.monitor.crc_errors=msg[1]
                elif kind=='image':self._render_camera_image(msg[1])
                elif kind=='error':
                    self.banner_var.set('Connection error: '+msg[1])
                    self.disconnect()
                    self.banner_var.set('Connection error: '+msg[1])
                elif kind=='done':
                    if self.worker is not None:
                        self.disconnect()
                    self.footer_var.set('Source finished. Export the summary or replay another recording.')
            if self.stationary is not None:
                pct=100*min(1,max(0,(time.monotonic()-self.stationary.started_at)/self.stationary.seconds))
                self.progress['value']=pct
                if pct>=100:self._finish_stationary()
            if self.worker is not None and self.last_frame_wall is not None and time.monotonic()-self.last_frame_wall>2.5:
                self.footer_var.set('No valid VTF1 packets for >2.5 s. Check custom firmware, USB port, 921600 baud, cable and other serial readers.')
            self._render()
        finally:
            self.root.after(60,self._poll)

    @staticmethod
    def _fmt(v,unit='',digits=1):
        return '—' if v is None else f'{v:.{digits}f}{unit}'

    def _render(self):
        m=self.monitor.last_metrics
        if m:
            self.metric_vars['features'].set(str(m['n']))
            self.metric_vars['matched'].set(str(m['matched']))
            self.metric_vars['retention'].set(self._fmt(m['retention']*100 if m['retention'] is not None else None,'%'))
            self.metric_vars['flow'].set('—' if m['flow_x'] is None else f"({m['flow_x']:+.1f}, {m['flow_y']:+.1f}) px")
            self.metric_vars['scatter'].set(self._fmt(m['scatter_px'],' px',2))
            scatter=m['scatter_px']
            agreement=('TOO FEW TRACKS' if m['matched']<8 else
                       'LOW SCATTER' if scatter is not None and scatter<=1.0 else
                       'MODERATE' if scatter is not None and scatter<=2.0 else
                       'HIGH SCATTER')
            self.metric_vars['agreement'].set(agreement)
            self.metric_vars['coverage'].set(self._fmt(m['coverage']*100,'%',0))
            self.metric_vars['rate'].set(self._fmt(m['fps_host'],' fps')+'*')
            self.metric_vars['timing'].set('—' if m['device_interval_ticks'] is None else f"{m['device_interval_ticks']:,} ticks")
            self.metric_vars['drops'].set(f"{self.monitor.sequence_gaps} / {self.monitor.crc_errors}")
        self._draw_map()
        self._draw_graphs()

    def _draw_map(self):
        c=self.feature_canvas
        w,h=c.winfo_width(),c.winfo_height()
        if w<10 or h<10:return
        c.delete('all')
        pad=22
        scale=min((w-2*pad)/320,(h-2*pad)/240)
        ox=(w-320*scale)/2;oy=(h-240*scale)/2
        c.create_rectangle(ox,oy,ox+320*scale,oy+240*scale,fill='#0d192a',outline=LINE)
        for i in range(1,4):
            x=ox+i*80*scale
            y=oy+i*60*scale
            c.create_line(x,oy,x,oy+240*scale,fill='#26374d',dash=(2,5))
            c.create_line(ox,y,ox+320*scale,y,fill='#26374d',dash=(2,5))
        if self.monitor.latest is None:
            c.create_text(w/2,h/2,text='Connect to display feature tracks',fill=MUTED,font=('Segoe UI',12))
            return
        for id_,p in self.monitor.latest_points.items():
            x=ox+p.x*scale;y=oy+p.y*scale
            bad=p.matched and p.residual>2.5
            color=RED if bad else CYAN if p.matched else AMBER
            if p.matched and (p.dx!=0 or p.dy!=0):
                # Display motion over one frame; enlarge a little for legibility.
                factor=2.0
                px=x-p.dx*scale*factor;py=y-p.dy*scale*factor
                c.create_line(px,py,x,y,fill=color,width=1.6,arrow='last',arrowshape=(5,6,2))
            radius=2.4 if p.matched else 3.3
            c.create_oval(x-radius,y-radius,x+radius,y+radius,fill=color,outline='')
            if id_%19==0:
                c.create_text(x+6,y-8,text=str(id_),font=('Consolas',8),anchor='w',fill=MUTED)
        c.create_text(ox+8,oy+8,anchor='nw',text=f'{len(self.monitor.latest_points)} tracks',fill=TEXT,font=('Consolas',10))
        c.create_text(ox+8,oy+240*scale-6,anchor='sw',text='Cyan = matched · amber = new · red = inconsistent flow',fill=MUTED,font=('Segoe UI',9))

    def _plot(self,c,title,series):
        w=c.winfo_width();h=c.winfo_height()
        if w<50:return
        c.delete('all')
        c.create_text(15,10,text=title,fill=TEXT,font=('Segoe UI',10,'bold'),anchor='nw')
        x0,x1=30,w-16;y0,y1=38,h-18
        for row in range(3):
            y=y0+(y1-y0)*row/2
            c.create_line(x0,y,x1,y,fill=LINE,dash=(2,5))
        finite=[float(v) for _,vals in series for v in vals if v is not None]
        top=max([1]+finite)*1.08
        c.create_text(27,y0,text=f'{top:.1f}',fill=MUTED,font=('Consolas',8),anchor='e')
        c.create_text(27,y1,text='0',fill=MUTED,font=('Consolas',8),anchor='e')
        for color,values in series:
            values=list(values)[-200:]
            if len(values)<2:continue
            coords=[]
            for i,v in enumerate(values):
                if v is None:continue
                x=x0+(x1-x0)*i/max(1,len(values)-1)
                y=y1-(y1-y0)*max(0,v)/top
                coords.extend((x,y))
            if len(coords)>=4:c.create_line(*coords,fill=color,width=2,smooth=False)

    def _draw_graphs(self):
        h=list(self.monitor.history)[-200:]
        self._plot(self.count_graph,'Feature count (cyan)  ·  matched IDs (green)',[
            (CYAN,[r['n'] for r in h]),(GREEN,[r['matched'] for r in h])])
        self._plot(self.flow_graph,'Frame motion (cyan)  ·  motion scatter (orange)  [px]',[
            (CYAN,[r['flow_px'] for r in h]),(AMBER,[r['scatter_px'] for r in h])])

    def export_report(self):
        if self.monitor.frames==0:
            messagebox.showinfo('No data','Connect and receive some packets before exporting.')
            return
        path=filedialog.asksaveasfilename(title='Export session summary',defaultextension='.json',
                                           initialfile='grove_tracking_summary.json',filetypes=[('JSON report','*.json')])
        if not path:return
        data=dict(source=self.source_name,recorded=datetime.now().isoformat(timespec='seconds'),
                  session_log_dir=str(self.session_dir),monitor=self.monitor.summary(),
                  stationary_test=self.stationary_result)
        try:
            Path(path).write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
            self.footer_var.set('Saved report: '+path)
        except OSError as exc:
            messagebox.showerror('Cannot save',str(exc))

    def close(self):
        self.disconnect()
        self.root.destroy()


def main():
    ap=argparse.ArgumentParser(description='USB GUI for Grove Vision AI V2 VTF1 feature-stream experiment')
    ap.add_argument('--demo',choices=['static','motion'],help='Start synthetic demonstration immediately')
    ap.add_argument('--port',help='Select a serial port (e.g., COM5 or /dev/ttyACM0)')
    ap.add_argument('--replay',type=Path,help='Replay a saved serial_raw.bin file')
    args=ap.parse_args()
    root=tk.Tk()
    app=Dashboard(root)
    if args.port:
        app.port_var.set(args.port)
        root.after(200,app.toggle_connection)
    elif args.demo:
        app.port_var.set(DEMO_STATIC if args.demo=='static' else DEMO_MOTION)
        root.after(200,app.toggle_connection)
    elif args.replay:
        root.after(200,lambda:app._new_session('REPLAY',args.replay))
    root.mainloop()

if __name__=='__main__':main()
