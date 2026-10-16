#!/usr/bin/env python3
"""Same-content review views and explicit, non-adopting feedback application.

HTML/Markdown and feedback inspection use only the standard library. XLSX authoring
uses an explicitly supplied existing @oai/artifact-tool runtime; never installs it.
"""
import argparse
import copy
import hashlib
import html
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import deliver

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
HEADERS = ["单元ID", "片段ID", "来源ID", "估时/条件（只列一次）", "完整正文（可修改）", "审阅意见（不改正文）"]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def write_json(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def chunks(text, max_lines=12, line_units=58):
    """Reversible display-only continuations; no inferred shots or timings."""
    result, start, lines, units = [], 0, 1, 0
    for i, char in enumerate(text):
        width = 2 if ord(char) > 255 else 1
        next_lines = lines + (1 if char == "\n" or units + width > line_units else 0)
        if next_lines > max_lines and i > start:
            result.append(text[start:i])
            start, lines, units = i, 1, 0
        if char == "\n":
            lines, units = lines + 1, 0
        elif units + width > line_units:
            lines, units = lines + 1, width
        else:
            units += width
    result.append(text[start:])
    require("".join(result) == text, "continuation round-trip failure")
    return result


def make_manifest(bundle):
    rendered = deliver.prepare(bundle)
    items, segments = {}, []
    indexed = {i["id"]: i for i in bundle["items"]}
    for iid, value in rendered.items():
        parts = chunks(value["body"])
        timing = indexed[iid].get("timing_note", "未提供；不能作为0秒")
        require(isinstance(timing, str), "timing_note must be text")
        items[iid] = {**value, "timing_note": timing}
        for n, part in enumerate(parts, 1):
            segments.append({"id": f"{iid}__{n:03}", "item_id": iid,
                             "source_ids": value["source_ids"], "body": part,
                             "timing_note": timing if n == 1 else ""})
    source_segments = [{"id": f'{s["id"]}__{n:03}', "source_id": s["id"], "text": part}
                       for s in bundle["source_units"] for n, part in enumerate(chunks(s["text"]), 1)]
    return {"format": "suh-review-baseline/1", "baseline_sha256": digest(bundle),
            "title": bundle["title"], "kind": bundle["kind"], "items": items,
            "segments": segments, "source_units": bundle["source_units"], "source_segments": source_segments,
            "adoption_status": "not_recorded_by_export"}


def build_html(manifest):
    esc = html.escape
    cards = []
    for s in manifest["segments"]:
        cards.append(f'<article data-segment="{esc(s["id"])}"><h2>{esc(s["item_id"])} '
                     f'<small>{esc(s["id"])}</small></h2><p>来源：{esc(", ".join(s["source_ids"]))}'
                     f'　{esc(s["timing_note"])}</p><label>完整正文（可编辑）'
                     f'<textarea class="body">\n{esc(s["body"])}</textarea></label>'
                     '<label>审阅意见（不会被当成正文或批准）<textarea class="comment"></textarea></label></article>')
    sources = "".join(f'<h3>{esc(s["id"])}</h3><pre>{esc(s["text"])}</pre>' for s in manifest["source_units"])
    data = canonical(manifest).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>''' + esc(manifest["title"]) + ''' · 审阅</title><style>
body{max-width:1080px;margin:32px auto;padding:0 20px;background:#f2f4f3;color:#172b2a;font:16px/1.65 system-ui,sans-serif}
header,article,details{background:white;border:1px solid #ccd8d5;padding:24px;margin:18px 0;border-radius:10px}h1{margin:0}h2{font-size:20px}small{font-size:12px;color:#576f69}
label{display:block;margin:14px 0}textarea{box-sizing:border-box;width:100%;font:16px/1.6 system-ui,sans-serif;border:1px solid #8fa6a0;padding:12px;resize:vertical;min-height:110px;background:#fffef7}textarea.body{min-height:210px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}
button{padding:12px 18px;margin:5px 8px 5px 0;background:#195e55;color:white;border:0;border-radius:6px;font:inherit;cursor:pointer}nav a{margin-right:16px}#status{font-weight:600}.note{color:#596c66}
</style><header><h1>''' + esc(manifest["title"]) + '''</h1><p>单元及续行不是镜头。原文、正文与意见分开；文件保存不代表采用。</p>
<p class="note">修改只在本页内存中，关闭会丢失。完成后点击“导出反馈 JSON”，将下载的文件交回 Agent。此页不使用云服务、不自动提交或批准。</p>
<button id="export">导出反馈 JSON</button><button id="copy">复制当前完整正文</button><p id="status" role="status"></p></header>
<details><summary>来源原文（只读）</summary>''' + sources + '''</details>''' + "".join(cards) + '''
<script type="application/json" id="baseline">''' + data + '''</script><script>
const baseline=JSON.parse(document.getElementById('baseline').textContent);
const rows=()=>Array.from(document.querySelectorAll('article[data-segment]')).map(el=>({id:el.dataset.segment,body:el.querySelector('.body').value,comment:el.querySelector('.comment').value}));
document.getElementById('export').addEventListener('click',()=>{const feedback={format:'suh-review-feedback/1',baseline_sha256:baseline.baseline_sha256,segments:rows(),adoption_status:'not_recorded_by_export'};const blob=new Blob([JSON.stringify(feedback,null,2)+'\\n'],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='Review-feedback.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='已请求下载反馈文件；请确认浏览器下载成功。没有自动采用或修改主稿。';});
document.getElementById('copy').addEventListener('click',async()=>{try{const current=Object.fromEntries(rows().map(r=>[r.id,r.body]));const text=Object.keys(baseline.items).map(id=>baseline.segments.filter(s=>s.item_id===id).map(s=>current[s.id]).join('')).join('\\n\\n');await navigator.clipboard.writeText(text);document.getElementById('status').textContent='已复制正文，未写回主稿。';}catch(e){document.getElementById('status').textContent='浏览器未允许剪贴板，请选取正文复制；反馈仍可导出。';}});
</script></html>'''


def export(bundle, out, xlsx=False, node=None, node_modules=None, render=False):
    started = time.perf_counter()
    manifest = make_manifest(bundle)
    out = Path(out)
    require(not out.exists(), "output exists; use a new directory")
    out.mkdir(parents=True)
    write_json(out / "Bundle.json", bundle)
    write_json(out / "Review-baseline.json", manifest)
    master = "# " + bundle["title"] + "\n\n" + "\n\n".join(
        "## " + iid + "\n\n" + v["body"] for iid, v in manifest["items"].items()) + "\n"
    (out / "Master.md").write_text(master, encoding="utf-8")
    page = build_html(manifest)
    (out / "Review.html").write_text(page, encoding="utf-8")
    require((out / "Master.md").read_text(encoding="utf-8") == master, "MD readback failed")
    report = {"format": "suh-review-export/1", "baseline_sha256": manifest["baseline_sha256"],
              "views": ["markdown", "html"], "xlsx": "not_requested", "semantic_status": "not_checked",
              "adoption_status": "not_recorded_by_export"}
    report["md_html_seconds"] = time.perf_counter() - started
    if xlsx:
        xlsx_started = time.perf_counter()
        require(node and node_modules, "XLSX requires --node and --node-modules from existing runtime; no install")
        require(Path(node).is_file() and Path(node_modules).is_dir(), "existing runtime paths not found")
        with tempfile.TemporaryDirectory(prefix="suh-review-") as tmp:
            target = Path(tmp) / "Review-workbook.mjs"
            shutil.copyfile(Path(__file__).with_name("Review-workbook.mjs"), target)
            (Path(tmp) / "node_modules").symlink_to(Path(node_modules).resolve(), target_is_directory=True)
            args = [str(node), str(target), str((out / "Review-baseline.json").resolve()), str(out.resolve())]
            if render:
                args.append("--render")
            subprocess.run(args, check=True, capture_output=True, text=True)
        returned = read_xlsx(out / "Review.xlsx", manifest)
        require([s["id"] for s in returned["segments"]] == [s["id"] for s in manifest["segments"]],
                "XLSX segment order readback mismatch")
        require(all(s["body"] == manifest["segments"][n]["body"] for n, s in enumerate(returned["segments"])), "XLSX body readback mismatch")
        report.update(xlsx="exported_and_exact_body_readback", views=["markdown", "html", "xlsx"],
                      render="rendered_requires_visual_inspection" if render else "not_requested")
        report["xlsx_seconds_including_optional_render"] = time.perf_counter() - xlsx_started
    report["file_bytes"] = {p.name: p.stat().st_size for p in out.iterdir() if p.is_file()}
    write_json(out / "Review-checks.json", report)
    return report


def _texts(element):
    return "".join(t.text or "" for t in element.findall(".//m:t", NS))


def _sheet_rows(zf, member, shared):
    root = ET.fromstring(zf.read(member))
    result = []
    for row in root.findall("m:sheetData/m:row", NS):
        cells = {}
        for cell in row.findall("m:c", NS):
            require(cell.find("m:f", NS) is None, "formulas are not supported in review input")
            ref = cell.attrib["r"]
            value = cell.find("m:v", NS)
            typ = cell.attrib.get("t")
            if typ == "inlineStr":
                text = _texts(cell)
            elif typ == "s":
                text = shared[int(value.text)] if value is not None else ""
            else:
                text = value.text if value is not None and value.text is not None else ""
            # Artifact writes literal = text as quote-prefixed strings. Strip only
            # its explicit quotePrefix style is not reliably round-tripped; writer
            # instead uses formula-safe format @ values and rejects formula nodes.
            cells[re.sub(r"\d", "", ref)] = text
        if any(cells.values()):
            result.append((int(row.attrib["r"]), cells))
    return result


def read_xlsx(path, manifest):
    with zipfile.ZipFile(path) as zf:
        require(sum(x.file_size for x in zf.infolist()) < 100_000_000, "workbook too large")
        require(not any("threadedComments" in name for name in zf.namelist()),
                "threaded Excel Comments are unsupported: retain file, explicitly copy threads to review column and re-import")
        shared = []
        if "xl/sharedStrings.xml" in zf.namelist():
            shared = [_texts(e) for e in ET.fromstring(zf.read("xl/sharedStrings.xml")).findall("m:si", NS)]
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        relations = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in relations}
        sheets = {}
        for s in wb.findall("m:sheets/m:sheet", NS):
            rid = s.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
            t = targets[rid]
            sheets[s.attrib["name"]] = t.lstrip("/") if t.startswith("/") else "xl/" + t
        require("Review" in sheets and "Baseline" in sheets and "Sources" in sheets, "missing required review sheets")
        metadata = dict((r.get("A", ""), r.get("B", "")) for _, r in _sheet_rows(zf, sheets["Baseline"], shared))
        require(metadata.get("baseline_sha256") == manifest["baseline_sha256"], "workbook baseline mismatch")
        # Source and metadata edits are never silently accepted as creative edits.
        source_rows = _sheet_rows(zf, sheets["Sources"], shared)[1:]
        expected_sources = {r["id"]: (r["source_id"], r["text"]) for r in manifest["source_segments"]}
        observed_sources = {}
        for _, r in source_rows:
            sid = r.get("B", "")
            require(sid not in observed_sources, "duplicate source ID")
            observed_sources[sid] = (r.get("A", ""), r.get("C", ""))
        require(observed_sources == expected_sources, "source text changed: resolve source revision separately")
        rows = _sheet_rows(zf, sheets["Review"], shared)
        header = next((idx for idx, (_, r) in enumerate(rows) if r.get("A") == HEADERS[0]), None)
        require(header is not None, "review header missing")
        require([rows[header][1].get(chr(65+n), "") for n in range(6)] == HEADERS, "review headers changed")
        expected = {s["id"]: s for s in manifest["segments"]}
        records, row_segments = [], {}
        for row_number, row in rows[header + 1:]:
            sid = row.get("B", "")
            require(sid in expected, "unknown or blank segment ID: " + sid)
            s = expected[sid]
            require(row.get("A") == s["item_id"], "item/segment ID mismatch")
            require(row.get("C", "") == ", ".join(s["source_ids"]), "source IDs changed")
            require(row.get("D", "") == s["timing_note"], "timing changed: submit this as an explicit comment for professional revision")
            records.append({"id": sid, "body": row.get("E", ""), "comment": row.get("F", "")})
            row_segments[row_number] = records[-1]
        ids = [record["id"] for record in records]
        require(len(ids) == len(set(ids)), "duplicate review segment ID")
        require(set(ids) == set(expected), "review missing segment IDs; deletion is not a removal instruction")
        # Read legacy Excel Notes attached to body/review columns as comments.
        # Unsupported positions stop import rather than dropping feedback.
        sheet_path = Path(sheets["Review"])
        rel_path = str(sheet_path.parent / "_rels" / (sheet_path.name + ".rels"))
        consumed_comments = set()
        if rel_path in zf.namelist():
            import posixpath
            for rel in ET.fromstring(zf.read(rel_path)):
                if rel.attrib.get("Type", "").endswith("/comments"):
                    target = rel.attrib["Target"]
                    member = target.lstrip("/") if target.startswith("/") else posixpath.normpath(str(sheet_path.parent / target))
                    consumed_comments.add(member)
                    for comment in ET.fromstring(zf.read(member)).findall("m:commentList/m:comment", NS):
                        ref = comment.attrib["ref"]
                        match = re.fullmatch(r"([A-Z]+)(\d+)", ref)
                        require(match and match[1] in ("E", "F") and int(match[2]) in row_segments,
                                "legacy Note outside body/review columns: copy it to a review cell explicitly")
                        rec = row_segments[int(match[2])]
                        rec["comment"] += ("\n" if rec["comment"] else "") + "[Excel Note] " + _texts(comment)
        all_comments = {name for name in zf.namelist()
                        if re.search(r"(?:^|/)comments?[^/]*\.xml$", name)}
        require(all_comments <= consumed_comments,
                "legacy Notes outside Review sheet are unsupported: explicitly move feedback to review column")
        return {"format": "suh-review-feedback/1", "baseline_sha256": manifest["baseline_sha256"], "segments": records}


def extract_feedback(bundle, feedback, origin="unspecified"):
    manifest = make_manifest(bundle)
    require(feedback.get("format") == "suh-review-feedback/1", "unsupported feedback format")
    require(feedback.get("baseline_sha256") == manifest["baseline_sha256"], "feedback baseline mismatch/stale")
    expected = {s["id"]: s for s in manifest["segments"]}
    observed = {}
    require(isinstance(feedback.get("segments"), list), "feedback segments must be a list")
    for rec in feedback["segments"]:
        require(isinstance(rec, dict), "feedback segment must be an object")
        sid = rec.get("id")
        require(isinstance(sid, str) and sid in expected and sid not in observed, "unknown/duplicate segment ID")
        require(isinstance(rec.get("body"), str) and isinstance(rec.get("comment", ""), str), "feedback must contain text")
        observed[sid] = rec
    require(set(observed) == set(expected), "feedback missing segment IDs; deletion is not a removal instruction")
    edits, comments = [], []
    for iid, item in manifest["items"].items():
        segments = [s for s in manifest["segments"] if s["item_id"] == iid]
        after = "".join(observed[s["id"]]["body"] for s in segments)
        if after != item["body"]:
            edits.append({"id": iid, "before": item["body"], "after": after})
        for s in segments:
            comment = observed[s["id"]].get("comment", "")
            if comment.strip():
                comments.append({"id": iid, "segment_id": s["id"], "text": comment})
    return {"format": "suh-review-patch/1", "baseline_sha256": manifest["baseline_sha256"],
            "origin": origin, "edits": edits, "comments": comments,
            "status": "candidate_feedback_not_adopted", "semantic_status": "not_checked"}


def apply_feedback(bundle, patch, candidate, accepted, evidence_ref, evidence_text):
    require(patch.get("format") == "suh-review-patch/1", "unsupported patch")
    require(patch.get("baseline_sha256") == digest(bundle), "base changed since feedback")
    require(bool(evidence_ref.strip()) and bool(evidence_text.strip()), "actual scoped human instruction must be recorded")
    before, after = deliver.prepare(bundle), deliver.prepare(candidate)
    edits = {e["id"]: e for e in patch.get("edits", [])}
    require(len(edits) == len(patch.get("edits", [])), "duplicate patch ID")
    require(bool(accepted) and len(accepted) == len(set(accepted)) and set(accepted) <= set(edits), "accepted IDs must select actual body edits")
    require(set(before) == set(after), "add/remove units needs separate scoped revision")
    for key in set(bundle) | set(candidate):
        if key not in ("items", "dialogue"):
            require(bundle.get(key) == candidate.get(key), "unrelated metadata/source revision: " + key)
    old_items = {i["id"]: i for i in bundle["items"]}
    new_items = {i["id"]: i for i in candidate["items"]}
    require([i["id"] for i in bundle["items"]] == [i["id"] for i in candidate["items"]], "candidate reordered units")
    for iid in before:
        if iid in accepted:
            require(edits[iid]["before"] == before[iid]["body"], "patch preimage mismatch")
            require(after[iid]["body"] == edits[iid]["after"], "candidate body does not match accepted feedback")
            # No invisible source/dependency/facet/timing changes are implied by a cell edit.
            for key in set(old_items[iid]) | set(new_items[iid]):
                if key != "body":
                    require(old_items[iid].get(key) == new_items[iid].get(key), "other item fields require separate scoped revision: " + key)
        else:
            require(new_items[iid] == old_items[iid] and before[iid] == after[iid], "unselected item changed: " + iid)
    changed_dialogue = []
    old_lines = {x["id"]: x for x in bundle.get("dialogue", [])}
    new_lines = {x["id"]: x for x in candidate.get("dialogue", [])}
    require(list(old_lines) == list(new_lines), "dialogue addition/removal requires explicit separate revision")
    for did in old_lines:
        if old_lines[did] != new_lines[did]:
            changed_dialogue.append(did)
            require(any("[dialogue:" + did in old_items[i]["body"] for i in accepted), "dialogue changed outside selected scope")
    revised = copy.deepcopy(candidate)
    if bundle['kind'] == 'previs':
        pending = revised.setdefault('derivation_pending', {})
        for iid in accepted:
            pending[iid] = digest(after[iid]['body'])
    return revised, {"format": "suh-feedback-application/1", "base_sha256": digest(bundle),
        "candidate_sha256": digest(revised), "accepted_body_edits": accepted,
        "changed_dialogue_ids": changed_dialogue, "evidence_ref": evidence_ref, "evidence_text": evidence_text,
        "derivation_pending": list(revised.get('derivation_pending', {})),
        "comments": patch.get("comments", []), "adoption_status": "not_recorded_by_application",
        "note": "Applied only selected literal edits to a new candidate. Agent must review semantic/timing consequences and record actual adoption separately."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("export")
    p.add_argument("bundle", type=Path); p.add_argument("--out", type=Path, required=True)
    p.add_argument("--xlsx", action="store_true"); p.add_argument("--node"); p.add_argument("--node-modules"); p.add_argument("--render", action="store_true")
    p = sub.add_parser("import-feedback")
    p.add_argument("bundle", type=Path); p.add_argument("feedback", type=Path); p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("apply-feedback")
    p.add_argument("bundle", type=Path); p.add_argument("patch", type=Path); p.add_argument("--candidate", type=Path, required=True)
    p.add_argument("--accept", nargs="+", required=True); p.add_argument("--evidence-ref", required=True); p.add_argument("--evidence-text", required=True); p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        bundle = deliver.load(args.bundle)
        if args.command == "export":
            result = export(bundle, args.out, args.xlsx, args.node, args.node_modules, args.render)
        elif args.command == "import-feedback":
            feedback = read_xlsx(args.feedback, make_manifest(bundle)) if args.feedback.suffix.lower() == ".xlsx" else deliver.load(args.feedback)
            result = extract_feedback(bundle, feedback, str(args.feedback.resolve()))
            write_json(args.out, result)
        else:
            revised, result = apply_feedback(bundle, deliver.load(args.patch), deliver.load(args.candidate), args.accept, args.evidence_ref, args.evidence_text)
            require(not args.out.exists(), "output exists")
            args.out.mkdir(parents=True)
            write_json(args.out / "Bundle.json", revised); write_json(args.out / "Feedback-application.json", result)
    except (ValueError, OSError, KeyError, ET.ParseError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(2, "Review delivery failed: " + str(error) + "\n")
    print(json.dumps({"saved": str(args.out), "status": result.get("status", "completed_without_adoption")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
