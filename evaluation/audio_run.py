"""Transcribe only consented scripted recordings, with resumable per-file caching.

Fill audio_manifest.json recordings with scenario_id, note_id, speaker_id,
consent_record, path, split, variant (clean|noise|8khz). Paths are relative to repo
root. Never infer consent from a filename or synthesize a missing speaker.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
from shiftproof.providers import transcribe, ProviderError
from shiftproof.service import validate_audio
from language_run import distribution

ROOT=Path(__file__).parent


def run(max_calls=10):
    manifest=json.loads((ROOT/'audio_manifest.json').read_text())
    cache=ROOT.parent/'.local/audio-evaluation';cache.mkdir(parents=True,exist_ok=True)
    assignments={a['scenario_id']:a for a in manifest['assignments']}
    rows=[];errors=[];calls=0;seen=set()
    for item in manifest['recordings']:
        sid,nid=item['scenario_id'],item['note_id'];assignment=assignments.get(sid)
        identity=(sid,nid,item['variant'])
        if identity in seen: raise ValueError('Duplicate recording identity')
        seen.add(identity)
        if not assignment or not item.get('consent_record') or item['speaker_id']!=assignment['speaker_id'] or item['split']!=assignment['split'] or item['variant'] not in ('clean','noise','8khz') or nid not in [n['note_id'] for n in assignment['notes']]:
            raise ValueError('Recording must match an assignment, speaker, split, variant and consent record')
        audio=(ROOT.parent/item['path']).read_bytes();validate_audio(audio)
        digest=hashlib.sha256(audio+b'prisma-hi-IN-verbatim-v1').hexdigest();path=cache/f'{digest}.json'
        try:
            if path.exists(): response=json.loads(path.read_text());origin='replay'
            else:
                if calls>=max_calls: break
                start=time.monotonic();calls+=1;text,rid=transcribe(audio)
                response={'text':text,'request_id':rid,'transcription_ms':round((time.monotonic()-start)*1000),'audio_sha256':hashlib.sha256(audio).hexdigest()}
                path.write_text(json.dumps(response,ensure_ascii=False,indent=2)+'\n');origin='live'
            rows.append({**item,**response,'origin':origin})
        except ProviderError as exc:
            errors.append({'scenario_id':sid,'note_id':nid,'error':str(exc)});break
    report={'status':'not_collected' if not manifest['recordings'] else 'completed' if len(rows)==len(manifest['recordings']) and not errors else 'partial',
            'dataset_sha256':manifest['dataset_sha256'],'assignments':manifest['assignments'],'recordings':rows,'errors':errors,
            'network_calls':calls,'transcription_latency':distribution([r['transcription_ms'] for r in rows if r['origin']=='live']),
            'end_to_end_latency':{'status':'not_measured','median_ms':None,'p95_ms':None},
            'limitations':['Controlled scripted two-speaker study; not a real factory trial.','Timing replays are excluded from live latency.','Missing recordings are not replaced by synthetic speech.']}
    output=ROOT/'results/audio-transcripts.json';output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'transcripts':len(rows),'network_calls':calls,'errors':errors,'report':str(output)},indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--max-calls',type=int,default=10);a=p.parse_args();run(a.max_calls)
