"""One copy of each native model request, with lossless audit references."""
from hashlib import sha256
import json
from pathlib import Path

from .ga_runtime import filesystem_path
from .watch import atomic_json

FORMAT = 'native-model-params-reference-1'


def record_model_request(message, folder, relative):
    folder=filesystem_path(folder)
    target=folder/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    atomic_json(target,message.get('params'))
    reference={'format':FORMAT,'path':Path(relative).as_posix(),
               'sha256':sha256(target.read_bytes()).hexdigest()}
    return {key:value for key,value in message.items() if key!='params'} | {'_params_reference':reference}


def read_audit(folder):
    folder=filesystem_path(folder)
    messages=[]
    for line in (folder/'audit.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():continue
        value=json.loads(line)
        ref=value.get('_params_reference')
        if ref is not None:
            if ref.get('format')!=FORMAT or value.get('kind')!='request' or value.get('method')!='model' or 'params' in value:
                raise ValueError('Invalid native model audit reference')
            relative=Path(ref['path'])
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0] not in ('model','audit-model-rejections'):
                raise ValueError('Model audit reference escaped session')
            target=folder/relative
            if target.is_symlink() or not target.resolve().is_relative_to(folder.resolve()):
                raise ValueError('Model audit reference escaped session')
            body=target.read_bytes()
            if sha256(body).hexdigest()!=ref['sha256']:
                raise ValueError('Model audit reference integrity mismatch')
            value={key:item for key,item in value.items() if key!='_params_reference'} | {'params':json.loads(body)}
        messages.append(value)
    return messages
