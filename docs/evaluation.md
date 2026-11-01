# Evaluation protocol

There are two datasets. `evaluation/scenarios.json` contains the original 60 supplied-claim engine checks, including related template variants. `evaluation/language_scenarios.json` contains 60 separately authored situations, 20 development and 40 held out. Both were created alongside the implementation; neither has independent human labels yet. The language set is frozen with a SHA-256 file. Related situations stay within one split. A second Hindi speaker must label the held-out cases before viewing predictions.

## Reproducible runs

From the repository root with the editable backend installed:

```sh
.venv/bin/pytest backend/tests -q
.venv/bin/python evaluation/run.py --mode engine
.venv/bin/python evaluation/language_run.py --mode contract --split all --output evaluation/results/new-contract-run
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split development --max-calls 100
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split held_out --max-calls 200
```

Contract mode injects gold extraction solely to test creation, processing, review and reconciliation through the real services in a disposable SQLite database. Its accuracy is not model accuracy. Live mode uses the configured Gemini model for extraction and the full-context baseline. The baseline sees original notes, source IDs, timestamps, questions and external review events, but never gold labels or ShiftProof's extracted claims/state. Both systems receive the versioned, independently frozen questions from `clarification_inputs.json`. If the actual ShiftProof workflow cannot produce its required question, that system records a failure; the baseline still runs against the frozen input. Ablation uses the same extracted claims and removes correction/condition handling. Authorization and snapshot features are assessed separately from language accuracy.

Runs persist source/model/prompt/schema keyed responses and daily request counters. Successful cached responses are visibly labeled replay. Identity includes dataset, model, prompt and implementation hashes; a changed run must use a new output directory. Do not overwrite results to hide failures. No provider or model fallback occurs. There are two network attempts total per processing attempt, shared by transient retries and output repair. Quota/auth failures do not retry inside that attempt. The request budget includes failed calls; free service quotas may be lower. Each system has an independent result and append-only attempt history. Case-specific extraction failures do not suppress the baseline; shared quota/auth failures pause work explicitly. Resume after service availability returns. A complete comparison requires all requested systems on every case. Do not run multiple comparisons concurrently against a small requests-per-minute allowance.

State accuracy requires both status and quantity. The requested denominator includes unavailable cases, while all-unavailable results remain null. Conflict precision/recall use completed cases and report TP/FP/FN. Coverage counts unavailable answerable cases as unanswered. Report false-ready counts with completed denominators, a separate pre-final-review diagnostic, and unsupported quality-clearance extractions. Valid IDs/exact excerpts do not establish entailment; semantic evidence and answer correctness remain pending human annotation. Targets are 90% state accuracy, 85% conflict precision/recall, 80% answer coverage and a 10-point correction/condition gain over the matched baseline, not claimed achievements.

Stage timings separate transcription, extraction and reconciliation; speech responses include TTS Server-Timing. Cached runs and contract checks do not measure live latency. Recording-stop-to-visible-result p50/p95 is unmeasured until the audio study, and deliberate transcript-inspection time must be reported separately.

## Independent labels and human audio

`evaluation/study/blind-annotations.jsonl` omits gold labels and predictions. Give it to the second speaker before sharing model outputs. Keep their labels unchanged; preserve disagreements and adjudication in separate fields. Do not edit the frozen dataset in response to predictions. Publish an explicitly versioned adjudicated dataset if labels change. The implementation author's labels are not an independent review.

`evaluation/audio_manifest.json` assigns eight development scenarios to speaker-a and twelve held-out scenarios to speaker-b. Have consenting speakers record each fictional note in mono PCM WAV. Store consent references privately. Add recording entries with `scenario_id`, `note_id`, `speaker_id`, `consent_record`, `path`, `split`, and `variant` (`clean`, `noise`, or `8khz`). `prepare_audio.py` generates controlled white-noise and low-pass 8 kHz copies; register each copy in the same split. These are simulations, not factory/telephone recordings. Synthetic speech is excluded from human evidence.

```sh
.venv/bin/python evaluation/audio_run.py --max-calls 10
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split held_out --audio-variant gold
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split held_out --audio-variant clean
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split held_out --audio-variant noise
EXTRACTION_PROVIDER=gemini .venv/bin/python evaluation/language_run.py --mode live --split held_out --audio-variant 8khz
```

The audio runner validates assignments and consent references, caches Prisma transcripts by audio hash, and preserves missing/failed inputs. Gold and Prisma variants use the same assigned cases. Do not count existing development recordings toward the independent study.

For answer/evidence review after a live run:

```sh
.venv/bin/python evaluation/study.py semantic-sheet --run-dir evaluation/results/language-live-held_out
# A Hindi reviewer fills reviewer_id, answer_correct, evidence_entails_answer and reason.
.venv/bin/python evaluation/study.py score-semantics --run-dir evaluation/results/language-live-held_out
```

The original model report remains unchanged; semantic results are saved separately with their reviewed-subset denominator. Study preparation refuses to overwrite existing participant sheets.

## Usability exercise

Use the new `evaluation/study/usability-v2.csv` (the original worksheet is preserved) to counterbalance raw transcripts versus ShiftProof and voice capture versus manual claim entry. Record each assignment as pending, completed or failed, including participant background. Enter numerator/denominator pairs for missed tasks, false-ready decisions, claim corrections, supporting-source retrieval and latest-version acknowledgements. Enter capture, understanding and source-finding seconds separately, plus transcript-edit counts. Blank fields are unmeasured, never zero. With two speakers this is a formative exercise, not representative factory validation. No study participants, consent, scores or time savings are fabricated.


```sh
PYTHONPATH=backend .venv/bin/python evaluation/study.py score-usability --input evaluation/study/usability-v2.csv --output .local/study-score.json
STUDY_PARTICIPANT=speaker-a node scripts/study-browser.mjs
# Perform an assigned task in the opened private localhost browser, then close it.
PYTHONPATH=backend .venv/bin/python evaluation/timing.py --input .local/study-sessions/<session>/events.jsonl --output .local/study-sessions/<session>/timings.json
```

The harness is opt-in and refuses non-local hosts. No participant telemetry is stored by the application or sent from the public demo. `performance.now()` measures intervals within a document. The report separates transcript inspection from processing and includes failed/incomplete attempt counts. Playback timing is request-to-available and request-to-start; human comprehension still requires the worksheet. Automated browser tests and walkthrough recordings are not participant sessions.

Semantic review packets contain randomized opaque IDs, original transcripts, questions, review events, answers and cited note IDs. System mappings are stored separately in ignored `.local/study-mappings/` with owner-only permissions. Do not share them until review ends; wording can still reveal a system. Packet scoring rejects altered source payloads and duplicate/removed entries. Keep independent gold-label annotation separate and complete it before showing predictions.

The 12 development-only answer checks in `answer_checks.json` cover four cases per question group, including unrelated questions that must abstain. They are regression checks, not held-out model results. `scripts/manufacturing_demos.py` uses isolated SQLite and explicitly labeled fixtures to demonstrate production, quality and dispatch behavior.

Resume the audited October 16 runs without changing their identities:

```sh
PYTHONPATH=backend .venv/bin/python evaluation/language_run.py --mode live --split development --output evaluation/results/language-live-development-audited-oct16 --max-calls 200
PYTHONPATH=backend .venv/bin/python evaluation/language_run.py --mode live --split held_out --output evaluation/results/language-live-held_out-audited-oct16 --max-calls 200
```

The dashboard loads the explicitly selected report from `evaluation/results/published-language-run.json`; it does not treat another model's historical results as a current smoke test. After resuming a run, create a new blinded review packet with a separate mapping for newly completed responses; preserve existing annotations.

To reduce free-tier rate-limit interruptions, pace system attempts without changing model logic or cached identities:

```sh
PYTHONPATH=backend .venv/bin/python scripts/resume_comparison.py --split held_out --output evaluation/results/language-live-held_out-audited-oct16 --seconds 20 --max-calls 200
```

`pacing.json` discloses the delay. Provider-stage timings exclude this outer wait; per-system wall time includes it. Failed quota calls remain in attempt history. A shared quota failure still pauses the invocation; the script does not loop around quota errors.

The audited runs preserve original capture directories and revalidate their successful, content-addressed provider responses through the real services. Their manifests explicitly hash both extraction and baseline schemas. Old derived state is not imported. The before-final-review diagnostic uses the fact that every scenario has an unreviewed final note; final reviewed readiness is not its gold label. This policy diagnostic is separate from language accuracy.
