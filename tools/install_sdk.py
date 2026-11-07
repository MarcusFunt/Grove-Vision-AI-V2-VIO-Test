#!/usr/bin/env python3
"""Copy experiment into the verified Himax hello_world_cmsis_cv scenario.
Requires a separate recursive clone of vendor repo. Creates a .original backup.
Does not flash hardware.
"""
import argparse, pathlib, shutil
import re
ROOT=pathlib.Path(__file__).resolve().parents[1]
TARGET='EPII_CM55M_APP_S/app/scenario_app/hello_world_cmsis_cv'
FILES=('cvapp_hello_world_cmsis_cv.cpp','vt_tracker.h','vt_tracker.c','vt_packet.h','vt_packet.c')

def backup_original(path):
    backup=path.with_name(path.name+'.original')
    if not backup.exists():shutil.copy2(path,backup)
    return backup

def configure_line(path,pattern,transform,label):
    backup=backup_original(path)
    original=backup.read_text(encoding='utf-8')
    matches=list(re.finditer(pattern,original,re.MULTILINE))
    if len(matches)!=1:
        raise SystemExit(f'Expected one {label} in {backup}, found {len(matches)}')
    updated=transform(matches[0].group(0))
    content=original[:matches[0].start()]+updated+original[matches[0].end():]
    path.write_text(content,encoding='utf-8',newline='')

def patch_windows_source_discovery(app_root):
    """Avoid duplicate case-variant wildcard matches on Windows."""
    path=app_root/'options'/'scripts.mk'
    backup=backup_original(path)
    content=backup.read_text(encoding='utf-8')
    patterns={
        'get_csrcs': r'get_csrcs\s*=.*',
        'get_asmsrcs': r'get_asmsrcs\s*=.*',
        'get_cxxsrcs': r'get_cxxsrcs\s*=.*',
        'get_ccsrcs': r'get_ccsrcs\s*=.*',
    }
    for name,pattern in patterns.items():
        matches=list(re.finditer(pattern,content,re.MULTILINE))
        if len(matches)!=1:
            raise SystemExit(f'Expected one {name} source-discovery function in {backup}, found {len(matches)}')
        match=matches[0]
        original=match.group(0)
        replacement=original.replace(' = ', ' = $(sort ', 1)+')'
        content=content[:match.start()]+replacement+content[match.end():]
    path.write_text(content,encoding='utf-8',newline='')
    print('Deduplicated case-insensitive SDK source wildcards in',path)

def suppress_frame_ready_logging(app_root):
    """Keep the binary tracker stream free of one vendor text line per frame."""
    path=app_root/'app'/'scenario_app'/'hello_world_cmsis_cv'/'hello_world_cmsis_cv.c'
    backup=backup_original(path)
    original=backup.read_text(encoding='utf-8')
    pattern=r'^([ \t]*)dbg_printf\(DBG_LESS_INFO, "SENSORDPLIB_STATUS_XDMA_FRAME_READY %d .*g_cur_jpegenc_frame\);[ \t]*$'
    matches=list(re.finditer(pattern,original,re.MULTILINE))
    if len(matches)!=1:
        raise SystemExit(f'Expected one per-frame debug log in {backup}, found {len(matches)}')
    match=matches[0]
    replacement=match.group(1)+'/* Binary VTF1 packets use this UART; suppress per-frame text. */'
    content=original[:match.start()]+replacement+original[match.end():]
    path.write_text(content,encoding='utf-8',newline='')
    print('Suppressed the vendor per-frame UART diagnostic in',path)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('sdk',type=pathlib.Path)
    a=p.parse_args()
    dest=a.sdk.resolve()/TARGET
    app_root=a.sdk.resolve()/'EPII_CM55M_APP_S'
    buildfile=app_root/'makefile'
    scenario_config=dest/'hello_world_cmsis_cv.mk'
    linker_script=dest/'TFLM_cmsis_cv_S_only.ld'
    if not dest.is_dir() or not buildfile.is_file():
        raise SystemExit('Not an upstream Himax SDK checkout: expected '+str(dest))
    orig=dest/'cvapp_hello_world_cmsis_cv.cpp'
    backup_original(orig)
    for name in FILES:
        shutil.copy2(ROOT/'firmware'/name,dest/name)
        print('Installed',dest/name)

    configure_line(buildfile,r'^APP_TYPE\s*=.*$',
                   lambda _: 'APP_TYPE = hello_world_cmsis_cv','APP_TYPE assignment')
    configure_line(scenario_config,r'^LIB_SEL\s*=.*$',
                   lambda line: 'LIB_SEL = '+' '.join(
                       lib for lib in line.split('=',1)[1].split()
                       if lib not in {'cmsis_cv','cmsis_dsp'}),
                   'LIB_SEL assignment')
    configure_line(linker_script,r'^__HEAP_SIZE\s*=.*$',
                   lambda _: '__HEAP_SIZE = 0x10000;','linker heap size')
    patch_windows_source_discovery(app_root)
    suppress_frame_ready_logging(app_root)
    print('Configured APP_TYPE = hello_world_cmsis_cv in',buildfile)
    print('Skipped unused CMSIS-CV/DSP archives in',scenario_config)
    print('Reserved a 64 KiB heap for the feature-tracking firmware in',linker_script)
    print('Verify build with vendor toolchain before flashing.')
if __name__=='__main__':main()
