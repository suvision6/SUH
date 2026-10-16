#!/usr/bin/env python3
"""Local previs request/asset ledger. No model call, installation or human authentication.

Preparation uses standard library. Register/export need Pillow; PDF also needs
ReportLab and a local embeddable font. The CLI reads one operation JSON from disk.
"""
import argparse
import copy
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from deliver import load, prepare, records, require, nonempty, unique_object


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def now():
    return datetime.now(timezone.utc).isoformat()


def load_snapshot(path):
    """Parse and identify exactly the same bytes, preserving strict JSON rules."""
    raw = Path(path).read_bytes()
    def bad_number(value):
        raise ValueError('non-finite JSON value: ' + value)
    return raw, json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=bad_number)


def save_new(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as f:
        f.write(raw)
    require(path.read_bytes() == raw, 'saved bytes mismatch')


def save_identical(path, raw):
    """Resume a local interrupted write only when the exact bytes agree."""
    path = Path(path)
    if path.exists():
        require(path.is_file() and path.read_bytes() == raw, 'interrupted asset differs; preserve both and inspect: ' + str(path))
    else:
        save_new(path, raw)


def evidence(data):
    for key in ('evidence_ref', 'evidence_text'):
        nonempty(data.get(key), key)
    return {k: data[k] for k in ('evidence_ref', 'evidence_text')}


def image_read(path):
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        require(getattr(im, 'n_frames', 1) == 1, 'single still image required')
        im.load()
        im = ImageOps.exif_transpose(im)
        if 'A' in im.getbands() or 'transparency' in im.info:
            rgba = im.convert('RGBA')
            base = Image.new('RGBA', rgba.size, 'white')
            im = Image.alpha_composite(base, rgba).convert('RGB')
        else:
            im = im.convert('RGB')
        return im.copy()


def grid(page):
    """Page layout as (rows, cols). Absent layout keeps the 3x3 default."""
    layout = page.get('layout') or {'rows': 3, 'cols': 3}
    require(isinstance(layout, dict) and set(layout) <= {'rows', 'cols'}, 'layout needs only rows/cols')
    rows, cols = layout.get('rows'), layout.get('cols')
    require(type(rows) is int and type(cols) is int and 1 <= rows <= 4 and 1 <= cols <= 4,
            'layout rows/cols must be integers 1-4')
    return rows, cols


def page_assembly(page):
    """Snapshot effective layout and every slot, including unused positions."""
    rows, cols = grid(page)
    return {'layout': {'rows': rows, 'cols': cols}, 'slots': list(page['slots'])}


def catalog(bundle):
    rendered = prepare(bundle)
    require(bundle['kind'] == 'previs', 'previs bundle required')
    media = bundle.get('media', {})
    panels = records(media.get('panels'), 'media.panels')
    pages = records(media.get('pages'), 'media.pages')
    sources = {s['id']: s for s in bundle['source_units']}
    seen = []
    for p in panels.values():
        for k in ('shot_id', 'moment', 'current_input'):
            nonempty(p.get(k), 'panel ' + k)
        require(p.get('relation') in ('first', 'same_shot', 'cut', 'ellipsis', 'alternative'), 'invalid relation')
        refs = p.get('source_ids')
        require(isinstance(refs, list) and refs and len(refs) == len(set(refs)), 'panel source_ids required')
        require(all(r in sources for r in refs), 'unknown panel source')
        for key, text in p.get('facets', {}).items():
            nonempty(key, 'facet dimension')
            nonempty(text, 'facet text')
    for pg in pages.values():
        require(pg.get('item_id') in rendered, 'page needs existing item_id')
        slots = pg.get('slots')
        rows, cols = grid(pg)
        require(isinstance(slots, list) and len(slots) == rows * cols,
                'page requires rows*cols slots (default 3x3 = 9), null means UNUSED')
        require(any(slots), 'page has no active panel')
        for panel in slots:
            require(panel is None or panel in panels, 'unknown panel in page')
            if panel is not None:
                seen.append(panel)
        # Page body is generated from the same saved copy text, not re-authored here.
    require(len(seen) == len(set(seen)) and set(seen) == set(panels), 'all panels must occur exactly once; stable IDs cannot duplicate')
    return panels, pages, sources, rendered


def panel_basis(bundle, panel, sources):
    # Exclude page/slot so repagination does not re-identify or re-approve images.
    return digest(canonical({'panel': panel, 'conditions': bundle.get('conditions', {}),
                             'sources': [sources[s] for s in panel['source_ids']]}))


def derivation_snapshot(bundle, item_id):
    panels, pages, _, rendered = catalog(bundle)
    ids = [pid for page in pages.values() if page['item_id'] == item_id for pid in page['slots'] if pid]
    return {'body_sha256': digest(canonical(rendered[item_id]['body'])),
            'copy_text': rendered[item_id]['copy_text'],
            'panel_inputs': {pid: panels[pid]['current_input'] for pid in ids}}


def update_derivation(state, bundle):
    """Track unreviewed derivation, independently of whether images need replacing."""
    _, pages, _, rendered = catalog(bundle)
    old_rendered = prepare(state['bundle'])
    pending = state.setdefault('derivation_pending', {})
    resolved = state.setdefault('derivation_resolved', {})
    for iid in {page['item_id'] for page in pages.values()}:
        target = digest(canonical(rendered[iid]['body']))
        changed = iid in old_rendered and old_rendered[iid]['body'] != rendered[iid]['body']
        flagged = iid in bundle.get('derivation_pending', {}) and resolved.get(iid) != target
        if changed or flagged:
            if iid not in pending:
                basis = state['bundle'] if iid in old_rendered else bundle
                pending[iid] = derivation_snapshot(basis, iid)
            pending[iid]['target_body_sha256'] = target


def pending_for(state, panel_ids):
    _, pages, _, _ = catalog(state['bundle'])
    return sorted({p['item_id'] for p in pages.values()
                   if set(panel_ids).intersection(p['slots']) and p['item_id'] in state.get('derivation_pending', {})})


def unresolved_panels(request):
    if request['status'] not in ('submitting', 'submitted', 'unknown', 'succeeded') or request.get('received'):
        return set()
    archived = request.get('archived', {}) if request['status'] == 'succeeded' else {}
    return set(request['panel_ids']) - set(archived)


def reference_records(refs):
    result = []
    for r in refs:
        nonempty(r.get('purpose'), 'reference purpose')
        p = Path(r['path']).expanduser().resolve()
        require(p.is_file(), 'reference is not a readable file: ' + str(p))
        image_read(p)
        result.append({'path': str(p), 'sha256': digest(p.read_bytes()), 'purpose': r['purpose'],
                       'attachment': 'not_yet_submitted'})
    return result


def initialize(root, bundle_path, test_mode=False):
    root = Path(root)
    require(not root.exists(), 'new workspace required')
    source = Path(bundle_path).resolve()
    bundle = load(source)
    panels, _, sources, _ = catalog(bundle)
    root.mkdir(parents=True)
    state = {'format': 'suh-previs-media-ledger/1', 'test_mode': bool(test_mode),
             'bundle': bundle, 'bundle_origin': str(source), 'bundle_sha256': digest(source.read_bytes()),
             'panels': {pid: {'basis': panel_basis(bundle, p, sources), 'versions': [], 'selected': None}
                        for pid, p in panels.items()}, 'requests': {}, 'events': []}
    update_derivation(state, bundle)
    save_new(root / 'Ledger.json', canonical(state))
    save_new(root / 'Snapshots' / 'Bundle-0001.json', canonical(bundle))
    return {'workspace': str(root.resolve()), 'panels': len(panels), 'test_mode': bool(test_mode)}


@contextmanager
def locked(root):
    root = Path(root)
    lock = root / 'Ledger.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise ValueError('Ledger.lock exists; inspect the task and lock before recovery; do not auto-clear') from None
    try:
        os.close(fd)
        raw, state = load_snapshot(root / 'Ledger.json')
        yield state
        require((root / 'Ledger.json').read_bytes() == raw, 'ledger changed concurrently')
        updated = canonical(state)
        if updated != raw:
            # A previous interrupted temporary remains evidence, never a commit source.
            with tempfile.NamedTemporaryFile(dir=root, prefix='Ledger-', suffix='.tmp', delete=False) as f:
                temp = Path(f.name)
                f.write(updated)
                f.flush()
                os.fsync(f.fileno())
            require(temp.read_bytes() == updated, 'ledger temporary readback mismatch')
            require((root / 'Ledger.json').read_bytes() == raw, 'ledger changed concurrently')
            os.replace(temp, root / 'Ledger.json')
    finally:
        lock.unlink()  # One exact owned lock file, never recursive deletion.


def request_current(state, req):
    _, pages, _, rendered = catalog(state['bundle'])
    same = not pending_for(state, req['panel_ids']) and all(state['panels'][p]['basis'] == b for p,b in req['basis'].items())
    if req.get('page_id'):
        page = pages.get(req['page_id'])
        # Legacy page requests lack assembly evidence: preserve them, but do not
        # infer their historical layout from the current bundle.
        same = (same and bool(page) and req.get('page_assembly') == page_assembly(page)
                and [x for x in page['slots'] if x] == req['panel_ids']
                and rendered[page['item_id']]['copy_text'] == req['prompt'])
    return same


def prepared_input(state, op):
    """The existing input contract, shared by prepare and explicit local recovery."""
    rid = op['id']
    records([{'id': rid}], 'request')
    require(('page_id' in op) != ('panel_id' in op), 'choose one page OR panel')
    panels, pages, _, rendered = catalog(state['bundle'])
    if 'page_id' in op:
        page = pages[op['page_id']]
        ids = [x for x in page['slots'] if x is not None]
        text = rendered[page['item_id']]['copy_text']
    else:
        ids = [op['panel_id']]
        text = panels[ids[0]]['current_input']
    require(not pending_for(state, ids), 'drawing derivation pending: resolve affected body/page/panel inputs')
    payload = {'id': rid, 'panel_ids': ids, 'prompt': text,
               'references': reference_records(op.get('references', [])),
               'parameters': op.get('parameters', {}),
               'basis': {p: state['panels'][p]['basis'] for p in ids},
               'page_id': op.get('page_id'), 'panel_id': op.get('panel_id')}
    if 'page_id' in op:
        payload['page_assembly'] = page_assembly(page)
    payload['input_sha256'] = digest(canonical(payload))
    return payload


def recover_prepare(root, state, op):
    """Restore only a witnessed pre-submission local interruption, never a host call."""
    require(op.get('interruption') == 'before_host_submission',
            'explicit before_host_submission evidence required; unknown submission must be queried')
    ev = evidence(op)
    expected = prepared_input(state, op)
    rid = expected['id']
    path = root / 'Requests' / (rid + '.json')
    original_raw, original = load_snapshot(path)
    allowed = set(expected) | {'status', 'created', 'prepared_from_ledger_sha256'}
    require(set(original) == allowed and original.get('status') == 'prepared',
            'not an intact recoverable preparation; preserve and inspect')
    nonempty(original.get('created'), 'original creation time')
    require({k: original[k] for k in expected} == expected, 'recovery input differs; preserve original request')
    original_input = {k: original[k] for k in expected if k != 'input_sha256'}
    require(digest(canonical(original_input)) == original['input_sha256'], 'request input digest mismatch')
    require(not list((root / 'Responses').glob(rid + '-*.json')) and not (root / 'Archived' / rid).exists(),
            'submission/result evidence exists; query existing call, do not recover as prepared')
    existing = state['requests'].get(rid)
    if existing is not None:
        recovery = existing.get('preparation_recovery', {})
        require(existing.get('status') == 'prepared' and
                recovery.get('request_file_sha256') == digest(original_raw) and
                {k: existing.get(k) for k in expected} == expected,
                'request already exists or advanced; do not roll back submission state')
        return {'request_id': rid, 'recovery': 'already_completed', 'host_invoked': False}, True
    require(original.get('prepared_from_ledger_sha256') == digest((root / 'Ledger.json').read_bytes()),
            'preparation ledger basis differs or is legacy; preserve and inspect')
    require(not any(e.get('scope', {}).get('request_id') == rid for e in state['events']),
            'request history exists; do not reconstruct as unsubmitted')
    restored = dict(original)
    restored['preparation_recovery'] = dict(ev, request_file_sha256=digest(original_raw), at=now(),
        boundary='declared pre-host local interruption; not verification of host history')
    state['requests'][rid] = restored
    return {'request_id': rid, 'recovery': 'restored_prepared', 'input_sha256': original['input_sha256'],
            'host_invoked': False}, False


def version(root, state, pid, _read_bytes=None):
    read_bytes = Path.read_bytes if _read_bytes is None else _read_bytes
    panel = state['panels'][pid]
    matches = [v for v in panel['versions'] if v['revision'] == panel['selected']]
    if not matches:
        return None, ['missing']
    v = matches[0]
    problems = []
    if pending_for(state, [pid]):
        problems.append('derivation_pending')
    for path_key, hash_key in (('path', 'sha256'), ('raw_path', 'raw_sha256')):
        file = Path(root) / v[path_key]
        if not file.is_file() or digest(read_bytes(file)) != v[hash_key]:
            problems.append('changed_or_missing_' + path_key)
    if v['basis'] != panel['basis']:
        problems.append('stale_basis')
    if v.get('request_id'):
        req = state['requests'][v['request_id']]
        if req.get('page_id') and 'page_assembly' not in req:
            problems.append('page_assembly_unverified')
        elif not request_current(state, req):
            problems.append('stale_execution_input')
    for r in v.get('references', []):
        file = Path(r['path'])
        if not file.is_file() or digest(read_bytes(file)) != r['sha256']:
            problems.append('changed_or_missing_reference')
    return v, problems


def store_image(root, state, pid, im, raw, request, box=None, import_evidence=None):
    root = Path(root)
    panel = state['panels'][pid]
    rid = 'r%03d' % (len(panel['versions']) + 1)
    raw_hash = digest(raw)
    raw_path = 'Assets/Raw/' + raw_hash + '.bin'
    if not (root / raw_path).exists():
        save_new(root / raw_path, raw)
    else:
        require((root / raw_path).read_bytes() == raw, 'stored original corrupted')
    buf = io.BytesIO()
    im.save(buf, format='PNG')
    name = 'Assets/' + pid + '/' + rid + '.png'
    receipt = {'panel_id': pid, 'revision': rid, 'raw_sha256': raw_hash,
               'sha256': digest(buf.getvalue()), 'basis': panel['basis'], 'crop_box': box,
               'request_id': request['id'] if request else None,
               'request_sha256': request.get('input_sha256') if request else None,
               'import_evidence': import_evidence}
    save_identical(root / 'Assets' / pid / (rid + '-receipt.json'), canonical(receipt))
    save_identical(root / name, buf.getvalue())
    v = {'revision': rid, 'path': name, 'sha256': digest(buf.getvalue()), 'raw_path': raw_path,
         'raw_sha256': raw_hash, 'width': im.width, 'height': im.height, 'crop_box': box,
         'basis': panel['basis'], 'request_id': request['id'] if request else None,
         'request_sha256': request.get('input_sha256') if request else None,
         'references': copy.deepcopy(request.get('references', [])) if request else [],
         'import_evidence': import_evidence, 'agent_observations': [], 'decisions': [], 'created': now()}
    panel['versions'].append(v)
    panel['selected'] = rid
    return v


def operate(root, op):
    root = Path(root)
    action = op['action']
    if action == 'status':
        state = load(root / 'Ledger.json')
        panels, pages, _, _ = catalog(state['bundle'])
        return {'test_mode': state['test_mode'], 'panels': {p: {'selected': state['panels'][p]['selected'],
                 'problems': version(root, state, p)[1]} for p in panels},
                'derivation_pending': sorted(state.get('derivation_pending', {})),
                'requests': {r: {'status': q['status'], 'task_id': q.get('task_id'),
                                'input_current': request_current(state, q),
                                'legacy_page_assembly_missing': bool(q.get('page_id') and 'page_assembly' not in q),
                                'archived_panels': sorted(q.get('archived', {})),
                                'next': 'query_or_recover_existing_call; do_not_resubmit' if unresolved_panels(q) else 'follow_saved_state'}
                             for r, q in state['requests'].items()},
                'unused_slots': {p: [i + 1 for i, v in enumerate(q['slots']) if v is None] for p, q in pages.items()}}
    with locked(root) as state:
        panels, pages, sources, rendered = catalog(state['bundle'])
        result = {}
        if action == 'sync':
            bundle = load(op['bundle'])
            np, _, ns, _ = catalog(bundle)
            require(set(np) == set(panels), 'panel additions/removals require a new media workspace; do not silently migrate identity')
            update_derivation(state, bundle)
            changed = []
            for pid, p in np.items():
                new = panel_basis(bundle, p, ns)
                if new != state['panels'][pid]['basis']:
                    changed.append(pid)
                state['panels'][pid]['basis'] = new
            state['bundle'] = bundle
            state['bundle_origin'] = str(Path(op['bundle']).resolve())
            state['bundle_sha256'] = digest(Path(op['bundle']).read_bytes())
            n = len(list((root / 'Snapshots').glob('Bundle-*.json'))) + 1
            save_new(root / 'Snapshots' / ('Bundle-%04d.json' % n), canonical(bundle))
            result = {'changed_basis': changed, 'old_versions_preserved': True,
                      'derivation_pending': sorted(state.get('derivation_pending', {}))}
        elif action == 'resolve-derivation':
            reviews = op.get('items')
            require(isinstance(reviews, list) and reviews, 'explicit derivation item scope required')
            seen = set()
            for review in reviews:
                iid = review['item_id']
                require(iid not in seen and iid in state.get('derivation_pending', {}), 'unknown/duplicate pending item')
                seen.add(iid)
                nonempty(review.get('note'), 'specific professional derivation explanation')
                before = state['derivation_pending'][iid]
                current = derivation_snapshot(state['bundle'], iid)
                require(current['body_sha256'] == before['target_body_sha256'], 'derivation target changed')
                copy_changed = current['copy_text'] != before['copy_text']
                panels_changed = current['panel_inputs'] != before['panel_inputs']
                if review.get('outcome') == 'updated':
                    require(copy_changed and panels_changed, 'update affected page copy and panel input before resolving')
                else:
                    require(review.get('outcome') == 'no_visual_change', 'outcome must be updated or no_visual_change')
                    require(not copy_changed and not panels_changed, 'drawing inputs changed; cannot claim no visual change')
                state.setdefault('derivation_resolved', {})[iid] = current['body_sha256']
                del state['derivation_pending'][iid]
            result = {'resolved': sorted(seen), 'image_regeneration_required_by_resolution': False}
            state.setdefault('derivation_reviews', []).append({'at': now(), 'items': copy.deepcopy(reviews)})
        elif action == 'prepare':
            rid = op['id']
            records([{'id': rid}], 'request')
            require(rid not in state['requests'], 'request id already exists')
            payload = prepared_input(state, op)
            payload.update(status='prepared', created=now(),
                           prepared_from_ledger_sha256=digest((root / 'Ledger.json').read_bytes()))
            state['requests'][rid] = payload
            save_new(root / 'Requests' / (rid + '.json'), canonical(payload))
            result = payload
        elif action == 'recover-prepare':
            result, already = recover_prepare(root, state, op)
            if already:
                return result
        elif action == 'authorize':
            req = state['requests'][op['request_id']]
            require(req['status'] == 'prepared', 'only prepared request can be authorized')
            require(set(op['panel_ids']) == set(req['panel_ids']), 'authorization scope must exactly match prepared target')
            req['authorization'] = evidence(op)
            req['authorization']['input_sha256'] = req['input_sha256']
            result = {'authorized_request': req['id']}
        elif action == 'start':
            req = state['requests'][op['request_id']]
            require(req['status'] == 'prepared' and req.get('authorization'), 'prepared authorized request required')
            require(request_current(state,req), 'prepared input is stale')
            for q in state['requests'].values():
                require(q is req or not (unresolved_panels(q) & set(req['panel_ids'])), 'overlapping unresolved call; query/recover, do not duplicate')
            for ref in req['references']:
                require(Path(ref['path']).is_file() and digest(Path(ref['path']).read_bytes()) == ref['sha256'], 'reference changed before submit')
            nonempty(op.get('tool'), 'actual host tool name')
            require(isinstance(op.get('capabilities'), dict), 'record observed host tool capabilities')
            attached = op.get('attached_references', [])
            require(len(attached) == len(req['references']) and set(attached) == {r['sha256'] for r in req['references']}, 'all planned refs must actually be attached; no silent downgrade')
            req.update(status='submitting', tool=op['tool'], capabilities=op['capabilities'],
                       attached_references=attached, started=now())
            result = {'next': 'invoke named host tool once with saved input; then record actual return', 'request_id': req['id']}
        elif action == 'result':
            req = state['requests'][op['request_id']]
            require(req['status'] in ('submitting','submitted','unknown','succeeded'), 'no in-flight call')
            require(op.get('status') in ('submitted','unknown','succeeded','failed','cancelled'), 'invalid return status')
            nonempty(op.get('record_ref'), 'actual response/evidence reference')
            req.setdefault('results', []).append({k: op[k] for k in op if k not in ('action','request_id')})
            req.update(status=op['status'], task_id=op.get('task_id', req.get('task_id')),
                       model_reported=op.get('model_reported', 'not_exposed'))
            if 'response_file' in op:
                raw = Path(op['response_file']).read_bytes()
                name = 'Responses/' + req['id'] + '-' + digest(raw) + '.json'
                if not (root / name).exists():
                    save_new(root / name, raw)
                req['results'][-1]['saved_response'] = name
        elif action == 'archive':
            request = state['requests'][op['request_id']]
            require(request['status'] == 'succeeded' and not request.get('received'), 'known successful unreceived result required')
            require(not request_current(state, request), 'current result should use register, not stale archive')
            ids = op.get('panel_ids', request['panel_ids'])
            require(ids and len(ids) == len(set(ids)) and set(ids) <= unresolved_panels(request), 'archive only unreceived requested panels')
            raw = Path(op['image']).read_bytes()
            image_read(op['image'])
            name = 'Archived/' + request['id'] + '/' + digest(raw) + '.bin'
            save_identical(root / name, raw)
            for pid in ids:
                request.setdefault('archived', {})[pid] = {
                    'path': name, 'sha256': digest(raw), 'basis': request['basis'][pid],
                    'request_sha256': request['input_sha256'], 'selected_as_current': False}
            result = {'archived_panels': ids, 'unreceived_panels': sorted(unresolved_panels(request)),
                      'selected_as_current': False}
        elif action == 'register':
            request = state['requests'].get(op.get('request_id'))
            if request:
                require(request['status'] == 'succeeded' and not request.get('received'), 'successful unreceived result required')
                require(not request.get('archived'), 'partially archived old result must finish archival')
                ids = request['panel_ids']
                require(request_current(state,request), 'returned image uses stale input; preserve externally, do not register as current')
                import_evidence = None
            else:
                require('request_id' not in op, 'unknown request id')
                require(op.get('origin') in ('user_supplied', 'synthetic_fixture'), 'explicit import origin required')
                require(op['origin'] != 'synthetic_fixture' or state['test_mode'], 'synthetic images only in marked test workspace')
                ids = op['panel_ids']
                require(ids and len(ids) == len(set(ids)) and set(ids) <= set(panels), 'invalid imported panels')
                import_evidence = dict(evidence(op), origin=op['origin'])
            raw = Path(op['image']).read_bytes()
            im = image_read(op['image'])
            boxes = op.get('boxes')
            require((len(ids) == 1 and not (request and request.get('page_id'))) or boxes is not None, 'sheet registration needs observed boxes even with one active slot; no equal-thirds crop')
            if boxes is not None:
                require(set(boxes) == set(ids), 'boxes must match actual target panel IDs, excluding unused slots')
                rects = []
                for pid in ids:
                    b = boxes[pid]
                    require(isinstance(b,list) and len(b)==4 and all(type(v) is int for v in b), 'pixel boxes need four integers')
                    l,t,r,bt = b
                    require(0<=l<r<=im.width and 0<=t<bt<=im.height, 'crop outside image')
                    require(all(not(min(r,x[2])>max(l,x[0]) and min(bt,x[3])>max(t,x[1])) for x in rects), 'overlapping boxes')
                    rects.append(b)
                if request and request.get('page_id'):
                    slots = pages[request['page_id']]['slots']
                    cols = grid(pages[request['page_id']])[1]
                    for a in ids:
                        for b in ids:
                            ia, ib = slots.index(a), slots.index(b)
                            if ia >= ib: continue
                            ba, bb = boxes[a], boxes[b]
                            if ia // cols == ib // cols:
                                require(ba[0]+ba[2] < bb[0]+bb[2], 'boxes reverse page reading order')
                            if ia % cols == ib % cols:
                                require(ba[1]+ba[3] < bb[1]+bb[3], 'boxes reverse column reading order')
            saved = {}
            for pid in ids:
                box = boxes[pid] if boxes else None
                v = store_image(root,state,pid,im.crop(tuple(box)) if box else im,raw,request,box,import_evidence)
                saved[pid] = v['revision']
            if request:
                request['received'] = saved
            result = saved
        elif action in ('observe', 'adopt'):
            ids = op['panel_ids']
            require(ids and len(ids)==len(set(ids)) and set(ids)<=set(panels), 'invalid observation/adoption scope')
            versions = {}
            for pid in ids:
                v, problems = version(root,state,pid)
                require(not problems, pid + ': ' + ','.join(problems))
                versions[pid] = v
            if action == 'observe':
                require(op.get('status') in ('checked','needs_changes','not_visible'), 'invalid observation status')
                nonempty(op.get('observed'), 'specific visible observation')
                nonempty(op.get('view_ref'), 'actual view tool/output reference')
                for v in versions.values():
                    v['agent_observations'].append({k:op[k] for k in ('status','observed','view_ref')})
            else:
                ev = evidence(op)
                dims = op['dimensions']
                require(dims and len(dims)==len(set(dims)), 'explicit nonduplicate adoption dimensions required')
                require(op.get('decision') in ('approved','changes_requested'), 'invalid human decision')
                for pid,v in versions.items():
                    require(set(dims)<=set(panels[pid].get('facets',{})), 'each adopted dimension needs authored facet text, not just a checkbox')
                    v['decisions'].append(dict(ev, dimensions=dims, decision=op['decision'], image_sha256=v['sha256'], basis=v['basis'], time=now()))
                result = {'adopted_facets': {p:{d:panels[p]['facets'][d] for d in dims} for p in ids} if op['decision']=='approved' else {}}
        elif action == 'select':
            panel = state['panels'][op['panel_id']]
            require(any(v['revision']==op['revision'] for v in panel['versions']), 'unknown revision')
            panel['selected'] = op['revision']
        else:
            raise ValueError('unknown operation: ' + action)
        scope = {k:op[k] for k in ('request_id','panel_ids','panel_id') if k in op}
        if action == 'recover-prepare':
            scope['request_id'] = op['id']
            if 'page_id' in op:
                scope['page_id'] = op['page_id']
        state['events'].append({'at':now(),'action':action,'scope':scope})
        return result


def approved(v, dims):
    decisions = {}
    for d in v['decisions']:
        if d['image_sha256']==v['sha256'] and d['basis']==v['basis']:
            for dimension in d['dimensions']:
                decisions[dimension] = d['decision']
    return all(decisions.get(dim)=='approved' for dim in dims)


def export(root, output, stage='review', formats=('html',), page_ids=None, dimensions=('content',), font=None):
    import base64
    import html
    import time
    started = time.perf_counter()
    root, output = Path(root), Path(output)
    require(stage in ('review','adopted'), 'stage review or adopted required')
    require(set(formats)<=set(('html','pdf')) and formats, 'choose html and/or pdf')
    require(not output.exists(), 'new export directory required')
    ledger_raw, state = load_snapshot(root/'Ledger.json')
    panels,pages,_,_=catalog(state['bundle'])
    chosen = list(pages) if page_ids is None else page_ids
    require(chosen and len(chosen)==len(set(chosen)) and set(chosen)<=set(pages), 'invalid page subset')
    selections = {}
    captured = {}
    def read_once(path):
        path = Path(path)
        if path not in captured:
            captured[path] = path.read_bytes()
        return captured[path]
    for pg in chosen:
        for pid in pages[pg]['slots']:
            if pid is None:
                continue
            v, problems = version(root,state,pid,_read_bytes=read_once)
            if stage=='adopted':
                require(v and not problems and approved(v,dimensions), 'adopted export blocked: missing/stale/unapproved ' + pid)
            selections[pid] = {'version':v, 'problems':problems,
                               'image_bytes':captured.get(root/v['path']) if v else None}
    label = ('SYNTHETIC TEST / ' if state['test_mode'] else '') + stage.upper()
    payloads = {}
    manifest = {'stage':stage,'test_mode':state['test_mode'],'page_ids':chosen,'all_pages':list(pages),
                'partial_scope': set(chosen)!=set(pages), 'adopted_dimensions':list(dimensions) if stage=='adopted' else [],
                'ledger_sha256':digest(ledger_raw),'items':[],'visual_quality':'not_checked_by_script'}
    if 'html' in formats:
        parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Previs review</title>',
               '<style>body{font:16px system-ui;background:#f4f4f0;color:#222;margin:24px}.grid{display:grid;grid-template-columns:repeat(var(--page-cols,3),1fr);gap:14px}figure{margin:0;background:white;padding:12px;border:1px solid #ccc}img{width:100%;height:220px;object-fit:contain}small{display:block;white-space:pre-wrap}.missing{height:220px;display:grid;place-items:center;background:#eee}h2{break-before:page}@media(max-width:700px){.grid{grid-template-columns:1fr}}</style>',
               '<h1>'+html.escape(state['bundle']['title'])+'</h1><p>'+html.escape(label)+' — 范围 '+html.escape(', '.join(chosen))+'</p><p>网页查看不是采用证据；反馈请引用稳定格ID与实际消息。</p>']
        for pg in chosen:
            parts.append('<h2>'+html.escape(pg)+'</h2><section class="grid" style="--page-cols:'+str(grid(pages[pg])[1])+'">')
            for slot,pid in enumerate(pages[pg]['slots'],1):
                parts.append('<figure>')
                if pid is None:
                    parts.append('<div class="missing">未使用 / UNUSED</div><small>slot '+str(slot)+'</small>')
                else:
                    entry=selections[pid];v=entry['version'];bad=entry['problems']
                    if v and not any(x.startswith('changed_or_missing') for x in bad):
                        image=entry['image_bytes']
                        parts.append('<img alt="'+html.escape(pid)+'" src="data:image/png;base64,'+base64.b64encode(image).decode()+'">')
                    else:
                        parts.append('<div class="missing">缺失 / MISSING</div>')
                    parts.append('<strong>'+html.escape(pid)+'</strong><small>'+html.escape(panels[pid]['shot_id']+' | '+panels[pid]['moment'])+'</small>')
                    parts.append('<small>'+html.escape(', '.join(bad) or ('版本 '+v['revision']+'；采用维度见记录'))+'</small>')
                parts.append('</figure>')
            parts.append('</section>')
        parts.append('</html>');payloads['Review.html']=''.join(parts).encode('utf-8')
    if 'pdf' in formats:
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.utils import ImageReader
        font_path=Path(font) if font else Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
        require(font_path.is_file(),'PDF requires local embeddable TrueType font via --font')
        f=TTFont('PrevisLocal',str(font_path))
        needed='预演审阅未使用缺失范围采用维度'+state['bundle']['title']+label+''.join(panels[p]['moment']+panels[p]['shot_id']+p for p in selections)
        require(all(ord(c) in f.face.charWidths for c in needed if not c.isspace()),'font lacks necessary characters')
        pdfmetrics.registerFont(f)
        buf=io.BytesIO();c=canvas.Canvas(buf,pagesize=(842,595))
        def text(x,y,value,size=9,width=244):
            c.setFont('PrevisLocal',size);line='';lines=[]
            for char in value:
                if char=='\n' or pdfmetrics.stringWidth(line+char,'PrevisLocal',size)>width:
                    lines.append(line);line='' if char=='\n' else char
                else: line+=char
            lines.append(line)
            # Metadata must never cover images; full prose remains in Markdown.
            require(len(lines)<=3,'PDF caption exceeds reserved space; use shorter display moment, retain full current_input')
            for i,s in enumerate(lines):c.drawString(x,y-i*(size+2),s)
        for pg in chosen:
            text(24,570,state['bundle']['title'],14,794)
            text(24,546,label+' | '+pg+' | '+','.join(dimensions) if stage=='adopted' else label+' | '+pg,9,794)
            rows,cols=grid(pages[pg]);px,py=798/cols,492/rows;cw,ch=px-12,py-13;ih=ch-63
            for slot,pid in enumerate(pages[pg]['slots']):
                col,row=slot%cols,slot//cols;x=24+col*px;y=520-row*py
                c.setStrokeColorRGB(.8,.8,.8);c.rect(x,y-ch,cw,ch)
                if pid is None:text(x+8,y-26,'未使用 / UNUSED',11,cw-10)
                else:
                    ent=selections[pid];v=ent['version'];bad=ent['problems']
                    text(x+6,y-13,pid+' | '+panels[pid]['shot_id'],9,cw-10)
                    if v and not any(a.startswith('changed_or_missing') for a in bad):
                        im=image_read(io.BytesIO(ent['image_bytes']));scale=min((cw-12)/im.width,ih/im.height)
                        w,h=im.width*scale,im.height*scale
                        c.drawImage(ImageReader(im),x+(cw-w)/2,y-21-ih+(ih-h)/2,width=w,height=h)
                    else:text(x+8,y-21-ih/2-4,'缺失 / MISSING',11,cw-10)
                    text(x+6,y-(ch-30),panels[pid]['moment'],8,cw-10)
                    text(x+6,y-(ch-7),','.join(bad) if bad else v['revision'],7,cw-10)
            c.showPage()
        c.save();payloads['Review.pdf']=buf.getvalue()
    for pid,entry in selections.items():
        v=entry['version']
        manifest['items'].append({'panel_id':pid,'revision':v['revision'] if v else None,
             'image_sha256':v['sha256'] if v else None,'basis':state['panels'][pid]['basis'],'problems':entry['problems'],
             'facets':{d:panels[pid].get('facets',{}).get(d) for d in dimensions} if stage=='adopted' else {}})
    if stage=='adopted':
        source_ids={s for pid in selections for s in panels[pid]['source_ids']}
        adopted={'format':'suh-delivery/1','kind':'previs','title':state['bundle']['title']+' - 采用范围',
                 'source_units':[s for s in state['bundle']['source_units'] if s['id'] in source_ids],
                 'dialogue':[], 'items':[], 'media_origin':{'workspace':str(root.resolve()),
                 'ledger_sha256':manifest['ledger_sha256'],'dimensions':list(dimensions),
                 'scope':'adopted facets only, not a replacement for the full scene/audio source'}}
        for pid,entry in selections.items():
            v=entry['version'];accepted={d:panels[pid]['facets'][d] for d in dimensions}
            # workflow_state reserves content for the whole rendered body.
            # Keep that adopted description in body, never facets.content.
            facets={d:t for d,t in accepted.items() if d!='content'}
            body=accepted['content'] if 'content' in accepted else '\n'.join(d+'：'+t for d,t in accepted.items())
            adopted['items'].append({'id':pid,'source_ids':panels[pid]['source_ids'],
              'body':body, 'facets':facets,
              'depends_on':panels[pid].get('depends_on',[]),
              'media':{'path':str((root/v['path']).resolve()),'sha256':v['sha256'], 'revision':v['revision'],
                       'source_shot_id':panels[pid].get('source_shot_id'), 'candidate_shot_id':panels[pid]['shot_id'],
                       'moment':panels[pid]['moment'], 'relation':panels[pid]['relation']},
              'human_evidence':[d for d in v['decisions'] if set(d['dimensions']) & set(dimensions)]})
        prepare(adopted)
        payloads['Adopted-bundle.json']=canonical(adopted)
    manifest['files']={name:{'bytes':len(raw),'sha256':digest(raw)} for name,raw in payloads.items()}
    manifest['render_build_seconds']=round(time.perf_counter()-started,4)
    payloads['Export.json']=canonical(manifest)
    output.mkdir(parents=True)
    for name,raw in payloads.items():save_new(output/name,raw)
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('init');i.add_argument('--bundle',required=True);i.add_argument('--workspace',required=True);i.add_argument('--test-mode',action='store_true')
    a=sub.add_parser('apply');a.add_argument('--workspace',required=True);a.add_argument('--operation',required=True)
    s=sub.add_parser('status');s.add_argument('--workspace',required=True)
    e=sub.add_parser('export');e.add_argument('--workspace',required=True);e.add_argument('--out',required=True);e.add_argument('--stage',choices=['review','adopted'],default='review');e.add_argument('--formats',nargs='+',choices=['html','pdf'],required=True);e.add_argument('--pages',nargs='+');e.add_argument('--dimensions',nargs='+',default=['content']);e.add_argument('--font')
    args=p.parse_args()
    try:
        if args.command=='init':r=initialize(args.workspace,args.bundle,args.test_mode)
        elif args.command=='apply':r=operate(args.workspace,load(args.operation))
        elif args.command=='status':r=operate(args.workspace,{'action':'status'})
        else:r=export(args.workspace,args.out,args.stage,args.formats,args.pages,args.dimensions,args.font)
    except (ValueError,OSError,KeyError,ImportError) as ex:p.exit(2,'Previs operation failed: '+str(ex)+'\n')
    print(json.dumps(r,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
