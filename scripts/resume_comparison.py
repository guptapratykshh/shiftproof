"""Pace independent system attempts without changing prompts, cached outputs or service logic."""
import argparse
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
import language_run


def main():
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['development','held_out'],required=True)
    p.add_argument('--output',required=True);p.add_argument('--seconds',type=float,default=20);p.add_argument('--max-calls',type=int,default=200);a=p.parse_args()
    if a.seconds<0 or a.seconds>60:p.error('--seconds must be between 0 and 60')
    next_attempt=0
    def pace(function):
        def call(*args,**kwargs):
            nonlocal next_attempt
            time.sleep(max(0,next_attempt-time.monotonic()))
            next_attempt=time.monotonic()+a.seconds
            return function(*args,**kwargs)
        return call
    language_run.replay=pace(language_run.replay);language_run.baseline=pace(language_run.baseline)
    folder=Path(a.output);folder.mkdir(parents=True,exist_ok=True)
    (folder/'pacing.json').write_text(json.dumps({'seconds_between_system_attempt_starts':a.seconds,
        'stage_latency_excludes_pacing':True,'system_elapsed_ms_includes_pacing':True,
        'scope':'Operator rate pacing only; model, prompts, validation, review services and cache identities are unchanged.'},indent=2)+'\n')
    language_run.run('live',a.split,a.output,a.max_calls)

if __name__=='__main__':main()
