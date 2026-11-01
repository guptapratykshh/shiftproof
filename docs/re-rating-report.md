# ShiftProof implementation and re-rating report

**Subsequent delivery:** organization accounts, private industry workspaces and the 3D landing page are documented in [the organization release report](organizations-release.md). The manufacturing results below describe their original frozen run, not a fresh benchmark of the expanded application.

Updated October 16, 2026 (IST). Local implementation, real speech integration, recovery, browser verification and evaluation tooling are delivered. The held-out model run is **completed** and the development run is **completed**. Independent annotations, the two-speaker audio study and usability measurements remain pending. AWS and billing were not changed.

## Try the implementation

- Private local application: http://localhost:5173 (backend http://127.0.0.1:8000).
- Interactive public preview: https://diary-silent-kernel-numerical.trycloudflare.com  -  operator, supervisor and quality accounts can make changes. This temporary link requires the Mac and tunnel to remain running.
- Visitor records live in `.local/public-preview/`, separate from private recordings and reviews. Public login, create/delete and private-record isolation were verified. Existing databases were backed up before restarting.
- Genuine integration clip: [60-second voice and recovery walkthrough](../artifacts/live-voice-recovery-60s.mp4), with [provenance and edit disclosures](../artifacts/live-voice-recovery-60s.json).

## Brief for an independent reviewer

ShiftProof helps a factory's incoming shift identify what still needs verification. Workers select a batch and record a short Hindi/Hinglish update. Gnani Prisma transcribes it; the worker inspects the saved transcript; Gemini proposes draft claims with exact source excerpts. Python reconciliation preserves unresolved quality holds, conditional work, contradictory counts and correction history. Authorized reviewers record their interpretation, and Gnani Timbre speaks one focused clarification. Incoming workers acknowledge an exact stored handover version; later material changes require acknowledgement again.

The demonstration is a fictional carton-packaging factory with six batches and three roles. It covers packing, quantities, quality, dispatch reports and tasks. Human-reviewed status records a person's decision; it does not establish physical truth or authorize shipment. Its originality claim is evidence preservation and explicit uncertainty across conflicting spoken handovers. Industry demand, voice advantage and time savings remain hypotheses.

## Changes against the review and implementation plan

| Weakness or requirement | Delivered change | Remaining limit |
|---|---|---|
| Unseen speech failed in sample-only mode | Fixed Gemini REST parsing of `steps[].content`; 12 live development checks passed; explicitly pinned `gemini-3.5-flash-lite` | Free quota can interrupt inference |
| Future completion could clear/hide a hold | Prompt distinguishes pending-now from future completion; planned/conditional/other-property reports cannot supersede active holds | Model interpretation can still be wrong; drafts need review |
| Quantity corrections needed real history | Property-specific supersession, prior reports retained, fifteen-to-fifty production demonstration | Hindi number ambiguity remains an observed failure category |
| Manufacturing relevance was too broad | Three reproducible production, seal-quality and dispatch demonstrations through real services | Fictional scenarios, no factory validation |
| Inspection completion could imply clearance | Inspection tasks and quality decisions remain separate; task completion cannot release a hold | Quality reviewer must explicitly resolve the hold |
| Readiness needed actionable evidence | Every unresolved reason has source IDs, next action and responsible role/person or Unassigned; dispatch-pending blocks readiness | Missing real-world observations remain unknown |
| Generic question matching could invent answers | Tested English/Hindi/Hinglish phrase sets; unrelated questions abstain; each answer item links sources | Three supported intents only; no arbitrary operational advice |
| History answers blurred old/current reports | Current, rejected, superseded and historical reports are distinguished; comparison snapshot named, otherwise Recorded history | Snapshot comparison is within this fictional workspace |
| Clarification replies could use stale context | Browser sends displayed version; backend returns 409 before creating stale replies; recording/text retained for explicit refresh | Older clients can omit the optional version for compatibility |
| Failures and provenance were opaque | Stage/error categories, model/prompt/source provenance, matching last-test receipt, text fallback and saved-transcript retries | Provider request IDs can be absent; none are invented |
| Retry chains could exceed free quota | Two network attempts total, shared between transient retry and malformed-output repair; no silent model switch | Per-workspace/run limits do not combine every process using the same account |
| Evaluation suppressed baseline after extraction failure | Independent system attempts, append-only failure history, replay labels, frozen shared clarification inputs | Quota/auth failures pause shared work explicitly |
| Benchmark only measured supplied claims | Separate live language comparison through create/process/review services; full-context same-model baseline and ablation | Frozen labels are implementation-author annotations |
| Reviewers could see system identity | Randomized review packets with original evidence; mappings stored privately; payload integrity checks | Writing style can still reveal a system |
| Voice benefit and practical impact unmeasured | Counterbalanced worksheets, six study metrics, transcript edits, separate capture/understanding/source-finding time, private browser timing harness | No independent human measurements yet |
| Gnani needed visible real use | Existing human recording → fresh Prisma → Gemini retry → Timbre clarification → acknowledgement video | Reused development recording; not a new participant session |
| Too many industries/integrations | Manufacturing scope retained; AWS, ERP and damaged-carton accounting deferred | Multi-factory tenancy/production operations are outside this prototype |

## Engineering evidence

| Check | Result | Interpretation |
|---|---:|---|
| Backend pytest | 153 passed, two dependency deprecation warnings | Core, provider mocks, roles, retries, concurrency, evidence, persistence and evaluation tooling |
| Playwright browser suite | 11 passed | Recording, manual recovery, stale clarification retention, source links, tasks, acknowledgement, mobile and evaluation views |
| TypeScript/Vite production build | Passed | Compilation and bundling |
| Gemini live development smoke | 12 / 12 passed | Exact expected claim sets, evidence, conditions, clarification and wrong-batch behavior |
| Original engine scenarios | 60 / 60 | Supplied structured claims; not model accuracy |
| Frozen language cases with gold extraction | 60 / 60 | Real-service contract checks; not model accuracy |
| Gold-service ablation | 52 / 60 | Corrections/conditions disabled; separate from live results below |
| Manufacturing workflow script | 3 / 3 | Explicitly labeled fixtures in isolated SQLite |
| Public interaction and isolation | Passed | All demo roles available; public writes did not alter private state |
| Walkthrough media | 60.000 s, H.264/AAC, 1600×1000 | Real UI footage with edit/provenance disclosure |

The regression suite includes negation, fifteen-to-fifty corrections, late uploads, persistent holds, planned claims, short replies, wrong batches, simultaneous reviews, duplicate processing, unauthorized clearance, transcript revisions, stale acknowledgements, malformed output, mixed transient/validation failures, quota/outage handling and playable WAV output. Capability checks for permission enforcement and acknowledgements are not presented as language-model scores.

## Live comparison: 40 frozen held-out cases

Model: **gemini-3.5-flash-lite**, temperature 0, maximum 4096 output tokens, Interactions JSON Schema with `store=false`, application Pydantic/exact-excerpt validation. Extraction prompt version: `2df7a7d1d94e3749`. The same model and shared source/timing/question/review inputs are used for the baseline. The baseline receives neither extracted claims nor derived state. The frozen clarification companion manifest is independent of predictions. A workflow failing to produce the required question is recorded as a failure.

Status: **completed**. All requested cases remain in state/coverage denominators; conflict and false-ready denominators identify evaluated cases. Cached successful provider responses are labeled replay, not new inference. The audited runs revalidate cached model output through the real services under explicit schema identities; the original capture runs and their failure histories remain preserved. Historical failures are retained even after successful resumption: **5 failed attempts** in the held-out run. Pacing was added between system attempts after free-quota interruptions; this outer delay is excluded from provider-stage timings and included in per-system wall time.

| Measure | ShiftProof | Full-context Gemini | Ablation |
|---|---:|---:|---:|
| Completed / requested | 40 / 40 | 40 / 40 | 40 / 40 |
| Correct state + quantity / requested | 36 / 40 (90.0%) | 22 / 40 (55.0%) | 33 / 40 (82.5%) |
| Conflict precision / recall | 80.0% / 100.0% | 66.7% / 25.0% | 57.1% / 100.0% |
| Conflicts TP / FP / FN | 8 / 2 / 0 | 2 / 1 / 6 | 8 / 6 / 0 |
| Coverage of answerable questions | 38 / 38 | 38 / 38 | 38 / 38 |
| False-ready / evaluated | 0 / 40 | 2 / 40 | 1 / 40 |
| False-ready before final review | 0 | 0 | Not evaluated |
| Valid evidence IDs/excerpts | 100.0%; 40 cases | 100.0%; 40 cases | Not evaluated |

Conflict precision is **80%, below the 85% target**; recall is 100%. State/quantity accuracy reaches the 90% target.

Correction/condition improvement over the matched baseline: **28.6 percentage points** across **7 matched cases**. This is a small synthetic set with author labels, not evidence of representative manufacturing performance. The target of ≥90% state accuracy, ≥85% conflict precision/recall, ≥80% answer coverage and ≥10 percentage-point correction/condition improvement is evaluated honestly; unmet targets remain unmet. Answer correctness and semantic support of citations require independent review and are **not measured**.

Fresh extraction timings in the audited run (earlier measured stage timings remain in the original capture report): **9 notes**, median **2457 ms**, p95 **3170 ms**. Replayed and contract stages are excluded. These are extraction-stage timings, not end-to-end audio latency. In the separate live demonstration, Prisma took 886 ms, Gemini 2344 ms and reconciliation 1 ms for one note; one note is not a latency study.

Observed held-out state/quantity failures:

- **LANG-023 (correction):** frozen label `review`, quantity `60`; ShiftProof returned `review`, quantity `7`.
- **LANG-031 (late):** frozen label `review`, quantity `125`; ShiftProof returned `conflict`, quantity `None`.
- **LANG-035 (negation):** frozen label `hold`, quantity `None`; ShiftProof returned `review`, quantity `None`.
- **LANG-042 (identifier):** frozen label `review`, quantity `None`; ShiftProof returned `conflict`, quantity `None`.

The early quantity failure includes a frozen label of 60 interpreted as 7. A dated late-report case remained a quantity conflict. These need independent Hindi label review and further development work; the frozen held-out labels and prompt were not edited to improve the reported score. Full outputs, reviews, errors and sources remain available for inspection.

## Development results (20 cases, separate from held-out)

Status: **completed**. Historical failed attempts: **3**.

| Measure | ShiftProof | Full-context Gemini | Ablation |
|---|---:|---:|---:|
| Completed / requested | 20 / 20 | 20 / 20 | 20 / 20 |
| Correct state + quantity / requested | 19 / 20 (95.0%) | 10 / 20 (50.0%) | 16 / 20 (80.0%) |
| Conflict precision / recall | 80.0% / 100.0% | 50.0% / 25.0% | 50.0% / 100.0% |
| Conflicts TP / FP / FN | 4 / 1 / 0 | 1 / 1 / 3 | 4 / 4 / 0 |
| Coverage of answerable questions | 19 / 19 | 19 / 19 | 19 / 19 |
| False-ready / evaluated | 0 / 20 | 1 / 20 | 0 / 20 |
| False-ready before final review | 0 | 0 | Not evaluated |
| Valid evidence IDs/excerpts | 100.0%; 20 cases | 100.0%; 20 cases | Not evaluated |

The 12 smoke checks and 12 deterministic answer checks are development checks and are not added to the held-out denominator. The original 60 engine cases remain separately labeled. The language dataset's 20/40 split and related-family grouping are unchanged.

## Human, audio and usefulness evaluation

Prepared: 60 blind label forms, 20 audio assignments (eight development scenarios for the user; twelve held-out for the second speaker), clean/noise/8 kHz tooling, blinded semantic review packets and eight counterbalanced usability assignments. No consent, second-speaker recording, independent label, answer-accuracy score or time-saving result has been fabricated.

`study.py` reports missed-task, false-ready, claim-correction, evidence-traceability and acknowledgement-completeness ratios with numerators/denominators, plus separate capture/understanding/source-finding times and transcript edits. Pending/failed sessions remain visible. `scripts/study-browser.mjs` records opt-in monotonic events only on private localhost; it stores participant measurements in ignored `.local/study-sessions/`, outside the public demo. The timing scorer separates inspection time from processing/playback and counts incomplete attempts. Two speakers cannot establish general factory or linguistic performance.

The delivered video reuses the existing human development recording through a test microphone with fresh provider inference. Its first extraction outage is explicitly simulated. Its successful retry uses live Gemini and the saved Prisma transcript. The mixed Timbre track was re-requested for the exact displayed question after browser audio capture returned an empty body. Processing waits are cut. These disclosures are visible in captions and the companion JSON; the clip is not a human evaluation session.

## Reproduction and artifacts

```sh
.venv/bin/pytest backend/tests -q
npm run build --prefix frontend
npm run test:e2e --prefix frontend
PYTHONPATH=backend .venv/bin/python scripts/check_gemini.py --model gemini-3.5-flash-lite --activate
PYTHONPATH=backend .venv/bin/python scripts/manufacturing_demos.py
PYTHONPATH=backend .venv/bin/python evaluation/language_run.py --mode contract --split all --output evaluation/results/new-contract-run
PYTHONPATH=backend .venv/bin/python scripts/resume_comparison.py --split held_out --output evaluation/results/new-live-run --seconds 20 --max-calls 200
PYTHONPATH=backend .venv/bin/python evaluation/study.py score-usability --input evaluation/study/usability-v2.csv --output .local/study-score.json
```

Use a new output directory when code, model, prompt, schema or dataset identity changes. Identical runs resume cached successes and append attempts; they do not overwrite failed history. `docs/evaluation.md` describes annotations, semantic scoring and the audio study. `docs/demo-script.md` documents the isolated recording server and the explicitly simulated failure.

Machine-readable evidence:

- `evaluation/results/provider-smoke-history.json`: earlier blocked/failed checks and the successful 12-case model test.
- `evaluation/results/language-live-held_out-audited-oct16/`: manifest, per-system cases, append-only attempts, original source inputs, provider caches, pacing and report.
- `evaluation/results/language-live-development-audited-oct16/`: separate development comparison.
- `evaluation/results/language-contract-oct16/` and `engine-all.json`: supplied-claim checks.
- `evaluation/results/manufacturing-demos.json`: three sourced workflow outputs.
- `evaluation/results/usability-pending.json`: zero fabricated participant measurements.
- `artifacts/live-voice-recovery-60s.mp4` and companion JSON: actual integration demonstration.

## Research and remaining limits

The adapter follows Google's [Interactions REST response](https://ai.google.dev/api/interactions-api) and [structured-output documentation](https://ai.google.dev/gemini-api/docs/structured-output). Valid JSON is not proof of correct interpretation. The pinned model passed this account's live checks; [pricing](https://ai.google.dev/gemini-api/docs/pricing) and free quota remain provider/account dependent. The configured free-tier assertion is not an independent billing audit. Gnani [Prisma/Timbre integration](https://docs.gnani.ai/api/introduction/quick-start) remains central to the voice flow.

Outstanding: independent annotation/adjudication, 20 controlled human audio scenarios, semantic answer/citation support, representative user/practitioner validation and voice-versus-form time/omission measurements. Real factory tenancy, ERP integration, damaged-carton arithmetic and AWS deployment remain out of scope. No social post, outreach or competition submission was sent. This report supports an independent re-rating; it does not award itself a score.
