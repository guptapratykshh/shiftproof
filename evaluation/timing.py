"""Summarize private browser events; all differences use one document's monotonic clock."""
import argparse
import json
import math
from pathlib import Path
from language_run import distribution


def summarize(events):
    groups={};playbacks={}
    for e in events:
        if not isinstance(e.get('at_ms'),(int,float)) or not math.isfinite(e['at_ms']) or e['at_ms']<0:
            raise ValueError('Invalid monotonic timestamp')
        table,key=(playbacks,e['playback_id']) if e.get('playback_id') else (groups,e.get('capture_id'))
        if key:table.setdefault((e['document_id'],key),[]).append(e)
    spans={'recording_ms':[],'preview_before_upload_ms':[],'transcription_visible_ms':[],
           'human_transcript_inspection_ms':[],'extraction_visible_ms':[],
           'stop_to_result_including_human_ms':[],'processing_excluding_human_ms':[],
           'playback_available_ms':[],'playback_started_ms':[]}
    def delta(row,start,end):
        a=next((e['at_ms'] for e in row if e['event']==start),None)
        b=next((e['at_ms'] for e in row if e['event']==end and (a is None or e['at_ms']>=a)),None)
        return b-a if a is not None and b is not None else None
    pairs={'recording_ms':('capture_started','recording_stopped'),
        'preview_before_upload_ms':('recording_stopped','upload_submitted'),
        'transcription_visible_ms':('upload_submitted','transcript_visible'),
        'human_transcript_inspection_ms':('transcript_visible','extraction_submitted'),
        'extraction_visible_ms':('extraction_submitted','result_visible'),
        'stop_to_result_including_human_ms':('recording_stopped','result_visible')}
    for row in groups.values():
        row.sort(key=lambda e:e['at_ms'])
        for name,pair in pairs.items():
            value=delta(row,*pair)
            if value is not None:spans[name].append(value)
        trans=delta(row,'upload_submitted','transcript_visible');ext=delta(row,'extraction_submitted','result_visible')
        if trans is not None and ext is not None:spans['processing_excluding_human_ms'].append(trans+ext)
    for row in playbacks.values():
        for name,end in [('playback_available_ms','playback_available'),('playback_started_ms','playback_started')]:
            value=delta(row,'playback_requested',end)
            if value is not None:spans[name].append(value)
    return {'status':'measured' if events else 'pending','capture_attempts':len(groups),
        'failed_capture_attempts':sum(any(e['event']=='processing_failed' for e in row) for row in groups.values()),
        'incomplete_capture_attempts':sum(not any(e['event'] in ('result_visible','processing_failed') for e in row) for row in groups.values()),
        'playback_attempts':len(playbacks),'failed_playbacks':sum(any(e['event']=='playback_failed' for e in row) for row in playbacks.values()),
        'timings':{k:distribution(v) for k,v in spans.items()},
        'limitations':['Browser-visible intervals include upload, network and polling; server stage timings are separate.',
                      'Human inspection and preview times are excluded from processing_excluding_human_ms.',
                      'Only completed intervals have percentiles; failed/incomplete attempts remain counted.',
                      'Timing events alone do not establish participant identity, consent or task correctness.']}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    report=summarize([json.loads(line) for line in Path(a.input).read_text().splitlines() if line.strip()])
    Path(a.output).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
