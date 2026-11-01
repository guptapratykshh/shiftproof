"""Build the local redesign delivery report from actual verification artifacts."""
from pathlib import Path
import json, html, xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/redesign'
def browser(name):
    p=ROOT/'artifacts'/name
    if not p.exists(): return {'status':'pending'}
    raw=p.read_text(); data=json.loads(raw[raw.index('{'):]); s=data['stats']
    return {'passed':s['expected'],'failed':s['unexpected'],'flaky':s['flaky'],'skipped':s['skipped'],'duration_ms':s['duration'],'artifact':name}
def backend():
    p=ROOT/'artifacts/redesign-backend-final.xml'
    if not p.exists(): return {'status':'pending'}
    root=ET.parse(p).getroot(); suites=root.findall('testsuite') or [root]
    return {k:sum(int(s.get(k,0)) for s in suites) for k in ['tests','failures','errors','skipped']}
build_log=(ROOT/'artifacts/redesign-build.log').read_text()
build={'passed':'✓ built in' in build_log,'typescript_and_vite':'✓ built in' in build_log,'warning':'Lazy Three.js scene exceeds Vite 500 kB advisory'}
checks={'build':build,'baseline_browser':browser('redesign-baseline-browser.json'),'pre_final_browser':browser('redesign-browser-initial.json'),'backend':backend(),'browser_full_run':browser('redesign-browser-final.json'),'management_connectivity_interruption':browser('redesign-management-connectivity.json'),'management_followup':browser('redesign-management-final.json'),'offline':browser('redesign-offline-final.json')}
def browser_coverage():
    outcomes={}
    def visit(suite):
        for spec in suite.get('specs',[]):
            outcomes[(suite.get('file',''),spec['title'])]=all(t['status']=='expected' for t in spec['tests'])
        for child in suite.get('suites',[]): visit(child)
    for filename in ['redesign-browser-final.json','redesign-management-final.json']:
        path=ROOT/'artifacts'/filename
        if path.exists():
            for suite in json.loads(path.read_text())['suites']: visit(suite)
    return {'unique_checks':len(outcomes),'latest_passed':sum(outcomes.values()),'latest_failed':sum(not v for v in outcomes.values()),'method':'Full run plus targeted rerun after test-only locator correction. Raw failed runs are retained.'}
checks['browser_coverage']=browser_coverage()
issues=[
 ('Reference uses fictional records and a simulated recorder','Ported design into the existing React/Vite app; production pages use authenticated scoped APIs.'),
 ('Workspace mixes all pages with capture state','Extracted Home, Overview, Work register, Reports, Capture, My work, saved reports and dialogs; capture state remains above navigation.'),
 ('No consistent appearance preferences','Added shared semantic colors and Light/Dark/System persistence across public, account, demo, worker and management screens.'),
 ('Workers see a technical combined workspace','Added three destinations, a prominent recording action, own activity and optional transcript review; management has a separate report queue.'),
 ('Capture context guard lacked braces','Preserved the frozen work and shift instead of resetting capture context on every ensure-note call.'),
 ('Draft checkpoint race during navigation','Autosave carries the capture ID from the render that scheduled it; retired captures cannot be saved under a replacement identity.'),
 ('Sidebar text and idle microphone bars lost contrast','Corrected semantic colors for sidebar names, organization selection and microphone-meter segments.'),
 ('Demo mobile header overflows with appearance controls','Header and actions wrap on narrow screens; language and appearance remain accessible.'),
 ('Older tests assume navigation positions and default capture page','Updated assertions to named destinations and the intentional Home-to-record journey; retained permission and backend assertions.'),
 ('Owner operational role can hide organization-wide report visibility','Owners retain management visibility while review controls still require backend operational permission; unauthorized review returns HTTP 403.'),
 ('Canceled and preparing reports appear actionable','Canceled reports are excluded from pending review; preparing reports display their actual progress and cannot be reviewed before their transcript exists.'),
 ('Application loads demo code inside private portal','Split demo and workspace route bundles; public Three.js scene remains separately loaded.'),
]
commands=['.venv/bin/python -m pytest backend/tests -q --junitxml=artifacts/redesign-backend-final.xml','cd frontend && npm run build','cd frontend && npx playwright test --reporter=json','cd frontend && npx playwright test tests/plum-redesign.spec.ts -g "management screens"','cd frontend && npx playwright test --config playwright.offline.config.ts --reporter=json','python3 scripts/report_redesign.py']
report={'checks':checks,'backend_api_changes':False,'database_migration':False,'private_records_modified':False,'provider_or_billing_changes':False,'issues':[{'issue':a,'change':b} for a,b in issues],'commands':commands,'visual_coverage':{'before_screenshots':len(list((OUT/'before').glob('*.png'))),'after_screenshots':len(list((OUT/'after').glob('*.png'))),'viewport_widths':[390,768,1440,1920],'languages':['Hindi','English'],'appearance':['Light','Dark','System'],'limits':'Theme/page matrix is automated. Not every possible state of every form was visually inspected, and no formal accessibility certification is claimed.'},'limitations':['No live Prisma, Gemini or Timbre verification in this redesign run.','Recorded browser journeys use a Chromium test microphone and an explicitly controlled transcript fixture.','No observed worker-comprehension or factory-usability sessions were conducted.','Existing manufacturing-only evaluation scope and preview-industry labels remain.','Appearance preferences are stored on this browser; they do not sync across devices.']}
OUT.mkdir(parents=True,exist_ok=True);(OUT/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
escape=html.escape
rows=''.join(f'<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>' for a,b in issues)
shots=sorted((OUT/'after').glob('*.png'))
links=''.join(f'<li><a href="after/{escape(p.name)}">{escape(p.stem)}</a></li>' for p in shots)
featured=['en-light-overview-1440.png','en-dark-overview-1440.png','en-light-worker-home-390.png','hi-dark-worker-home-390.png','supervisor-packing-review.png','owner-report-after-review.png']
figures=''.join(f'<figure><a href="after/{name}"><img loading="lazy" src="after/{name}" alt="{escape(Path(name).stem)}"></a><figcaption>{escape(Path(name).stem)}</figcaption></figure>' for name in featured if (OUT/'after'/name).exists())
steps=['Opened the worker Home and checked its three destinations and assigned work.','Opened Record, started the browser test microphone, checked the meter, stopped and played the recording.','Opened optional transcript review; saved the unfinished recording when navigating to My work.','Reloaded, restored the draft, sent the recording and returned Home without a discard prompt.','Opened Reports as the owner and found the worker’s recording, including the provider-failure state.','Recorded a second fictional update and used an explicitly controlled transcription fixture to check the optional transcript-before-send stage.','Submitted the saved transcript, opened its report, selected packing complete and Correct, selected the recording-based review reason, and saved.','Verified packing was human-reviewed while overall readiness remained blocked; captured the updated role-specific screens.']
page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>ShiftProof redesign implementation report</title>
<style>body{{font:16px/1.6 system-ui;background:#f7f5fb;color:#29213a;max-width:1150px;margin:32px auto;padding:0 24px}}h1{{font-size:32px}}h2{{margin-top:40px}}a{{color:#6246a5}}table{{border-collapse:collapse;width:100%;background:white}}td,th{{border:1px solid #e7e1f0;padding:14px;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;background:#eee8fc;padding:20px;border-radius:12px}}.gallery{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}}figure{{margin:0}}img{{width:100%;max-height:520px;object-fit:contain;object-position:top;background:white;border:1px solid #e7e1f0}}figcaption{{font-size:14px}}.note{{padding:20px;background:#eee8fc;border-radius:12px}}</style>
<h1>ShiftProof: redesign delivery</h1><p>The supplied plum/lavender reference is integrated into the existing application. Backend contracts, evidence, review permissions and provider safeguards are preserved.</p>
<div class="note">This is a frontend redesign and regression-verification report. Browser audio is simulated; live provider accuracy and worker usability are not established by these results.</div>
<h2>Verification</h2><pre>{escape(json.dumps(checks,indent=2))}</pre><p><a href="results.json">Machine-readable results</a> · <a href="../redesign-build.log">Production build log</a> · <a href="../redesign-backend-final.log">Backend log</a> · <a href="../redesign-browser-final.json">Browser results</a> · <a href="../redesign-offline-final.json">Offline results</a></p>
<p>The pre-final browser run passed 53 cases and failed the new owner-permission check because its request was invalid before authorization. The check now sends a valid interpretation and requires HTTP 403. The later full run passed 53 cases, including authorization, and stalled on the new Status-filter locator. That test now targets the combobox by accessible role and name; its separate rerun is reported above. A subsequent matrix attempt opened offline capture because the browser reported offline; the final visual rerun explicitly sets online mode. Production offline behavior is tested separately. All raw runs are retained, including failures. <a href="../redesign-browser-initial.json">Earlier run</a> · <a href="../redesign-management-final.json">Management rerun</a> · <a href="token-contrast.json">Semantic-token contrast measurements</a>.</p>
<h2>Screen and workflow checklist</h2><ul><li>Worker: Home, assigned work, recording, optional transcript check, delivery receipt, saved drafts, My work and Handover.</li><li>Management: scoped Overview, work register, Reports &amp; evidence, focused review and unchanged protected-clearance rules.</li><li>Owner: Team, invitations, access management, Settings, setup, policy controls and Downloads.</li><li>Accounts: signup, login, worker activation/login, recovery, organization selection, expired/access-ended states.</li><li>Public: themed landing with existing lazy 3D scene, isolated editable demo, manufacturing-only evaluation disclosures.</li><li>Appearance: Light, Dark and System; Hindi/English; mobile preferences; readable controls and internally scrolling desktop histories.</li></ul>
<p>Page/theme screenshots cover 390, 768, 1440 and 1920px. Existing checks also exercise keyboard dialogs, 200% zoom, offline recovery, empty states and provider failures. This is regression coverage, not an exhaustive audit of every state or an accessibility certification.</p>
<h2>Changes and issues addressed</h2><table><thead><tr><th>Issue</th><th>Change</th></tr></thead><tbody>{rows}</tbody></table>
<h2>GUI walkthrough</h2><ol>{''.join('<li>'+escape(s)+'</li>' for s in steps)}</ol><p>The second transcription is a labeled test fixture. It is not a claim of successful live Prisma recognition.</p><p><a href="walkthrough/worker-flow.webm">Worker GUI recording</a> · <a href="walkthrough/owner-review.webm">Owner/review GUI recording</a></p>
<h2>Selected screenshots</h2><div class="gallery">{figures}</div><details><summary>All after screenshots ({len(shots)})</summary><ul>{links}</ul></details><p><a href="before/en-overview-1440.png">Before: management overview</a> · <a href="before/hi-capture-390.png">Before: mobile Hindi capture</a></p>
<h2>Reproduce</h2><pre>{escape(chr(10).join(commands))}</pre><p>Browser fixtures use fresh isolated databases and fictional organizations. Do not replace those data directories with a private workspace.</p>
<h2>Remaining limits</h2><ul>{''.join('<li>'+escape(s)+'</li>' for s in report['limitations'])}</ul><p>No deployment, permission expansion, data migration, provider-model switch or billing change was required. The separately loaded Three.js scene still triggers Vite’s large-chunk advisory.</p></html>'''
(OUT/'report.html').write_text(page)
print(json.dumps(checks))
