#!/usr/bin/env python3
"""Local handoff ledger. Checks declared evidence and bytes, not human identity or story quality."""
import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from deliver import load, prepare

IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\Z')
KINDS = {'scene', 'prompt', 'previs'}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(ref, text):
    need(isinstance(ref, str) and ref.strip() and isinstance(text, str) and text.strip(), 'actual user/source evidence reference and text required')
    return {'ref': ref, 'text': text, 'identity_verification': 'not_performed_by_script'}


def initial(project, intent, request_ref, request_text):
    need(intent in ('pipeline', 'prompt_only', 'previs_only'), 'unknown task intent')
    need(bool(project.strip()), 'project required')
    return {'format': 'suh-workflow/1', 'project': project, 'intent': intent,
            'request': evidence(request_ref, request_text), 'artifacts': {}, 'effective': {}, 'events': [], 'revision': 0}


def event(state, action, **fields):
    state['events'].append({'action': action, 'timestamp': datetime.now(timezone.utc).isoformat(), **fields})
    state['revision'] += 1


def item_at(state, artifact_id, unit_id):
    need(artifact_id in state['artifacts'], 'unknown artifact: ' + artifact_id)
    artifact = state['artifacts'][artifact_id]
    need(unit_id in artifact['units'], 'unknown unit: ' + unit_id)
    return artifact, artifact['units'][unit_id]


def key_for(artifact, unit, dimension):
    return artifact['kind'] + '/' + artifact['lineage'] + '#' + unit + '@' + dimension


def effective_selection(state, artifact, uid, dimension):
    selected = state['effective'].get(key_for(artifact, uid, dimension))
    if dimension == 'content':
        return selected
    whole = state['effective'].get(key_for(artifact, uid, 'content'))
    if whole:
        # Older /1 ledgers have no facet entries derived from whole adoption.
        # Use their actual recorded review order without rewriting old events.
        def position(value, dims):
            if not value:
                return -1
            return max((i for i, e in enumerate(state['events'])
                        if e['action'] == 'human_review_recorded' and e.get('decision') == 'approved'
                        and e.get('artifact') == value['artifact'] and uid in e.get('units', [])
                        and set(e.get('dimensions', [])).intersection(dims)), default=-1)
        if not selected or position(whole, {'content'}) > position(selected, {dimension, 'content'}):
            _, unit = item_at(state, whole['artifact'], uid)
            return {'artifact': whole['artifact'], 'digest': unit['digests'].get(dimension)}
    return selected


def selection_invalid(state, selected, uid, dimension):
    if not selected:
        return False
    _, unit = item_at(state, selected['artifact'], uid)
    invalid = unit['invalid_dimensions']
    return 'content' in invalid or dimension in invalid or (dimension == 'content' and bool(invalid))


def dependency(state, value):
    if isinstance(value, str):
        parts = value.split('#')
        need(len(parts) == 2, 'dependency must be artifact#unit')
        aid, uid = parts
        dimensions = ['content']
    else:
        need(isinstance(value, dict), 'invalid dependency')
        aid, uid, dimensions = value.get('artifact'), value.get('unit'), value.get('dimensions', ['content'])
    need(isinstance(aid, str) and isinstance(uid, str), 'dependency requires artifact and unit')
    _, unit = item_at(state, aid, uid)
    need(isinstance(dimensions, list) and dimensions and all(isinstance(d, str) for d in dimensions), 'invalid dependency dimensions')
    need(len(set(dimensions)) == len(dimensions), 'duplicate dependency dimension')
    need(all(d in unit['digests'] for d in dimensions), 'dependency facet not declared in source')
    return {'artifact': aid, 'unit': uid, 'dimensions': dimensions,
            'digests': {d: unit['digests'][d] for d in dimensions}}


class _HealthCheck:
    """One read/check phase only; never persisted or reused after state mutation."""
    def __init__(self):
        self.nodes = {}
        self.files = {}

    def matches(self, path, expected):
        key = str(path.resolve())
        if key not in self.files:
            self.files[key] = file_digest(path) if path.is_file() else None
        return self.files[key] is not None and self.files[key] == expected


def health(state, artifact_id, unit_id, dimensions=None, stack=None, _check=None):
    dimensions = dimensions or ['content']
    _check = _HealthCheck() if _check is None else _check
    artifact, unit = item_at(state, artifact_id, unit_id)
    stack = set() if stack is None else set(stack)
    address = artifact_id + '#' + unit_id
    need(address not in stack, 'cyclic dependency')
    stack.add(address)
    key = (artifact_id, unit_id, tuple(sorted(set(dimensions))))
    if key in _check.nodes:
        return list(_check.nodes[key])
    reasons = []
    path = Path(artifact['bundle_path'])
    if not _check.matches(path, artifact['file_sha256']):
        reasons.append('registered_bundle_missing_or_modified')
    for source in artifact.get('source_files', []):
        source_path = Path(source['path'])
        if not _check.matches(source_path, source['sha256']):
            reasons.append('source_file_changed_scope_requires_review:' + source_path.name)
    invalid = unit['invalid_dimensions']
    if 'content' in invalid or ('content' in dimensions and invalid) or set(dimensions).intersection(invalid):
        reasons.append('explicitly_invalidated')
    for bound in unit.get('bound_files', []):
        bound_path = Path(bound['path'])
        if not _check.matches(bound_path, bound['sha256']):
            reasons.append('bound_media_missing_or_modified')
    for dim in dimensions:
        if dim not in unit['digests']:
            reasons.append('unknown_dimension:' + dim)
            continue
        selected = effective_selection(state, artifact, unit_id, dim)
        if selected and selected['digest'] != unit['digests'][dim]:
            reasons.append('superseded_effective_' + dim)
        if selection_invalid(state, selected, unit_id, dim):
            reasons.append('effective_selection_invalidated:' + dim)
        if dim == 'content':
            # Whole content includes its declared facets. A newer local adoption
            # can supersede that part without adopting any other dimension.
            for facet in unit['facets']:
                effective = effective_selection(state, artifact, unit_id, facet)
                if effective and effective['digest'] != unit['digests'][facet]:
                    reasons.append('superseded_effective_content_facet:' + facet)
                if selection_invalid(state, effective, unit_id, facet):
                    reasons.append('effective_selection_invalidated:' + facet)
    for dep in unit['dependencies']:
        _, upstream = item_at(state, dep['artifact'], dep['unit'])
        if any(upstream['digests'].get(d) != dep['digests'].get(d) for d in dep['dimensions']):
            reasons.append('dependency_snapshot_mismatch:' + dep['artifact'] + '#' + dep['unit'])
        problems = health(state, dep['artifact'], dep['unit'], dep['dimensions'], stack, _check)
        if problems:
            reasons.append('dependency:' + dep['artifact'] + '#' + dep['unit'] + ':' + ','.join(problems))
    result = tuple(sorted(set(reasons)))
    _check.nodes[key] = result
    return list(result)


def reviewed(state, artifact_id, unit_id, dimensions=None):
    dimensions = dimensions or ['content']
    _, unit = item_at(state, artifact_id, unit_id)
    return all(unit['reviews'].get(d, {}).get('decision') == 'approved' and
               unit['reviews'][d]['digest'] == unit['digests'].get(d) for d in dimensions)


def check_entry(state, target, route, upstream=None, units=None, _check=None):
    _check = _HealthCheck() if _check is None else _check
    need(target in ('scene', 'previs', 'prompt'), 'unknown target')
    need(route in ('mainline', 'independent'), 'unknown route')
    if route == 'independent':
        allowed = (target == 'prompt' and state['intent'] == 'prompt_only') or (target == 'previs' and state['intent'] == 'previs_only')
        if not allowed:
            return {'status': 'INTENT_MISMATCH', 'reason': 'cannot relabel this pipeline request as independent', 'next': 'use actual user request; do not invent a new intent'}
    if target == 'prompt' and route == 'mainline':
        if not upstream or not units:
            return {'status': 'WAIT_REVIEW', 'reason': 'reviewed director scope required', 'next': 'deliver director result for user review'}
        artifact = state['artifacts'].get(upstream)
        need(artifact is not None and artifact['kind'] == 'scene', 'mainline upstream must be a registered director bundle')
    problems, pending = {}, []
    if upstream:
        need(units is not None and bool(units), 'explicit upstream unit scope required')
        for uid in units:
            p = health(state, upstream, uid, _check=_check)
            if p:
                problems[uid] = p
            if target == 'prompt' and route == 'mainline' and not reviewed(state, upstream, uid):
                pending.append(uid)
    if problems:
        return {'status': 'STALE', 'units': problems, 'next': 'repair or select the correct current basis before continuing'}
    if pending:
        return {'status': 'WAIT_REVIEW', 'units': pending, 'next': 'wait for actual user review for this scope'}
    return {'status': 'READY', 'target': target, 'route': route, 'upstream': upstream, 'units': units or [],
            'meaning': 'declared workflow conditions only; not creative, media or identity approval'}


def register_bundle(state, artifact_id, bundle_path):
    _check = _HealthCheck()
    need(bool(IDENT.fullmatch(artifact_id)), 'invalid artifact id')
    need(artifact_id not in state['artifacts'], 'artifact id is immutable; use a new revision id')
    path = Path(bundle_path).resolve()
    bundle = load(path)
    rendered = prepare(bundle)
    need(bundle['kind'] in KINDS, 'unsupported kind')
    lineage = bundle.get('lineage', bundle['kind'])
    need(isinstance(lineage, str) and bool(IDENT.fullmatch(lineage)), 'invalid artifact lineage')
    source_files = []
    for value in bundle.get('source_files', []):
        need(isinstance(value, dict) and isinstance(value.get('path'), str), 'invalid source file binding')
        src = Path(value['path'])
        src = (src if src.is_absolute() else path.parent / src).resolve()
        actual = file_digest(src)
        need(not value.get('sha256') or value['sha256'] == actual, 'source file already differs from expected snapshot')
        source_files.append({'path': str(src), 'sha256': actual})
    raw_sources = {x['id']: x['text'] for x in bundle['source_units']}
    units = {}
    for item in bundle['items']:
        uid = item['id']
        facets = item.get('facets', {})
        need(isinstance(facets, dict) and all(isinstance(k, str) and isinstance(v, str) and v.strip() for k, v in facets.items()), 'facets must be nonempty text by dimension')
        need('content' not in facets, 'content is the whole rendered item, not a custom facet')
        deps = [dependency(state, value) for value in item.get('depends_on', [])]
        source = {x: raw_sources[x] for x in item['source_ids']}
        common = {'conditions': bundle.get('conditions', {}), 'sources': source}
        metadata = {k: v for k, v in item.items() if k not in ('body', 'copy_text', 'depends_on', 'dialogue_placements')}
        digests = {'content': digest({**common, 'rendered': rendered[uid], 'metadata': metadata})}
        digests.update({k: digest({**common, 'facet': v}) for k, v in facets.items()})
        bound_files = []
        media = item.get('media')
        if media is not None:
            need(isinstance(media, dict) and isinstance(media.get('path'), str) and isinstance(media.get('sha256'), str), 'media binding requires actual path and sha256')
            media_path = Path(media['path'])
            media_path = (media_path if media_path.is_absolute() else path.parent / media_path).resolve()
            need(file_digest(media_path) == media['sha256'], 'adopted media differs from its recorded bytes')
            bound_files.append({'path': str(media_path), 'sha256': media['sha256']})
        units[uid] = {'digests': digests, 'rendered': rendered[uid], 'facets': facets,
                      'dependencies': deps, 'bound_files': bound_files, 'reviews': {}, 'invalid_dimensions': []}
        if bundle['kind'] == 'prompt' and state['intent'] == 'pipeline':
            director_deps = [d for d in deps if state['artifacts'][d['artifact']]['kind'] == 'scene']
            need(bool(director_deps), 'mainline Prompt requires direct reviewed director dependencies')
            for dep in director_deps:
                need('content' in dep['dimensions'], 'director approval must cover the full relevant director content')
                result = check_entry(state, 'prompt', 'mainline', dep['artifact'], [dep['unit']], _check)
                need(result['status'] == 'READY', 'mainline Prompt blocked: ' + result['status'])
        elif bundle['kind'] == 'prompt':
            need(state['intent'] == 'prompt_only', 'previs-only request does not authorize Prompt production')
        for dep in deps:
            need(not health(state, dep['artifact'], dep['unit'], dep['dimensions'], _check=_check), 'cannot register from stale dependency')
            if bundle['kind'] == 'prompt' and state['artifacts'][dep['artifact']]['kind'] == 'previs':
                need(reviewed(state, dep['artifact'], dep['unit'], dep['dimensions']), 'previs dependencies must refer only to actually adopted dimensions')
    state['artifacts'][artifact_id] = {'kind': bundle['kind'], 'lineage': lineage, 'bundle_path': str(path),
        'file_sha256': file_digest(path), 'source_files': source_files, 'title': bundle['title'], 'units': units}
    event(state, 'register', artifact=artifact_id, kind=bundle['kind'], units=list(units))
    return {'artifact': artifact_id, 'units': list(units), 'adopted': False}


def record_review(state, artifact_id, units, decision, dimensions, ref, text):
    _check = _HealthCheck()
    need(decision in ('approved', 'changes_requested'), 'unknown review decision')
    ev = evidence(ref, text)
    need(bool(units) and len(units) == len(set(units)), 'explicit unique review scope required')
    need(bool(dimensions) and len(dimensions) == len(set(dimensions)), 'explicit unique dimensions required')
    prepared = []
    for uid in units:
        artifact, unit = item_at(state, artifact_id, uid)
        need(all(d in unit['digests'] for d in dimensions), 'partial adoption requires corresponding textual facets')
        if decision == 'approved':
            # A replacement may intentionally supersede an older effective unit.
            problems = [x for x in health(state, artifact_id, uid, dimensions, _check=_check)
                        if not x.startswith(('superseded_effective_', 'effective_selection_invalidated:'))]
            need(not problems, 'cannot approve missing, changed or invalidated content: ' + ','.join(problems))
        prepared.append((uid, artifact, unit))
    for uid, artifact, unit in prepared:
        for dim in dimensions:
            unit['reviews'][dim] = {'decision': decision, 'digest': unit['digests'][dim], 'evidence': ev}
            if decision == 'approved':
                state['effective'][key_for(artifact, uid, dim)] = {'artifact': artifact_id, 'digest': unit['digests'][dim]}
                if dim == 'content':
                    # Effective basis is distinct from a facet review. Keep old
                    # reviews of unchanged facets usable, but do not create new
                    # facet approvals from a whole-content selection.
                    prefix = key_for(artifact, uid, '')
                    known = {key[len(prefix):] for key in state['effective'] if key.startswith(prefix)}
                    for facet in (known | set(unit['facets'])) - {'content'}:
                        state['effective'][key_for(artifact, uid, facet)] = {
                            'artifact': artifact_id, 'digest': unit['digests'].get(facet)}
            elif dim not in unit['invalid_dimensions']:
                unit['invalid_dimensions'].append(dim)
    event(state, 'human_review_recorded', artifact=artifact_id, units=units, dimensions=dimensions, decision=decision, evidence=ev)
    return {'recorded': True, 'decision': decision, 'scope': units, 'human_identity_verified': False}


def invalidate(state, artifact_id, units, dimensions, ref, text):
    ev = evidence(ref, text)
    need(bool(units) and bool(dimensions), 'invalidation scope required')
    targets = []
    for uid in units:
        _, unit = item_at(state, artifact_id, uid)
        need(all(dim in unit['digests'] for dim in dimensions), 'unknown invalidation dimension')
        targets.append(unit)
    for unit in targets:
        unit['invalid_dimensions'] = sorted(set(unit['invalid_dimensions'] + dimensions))
    event(state, 'invalidate', artifact=artifact_id, units=units, dimensions=dimensions, evidence=ev)
    return status(state)


def status(state):
    _check = _HealthCheck()
    return {'project': state['project'], 'intent': state['intent'], 'revision': state['revision'],
            'artifacts': {aid: {'kind': a['kind'], 'units': {uid: {'issues': health(state, aid, uid, _check=_check),
                'review_decisions': {d: r['decision'] for d, r in u['reviews'].items()}}
                for uid, u in a['units'].items()}} for aid, a in state['artifacts'].items()}}


def approved_context(state, artifact_id, units, dimensions):
    _check = _HealthCheck()
    out = []
    artifact = state['artifacts'].get(artifact_id)
    need(artifact is not None, 'unknown artifact')
    for uid in units:
        _, unit = item_at(state, artifact_id, uid)
        need(not health(state, artifact_id, uid, dimensions, _check=_check), 'stale context')
        need(reviewed(state, artifact_id, uid, dimensions), 'requested dimension has not been adopted')
        content = unit['rendered'] if 'content' in dimensions else {'facets': {d: unit['facets'][d] for d in dimensions}}
        result = {'id': uid, 'dimensions': dimensions, **content}
        if unit.get('bound_files'):
            result['media_bindings'] = [{'path': b['path'], 'sha256': b['sha256'], 'adopted_dimensions': dimensions} for b in unit['bound_files']]
        out.append(result)
    return {'artifact': artifact_id, 'lineage': artifact['lineage'], 'bundle_path': artifact['bundle_path'],
            'source_files': artifact.get('source_files', []), 'units': out,
            'evidence_boundary': 'user feedback recorded by agent; not identity verification'}


def save_state(path, state, expected=None):
    path = Path(path)
    if expected is not None:
        need(path.exists() and file_digest(path) == expected, 'state changed concurrently; reload before applying')
    else:
        need(not path.exists(), 'state exists; init must not overwrite')
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = None
    try:
        os.close(fd)
        if expected is not None:
            need(file_digest(path) == expected, 'state changed concurrently')
        else:
            need(not path.exists(), 'state already exists')
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, prefix=path.name + '.', suffix='.tmp', delete=False) as f:
            temporary = Path(f.name)
            json.dump(state, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        need(load(temporary) == state, 'state readback mismatch')
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
        lock.unlink()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation', choices=['init', 'register', 'review', 'check', 'invalidate', 'status', 'context'])
    p.add_argument('--state', required=True, type=Path)
    p.add_argument('--project')
    p.add_argument('--intent', choices=['pipeline', 'prompt_only', 'previs_only'])
    p.add_argument('--evidence-ref')
    p.add_argument('--evidence-text')
    p.add_argument('--artifact')
    p.add_argument('--bundle', type=Path)
    p.add_argument('--units', nargs='+')
    p.add_argument('--dimensions', nargs='+', default=['content'])
    p.add_argument('--decision', choices=['approved', 'changes_requested'])
    p.add_argument('--target', choices=['scene', 'previs', 'prompt'])
    p.add_argument('--route', choices=['mainline', 'independent'], default='mainline')
    args = p.parse_args()
    try:
        if args.operation == 'init':
            need(bool(args.project) and bool(args.intent), 'project and intent required')
            state = initial(args.project, args.intent, args.evidence_ref, args.evidence_text)
            save_state(args.state, state)
            result = status(state)
        else:
            before = file_digest(args.state)
            state = load(args.state)
            need(state.get('format') == 'suh-workflow/1', 'unsupported workflow state')
            if args.operation == 'register':
                need(bool(args.artifact) and args.bundle is not None, 'artifact and bundle required')
                result = register_bundle(state, args.artifact, args.bundle)
            elif args.operation == 'review':
                result = record_review(state, args.artifact, args.units, args.decision, args.dimensions, args.evidence_ref, args.evidence_text)
            elif args.operation == 'invalidate':
                result = invalidate(state, args.artifact, args.units, args.dimensions, args.evidence_ref, args.evidence_text)
            elif args.operation == 'check':
                result = check_entry(state, args.target, args.route, args.artifact, args.units)
            elif args.operation == 'context':
                result = approved_context(state, args.artifact, args.units or [], args.dimensions)
            else:
                result = status(state)
            if args.operation in ('register', 'review', 'invalidate'):
                save_state(args.state, state, before)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.operation == 'check' and result['status'] != 'READY':
            raise SystemExit(3)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        p.exit(2, 'Workflow state error: ' + str(exc) + '\n')


if __name__ == '__main__':
    main()
