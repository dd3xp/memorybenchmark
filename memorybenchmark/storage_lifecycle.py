"""Retire task working copies only after a verified, committed checkpoint."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil

from .ga_runtime import filesystem_path, memory_manifest
from .watch import atomic_json


def retire_working_memory(state, checkpoint, expected, *, allowed_parent):
    state,checkpoint,allowed_parent=map(filesystem_path,(state,checkpoint,allowed_parent))
    if allowed_parent.name!='live-state' or state.parent.resolve()!=allowed_parent.resolve() or not re.fullmatch('[0-9a-f]{32}',state.name):
        raise ValueError('Working-memory cleanup is outside its own task boundary')
    if checkpoint.resolve().is_relative_to(state.resolve()) or state.is_symlink() or getattr(state,'is_junction',lambda:False)():
        raise ValueError('Working-memory cleanup cannot remove its checkpoint')
    if memory_manifest(checkpoint)!=expected or memory_manifest(state)!=expected:
        raise ValueError('Working memory is not an exact checkpoint copy')
    receipt={'utc':datetime.now(timezone.utc).isoformat(),'state_id':state.name,
             'checkpoint':str(checkpoint),'files':len(expected),
             'logical_bytes':sum(v['size'] for v in expected.values()),'status':'verified_before_removal'}
    record=checkpoint.parent/'working-memory-cleanup.json'
    atomic_json(record,receipt)  # no deletion if the preservation receipt cannot be saved
    shutil.rmtree(state)
    receipt.update(status='removed',utc=datetime.now(timezone.utc).isoformat())
    atomic_json(record,receipt)
    return receipt


def retire_committed_state(state, output, report, *, allowed_parent):
    """GC must never convert a completed game into a scientific retry."""
    if not report.get('infrastructure_ok'):
        return
    try:
        saved=json.loads((filesystem_path(output)/'summary.json').read_text(encoding='utf-8'))
        if saved.get('output_memory')!=report.get('output_memory'):
            raise ValueError('Checkpoint summary was not committed')
        retire_working_memory(state,Path(output)/'memory-after',report['output_memory'],allowed_parent=allowed_parent)
    except (OSError,ValueError,KeyError) as error:
        try:
            atomic_json(Path(output)/'working-memory-cleanup-deferred.json',{
                'utc':datetime.now(timezone.utc).isoformat(),'state_id':Path(state).name,
                'status':'retained_or_removal_deferred','error_type':type(error).__name__,
                'scientific_result_unchanged':True})
        except OSError:
            pass
