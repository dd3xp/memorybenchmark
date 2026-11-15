"""Read-only, bounded diagnostics; no credentials, prompts or model calls."""
import ctypes
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

STAGE = Path('C:/Codes/memorybenchmark-private/gemini-easy-normal-hermes-20261111')

def read(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, FileNotFoundError):
        return None

def latest(folder, pattern='*.json'):
    paths = sorted(folder.glob(pattern), reverse=True)
    for path in paths:
        value = read(path)
        if value is not None:
            return value
    return None

def tail(path):
    if not path.exists():
        return None
    with path.open('rb') as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 32768))
        lines = stream.read().splitlines()
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            pass
    return None

def process(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return {'pid': pid, 'alive': False}
    try:
        code = ctypes.c_ulong()
        times = [ctypes.c_ulonglong() for _ in range(4)]
        kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))
        ok = kernel.GetProcessTimes(ctypes.c_void_p(handle), *[ctypes.byref(v) for v in times])
        return {'pid': pid, 'alive': code.value == 259,
                'created_filetime': times[0].value if ok else None}
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))

rows = []
for spec in read(STAGE / 'prepared.json')['runs']:
    root, run = Path(spec['root']), Path(spec['run'])
    pilot = read(run / 'pilot.json')
    started = read(root / 'driver-started.json')
    exited = read(root / 'driver-exit.json')
    folders = sorted((run / 'sessions').glob('*'))
    current = folders[-1] if folders else None
    summary = read(current / 'summary.json') if current else None
    dirs = sorted((root / 'request-recovery-state/leases').glob('*'), key=lambda p: p.stat().st_mtime_ns)
    lease = latest(dirs[-1], 'lease-*.json') if dirs else None
    guard = read(dirs[-1] / 'guard-exit.json') if dirs else None
    transport = latest(root / 'transport-status.versions') or {}
    keys = ('kind','utc','reason','call','attempt','retry_after','delay_seconds','retry_at','request_sha256')
    row = {k: spec[k] for k in ('model','map','condition')}
    row.update(root=str(root), run=str(run), completed=len(pilot['sessions']),
               pilot_status=pilot['status'], sealed=(root / 'result.json').exists(),
               started=started, process=process(started['pid']) if started else None,
               exited=exited, current_session=current.name if current else None,
               summary={k:summary.get(k) for k in ('infrastructure_ok','infrastructure_error','success','done','game_actions','runtime_memory_id')} if summary else None,
               lease={k:lease.get(k) for k in ('host_pid','host_created_filetime','closed','paused','heartbeat_epoch','active_elapsed','active_budget')} if lease else None,
               guard=guard, transport={k:transport.get(k) for k in keys},
               ledger_tail={k:(tail(current/'transport-attempts.jsonl') or {}).get(k) for k in keys} if current else None)
    rows.append(row)
output={'utc':datetime.now(timezone.utc).isoformat(), 'disk_free_gib':round(shutil.disk_usage(STAGE).free/2**30,2),'runs':rows}
print(json.dumps(output,ensure_ascii=True))
