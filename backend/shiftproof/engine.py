"""Pure reconciliation. No model calls, permissions from speech, or implicit releases."""
from datetime import datetime

BATCHES = [
    {'id': 'B-17', 'name': 'Corrugated cartons', 'line': 'Line 01', 'target': 500},
    {'id': 'B-18', 'name': 'Mailer boxes', 'line': 'Line 01', 'target': 240},
    {'id': 'B-19', 'name': 'Retail sleeves', 'line': 'Line 01', 'target': 800},
    {'id': 'B-20', 'name': 'Shipping cartons', 'line': 'Line 02', 'target': 350},
    {'id': 'B-21', 'name': 'Gift boxes', 'line': 'Line 02', 'target': 180},
    {'id': 'B-22', 'name': 'Partition inserts', 'line': 'Line 02', 'target': 600},
]

def active_claims(state, batch_id):
    candidates = [c for c in state['claims'].values() if c['batch_id'] == batch_id and c['status'] not in ('superseded', 'rejected')]
    active = []
    for c in candidates:
        # Explicitly dated old observations remain in history, never overwrite a newer confirmed observation.
        later = [p for p in candidates if c['property'] == 'quantity'
                 and c['modality'] == p['modality'] == 'actual'
                 and not c.get('batch_mismatch') and not p.get('batch_mismatch')
                 and p.get('actor', {}).get('id') == c.get('actor', {}).get('id')
                 and p['property'] == c['property'] and p['status'] == 'confirmed'
                 and p.get('reported_at') and c.get('reported_at')
                 and datetime.fromisoformat(p['reported_at']) > datetime.fromisoformat(c['reported_at'])]
        if not later:
            active.append(c)
    return active

def clarification_progress(state, batch_id, question):
    """Keep the operational question separate from its answer/review progress.

    New unrelated evidence reopens it. Processing/review of the same reply does
    not ask the worker to repeat it or clear the underlying hold.
    """
    if not question:
        return None
    candidates = []
    for note in state['notes'].values():
        context = note.get('clarification_context') or {}
        if (note['batch_id'] == batch_id and note.get('clarification_ref') == question['id']
            and context.get('text') == question['text'] and note['status'] != 'discarded'
            and ((note.get('submitted_at') and note.get('submitted_revision') == note['revision']) or note['status'] in ('manual_review', 'processed'))):
            # A reviewer who explicitly found no operational answer may request it again.
            if (note.get('review_outcome') or {}).get('action') == 'no_operational_claims':
                continue
            candidates.append(note)
    covered = {cid for n in candidates for cid in (n.get('clarification_context') or {}).get('claim_ids', [])}
    covered.update(cid for n in candidates for cid in n.get('claim_ids', []))
    if candidates and set(question.get('claim_ids', [])) <= covered:
        unfinished = any(n['status'] in ('queued', 'processing') for n in candidates)
        claims = [state['claims'][cid] for n in candidates for cid in n.get('claim_ids', []) if cid in state['claims']]
        reviewed = bool(claims) and all(c['status'] in ('confirmed', 'rejected', 'superseded') and not c.get('source_review_pending') for c in claims)
        # Rejected answers do not resolve the question; retained holds still block readiness.
        usable = any(c['status'] == 'confirmed' for c in claims)
        status = 'processing' if unfinished else 'reviewed' if reviewed and usable and all(n['status'] == 'processed' for n in candidates) else 'needs_review'
        if reviewed and not usable:
            return {**question, 'response_status': 'needs_answer', 'response_note_ids': []}
        return {**question, 'response_status': status, 'response_note_ids': [n['id'] for n in candidates]}
    # A sourced current quality result already awaiting review is not a missing answer.
    # Do not use this shortcut when contradictory quality reports exist.
    quality = [c for c in active_claims(state, batch_id) if c['property'] == 'quality' and c['modality'] == 'actual' and not c.get('batch_mismatch') and not c.get('source_review_pending')]
    if question.get('type') == 'quality' and quality and all(c['value'] == 'cleared' for c in quality):
        return {**question, 'response_status': 'needs_review', 'response_note_ids': list(dict.fromkeys(c['note_id'] for c in quality))}
    return {**question, 'response_status': 'needs_answer', 'response_note_ids': []}

def batch_view(state, batch):
    if state.get('profile', 'manufacturing') != 'manufacturing':
        from .profiles import industry_view
        return industry_view(state, batch)
    display_id = batch['id'] if 'work_items' in state else batch['id'][2:]
    claims = active_claims(state, batch['id'])
    actual = [c for c in claims if c['modality'] == 'actual' and not c.get('batch_mismatch')]
    confirmed = [c for c in actual if c['status'] == 'confirmed' and not c.get('source_review_pending')]
    groups = {key: [c for c in actual if c['property'] == key] for key in ('packing', 'quality', 'dispatch', 'quantity', 'task')}
    conflicts = []
    for prop, items in groups.items():
        if prop != 'task' and len({str(c['value']) for c in items}) > 1:
            conflicts.append({'id': f'{batch["id"]}:{prop}', 'type': prop, 'message': f'Conflicting {prop} reports need review', 'claim_ids': [c['id'] for c in items]})
    holds = [c for c in groups['quality'] if c['value'] == 'pending']
    cleared = any(c['property'] == 'quality' and c['value'] == 'cleared' for c in confirmed)
    packed = any(c['property'] == 'packing' and c['value'] == 'complete' for c in confirmed)
    dispatch = [c for c in groups['dispatch'] if c['value'] == 'ready']
    conditional = [c for c in claims if c['modality'] != 'actual']
    mismatches = [c for c in claims if c.get('batch_mismatch')]
    if dispatch and (holds or not cleared or not packed):
        conflicts.append({'id': f'{batch["id"]}:readiness', 'type': 'unmet_condition', 'message': 'Dispatch readiness reported without verified packing and quality clearance', 'claim_ids': [c['id'] for c in dispatch + holds]})
    for c in mismatches:
        conflicts.append({'id': f'{c["id"]}:batch', 'type': 'batch_mismatch', 'message': 'Spoken batch does not match the selected batch', 'claim_ids': [c['id']]})
    unreviewed = [c for c in claims if c['status'] in ('draft', 'disputed') or c.get('source_review_pending')]
    unfinished = [n for n in state['notes'].values() if n['batch_id'] == batch['id'] and n['status'] in ('awaiting_upload', 'received', 'queued', 'processing', 'failed', 'manual_review')]
    pending = [c for c in actual if c['property'] in ('packing', 'dispatch') and c['value'] == 'pending']
    open_tasks = [c for c in groups['task'] if c.get('task_status', 'open') != 'completed' or c.get('completion_review_pending')]
    if holds:
        status = 'hold'
    elif conflicts:
        status = 'conflict'
    elif packed and cleared and not unreviewed and not conditional and not unfinished and not pending and not open_tasks:
        status = 'verified'
    elif claims or unfinished:
        status = 'review'
    else:
        status = 'unknown'
    quantity = [c['value'] for c in confirmed if c['property'] == 'quantity']
    quantity_value = quantity[0] if quantity and len(set(quantity)) == 1 and not any(c['type'] == 'quantity' for c in conflicts) else None
    required_quantity = batch.get('required_dispatch_quantity')
    quantity_shortfall = required_quantity is not None and (quantity_value is None or quantity_value < required_quantity)
    quantity_exception = state.get('quantity_exceptions', {}).get(batch['id'], {})
    exception_actor = quantity_exception.get('actor') or quantity_exception.get('author')
    accepted_quantity = quantity_exception.get('accepted_quantity')
    quantity_waived = bool(quantity_exception.get('reason') and isinstance(exception_actor, dict) and exception_actor.get('id')
        and not quantity_exception.get('revoked') and required_quantity is not None
        and quantity_exception.get('required_dispatch_quantity') == required_quantity
        and isinstance(accepted_quantity, int) and not isinstance(accepted_quantity, bool)
        and 0 <= accepted_quantity < required_quantity and quantity_value is not None and quantity_value >= accepted_quantity)
    if quantity_shortfall and not quantity_waived and status == 'verified':
        status = 'review'
    question, refs, qtype = None, [], None
    if holds or (dispatch and not cleared):
        question = f'बैच {display_id} का quality check clear हुआ है, या अभी pending है?'
        refs = [c['id'] for c in holds + dispatch]
        qtype = 'quality'
    elif any(c['type'] == 'quantity' for c in conflicts):
        question = f'बैच {display_id} में कितने cartons पूरे हुए हैं? सही संख्या बताएं।'
        refs = [c['id'] for c in groups['quantity']]
        qtype = 'quantity'
    elif mismatches:
        question = f'आपने किस batch की बात की है? चुना हुआ batch {display_id} है।'
        refs = [c['id'] for c in mismatches]
        qtype = 'batch'
    elif any(not (c.get('assigned_owner') or c.get('owner')) and c.get('task_status', 'open') == 'open' for c in groups['task']):
        question = 'यह काम अगली shift में कौन करेगा? जिम्मेदार व्यक्ति का नाम बताएं।'
        refs = [c['id'] for c in groups['task'] if not (c.get('assigned_owner') or c.get('owner')) and c.get('task_status', 'open') == 'open']
        qtype = 'owner'
    elif conditional:
        question = 'क्या बताई गई शर्त पूरी हो चुकी है? कृपया उसकी पुष्टि करें।'
        refs = [c['id'] for c in conditional]
        qtype = 'condition'
    elif conflicts:
        question = f'बैच {display_id} की अभी की स्थिति क्या है? विरोधी reports की पुष्टि करें।'
        refs = conflicts[0]['claim_ids']
        qtype = 'conflict'
    clarification = {'id': f'{batch["id"]}:{qtype}', 'text': question, 'claim_ids': refs, 'type': qtype} if question else None
    clarification = clarification_progress(state, batch['id'], clarification)
    tasks = [{'id': c['id'], 'title': str(c['value']), 'owner': c.get('assigned_owner') or c.get('owner'),
              'owner_id': c.get('assigned_owner_id'), 'assigned_owner_id': c.get('assigned_owner_id'),
              'completion_note_id': c.get('completion_note_id'), 'completion_note_revision': c.get('completion_note_revision'),
              'source_review_pending': c.get('source_review_pending', False) or c.get('completion_review_pending', False),
              'status': c.get('task_status', 'open'), 'claim_ids': [c['id']]} for c in groups['task']]
    if holds:
        tasks.insert(0, {'id': f'{batch["id"]}:quality', 'title': 'Verify quality clearance before dispatch', 'owner': 'Quality reviewer', 'status': 'open', 'claim_ids': [c['id'] for c in holds]})
    reasons = []
    def reason(code, text, items=(), notes=()):
        actions = {
            'quality_hold': ('Verify quality clearance before dispatch', 'Quality reviewer'),
            'quality_unknown': ('Review a sourced quality inspection result', 'Quality reviewer'),
            'conflict': ('Compare the cited reports and record a resolution', 'Shift supervisor'),
            'unreviewed': ('Review the reported claims against their sources', 'Shift supervisor'),
            'unfinished_notes': ('Finish processing or interpret the saved transcript', 'Shift supervisor'),
            'packing_unknown': ('Obtain and review an explicit packing completion report', 'Shift supervisor'),
        }
        action, owner = actions.get(code, ('Verify whether the reported work or condition is complete', None))
        if code == 'open_tasks' and len(items) == 1:
            action = str(items[0]['value'])
        if owner is None and len(items) == 1:
            owner = items[0].get('assigned_owner') or items[0].get('owner')
        reasons.append({'code': code, 'text': text, 'next_action': action, 'owner': owner,
                        'claim_ids': [c['id'] for c in items], 'note_ids': list(dict.fromkeys([c['note_id'] for c in items] + [n['id'] for n in notes]))})
    if holds: reason('quality_hold', 'Quality clearance remains pending', holds)
    for conflict in conflicts:
        related = [c for c in claims if c['id'] in conflict['claim_ids']]
        reason('conflict', conflict['message'], related)
        if related and all(c['property'] == 'quality' for c in related):
            reasons[-1]['owner'] = 'Quality reviewer'
    for claim in pending: reason('pending_work', f"{claim['property'].title()} is reported pending", [claim])
    for claim in open_tasks: reason('open_tasks', 'Handover task remains open', [claim])
    for claim in conditional: reason('not_actual', 'Planned or conditional work is not confirmed complete', [claim])
    if unreviewed:
        reason('unreviewed', 'Reported claims still need human review', unreviewed)
        if all(c['property'] == 'quality' and c['value'] == 'cleared' for c in unreviewed):
            reasons[-1]['owner'] = 'Quality reviewer'
            reasons[-1]['next_action'] = 'Review a sourced quality inspection result'
    revised = [c for c in claims if c.get('source_review_pending')]
    if revised: reason('source_revision', 'The source transcript changed; earlier interpretations need explicit review', revised)
    if unfinished: reason('unfinished_notes', 'Saved notes still need processing or review', notes=unfinished)
    if not packed: reason('packing_unknown', 'Packing completion is not human-reviewed', groups['packing'])
    if not cleared and not holds: reason('quality_unknown', 'Quality clearance is not human-reviewed', groups['quality'])
    if quantity_shortfall:
        if quantity_waived:
            reason('quantity_exception', 'Recorded quantity exception: ' + quantity_exception['reason'], groups['quantity'])
        else:
            reason('quantity_required', f'Dispatch requires {required_quantity} units; the human-reviewed quantity is {quantity_value if quantity_value is not None else "unknown"}', groups['quantity'])
            if quantity_exception and not quantity_exception.get('revoked'):
                reason('quantity_exception_review', 'The previous quantity exception does not cover this requirement or reviewed count; a supervisor must review it again', groups['quantity'])
    return {**batch, 'status': status, 'packing': 'complete' if packed and not any(c['property'] == 'packing' for c in pending) else 'unverified', 'quality': 'pending' if holds else ('cleared' if cleared else 'unverified'), 'quantity': quantity_value, 'claims': claims, 'claim_history': [c for c in state['claims'].values() if c['batch_id'] == batch['id']], 'readiness_reasons': reasons, 'conflicts': conflicts, 'clarification': clarification, 'tasks': tasks, 'unreviewed_count': len(unreviewed), 'pending_note_count': len(unfinished), 'evidence_ids': list(dict.fromkeys(c['note_id'] for c in claims))}

def handover(state):
    from .profiles import work_items
    batches = [batch_view(state, batch) for batch in work_items(state)]
    acks = list(state['acknowledgements'].values())
    prior = state['snapshots'].get('previous-shift', {})
    changes = [c for c in state['claims'].values() if c.get('introduced_version', 0) > prior.get('version', 0)]
    return {'shift_id': 'shift-B', 'shift_name': state.get('shift_name', 'Evening handover'), 'version': state['version'], 'batches': batches, 'acknowledgements': [{**a, 'current': a['version'] == state['version']} for a in acks], 'changes': changes, 'previous_shift': prior, 'counts': {'holds': sum(b['status'] == 'hold' for b in batches), 'conflicts': sum(len(b['conflicts']) for b in batches), 'unreviewed': sum(b['unreviewed_count'] for b in batches), 'verified': sum(b['status'] == 'verified' for b in batches)}}

def question_intent(question):
    import re
    import unicodedata
    q = unicodedata.normalize('NFKC', question).lower().strip()
    q = re.sub(r'[?？।.!]', '', q)
    q = re.sub(r'\s+', ' ', q)
    phrases = {
        'changes': {'what changed', 'what has changed', 'what changed since the previous shift', 'kya badla', 'kya badla hai', 'pichli shift se kya badla', 'क्या बदला', 'क्या बदला है', 'पिछली शिफ्ट से क्या बदला'},
        'pending': {'what is pending', 'what is still pending', 'what work is pending', 'what remains unfinished', 'kya pending hai', 'kya baaki hai', 'kya baki hai', 'kya bacha hai', 'क्या बाकी है', 'क्या काम बाकी है', 'क्या पेंडिंग है'},
        'hold': {'why is it held', 'why is this held', 'why is this batch held', 'why is the batch on hold', 'why is this batch on hold', 'why is dispatch pending', 'why is quality pending', 'batch kyun ruka hai', 'ye batch kyun ruka hai', 'quality check kyun pending hai', 'dispatch kyun pending hai', 'यह बैच क्यों रुका है', 'बैच क्यों रुका है', 'डिस्पैच क्यों रुका है', 'इस पर रोक क्यों है', 'इस बैच पर रोक क्यों है'},
    }
    return next((intent for intent, aliases in phrases.items() if q in aliases), None)


def answer_question(state, batch_id, question):
    from .profiles import work_items
    from fastapi import HTTPException
    selected = next((b for b in work_items(state) if b['id'] == batch_id), None)
    if not selected: raise HTTPException(404, 'Work item not found')
    view = batch_view(state, selected)
    intent = question_intent(question)
    items = []
    prior = state.get('snapshots', {}).get('previous-shift')
    comparison = {'id': 'previous-shift', 'version': prior['version']} if prior and 'version' in prior else None

    def add(text, claim_ids=(), note_ids=(), kind='reported', owner=None, presentation=None):
        refs = list(dict.fromkeys(claim_ids))
        notes = list(dict.fromkeys([state['claims'][cid]['note_id'] for cid in refs] + list(note_ids)))
        items.append({'text': text, 'claim_ids': refs, 'note_ids': notes, 'kind': kind, 'owner': owner, 'presentation': presentation})

    def result(answer=None, abstained=False):
        return {'answer': answer if answer is not None else '; '.join(i['text'] for i in items),
                'claim_ids': list(dict.fromkeys(cid for i in items for cid in i['claim_ids'])),
                'abstained': abstained, 'items': items, 'intent': intent, 'comparison_snapshot': comparison}

    if intent == 'changes':
        current_ids = {c['id'] for c in view['claims']}
        labels = {'draft':'Reported - needs review', 'confirmed':'Human-reviewed', 'rejected':'Rejected report', 'superseded':'Superseded report', 'disputed':'Disputed report'}
        for claim in view['claim_history']:
            decisions = [r for r in state['resolutions'].values() if r.get('claim_id') == claim['id'] or claim['id'] in r.get('supersedes', [])]
            changed = max([claim.get('introduced_version', 0)] + [r.get('version', 0) for r in decisions])
            if comparison and changed <= comparison['version']:
                continue
            kind = claim['status'] if claim['status'] in ('superseded','rejected') else 'current' if claim['id'] in current_ids else 'historical'
            label = labels.get(claim['status'], claim['status'])
            detail = f"{claim['property']}: {claim['value']}  -  {label}; {kind}"
            if claim.get('modality','actual') != 'actual': detail += f"; {claim['modality']}"
            if claim.get('condition'): detail += f"; condition: {claim['condition']}"
            add(detail, [claim['id']], kind=kind, presentation={'type': 'history', 'property': claim['property'], 'value': claim['value'], 'status': label, 'kind': kind, 'modality': claim.get('modality', 'actual'), 'condition': claim.get('condition')})
        heading = f"Changes since previous-shift snapshot v{comparison['version']}" if comparison else 'Recorded history (no previous-shift snapshot)'
        return result(heading + ': ' + ('; '.join(i['text'] for i in items) or 'no recorded changes.'))
    if intent in ('pending','hold'):
        for task in view['tasks']:
            if task['status'] != 'open': continue
            owner = task.get('owner') or 'Unassigned'
            add(f"Next action: {task['title']}. Responsible: {owner}", task['claim_ids'], kind='next_action', owner=owner, presentation={'type': 'task', 'action': task['title'], 'generated': task['id'].endswith(':quality'), 'owner': owner})
        for reason in view['readiness_reasons']:
            add(f"{reason['text']}. Next action: {reason['next_action']}. Responsible: {reason['owner'] or 'Unassigned'}",
                reason['claim_ids'], reason['note_ids'], kind=reason['code'], owner=reason['owner'], presentation={'type': 'reason', 'reason': reason['text'], 'action': reason['next_action'], 'code': reason['code'], 'owner': reason['owner']})
        if view['status'] == 'unknown':
            return result('There is not enough human-reviewed information to establish readiness.', abstained=True)
        if not items:
            refs=[c['id'] for c in view['claims'] if c['property'] in ('packing','quality') and c['status']=='confirmed']
            refs = [c['id'] for c in view['claims'] if c['status']=='confirmed']
            add('Required reports are human-reviewed. No unresolved conditions are recorded.', refs, kind='reviewed_status')
        return result()
    return result('I can explain pending work, holds, and recorded changes. This question is outside the supported handover questions.', abstained=True)
