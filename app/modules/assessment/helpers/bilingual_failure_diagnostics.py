"""Save a failed generated response for local replay; never persist API keys."""
import json
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

def save_failure(raw_output, request, error, *, directory=None, response_metadata=None):
    if not isinstance(raw_output,str) or len(raw_output)>20000000:
        raise ValueError('Diagnostic response size is invalid.')
    root=Path(directory) if directory is not None else Path(tempfile.gettempdir())/'school_monitor_ai_diagnostics'
    root.mkdir(parents=True,exist_ok=True)
    path=root/('bilingual_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+uuid4().hex+'.json')
    payload=dict(format='school_monitor_bilingual_v1',request=asdict(request),response=raw_output,
        error_type=type(error).__name__,error=str(error))
    if isinstance(response_metadata, dict):
        payload['response_metadata'] = response_metadata
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
        json.dump(payload,stream,ensure_ascii=False,indent=2,default=str)
    return path
