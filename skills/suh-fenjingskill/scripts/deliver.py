#!/usr/bin/env python3
"""Local text delivery. Structural evidence only; never invokes a media provider."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
RESERVED = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])\Z", re.I)
TOKEN = re.compile(r"\[dialogue:([^\]\n]+)\]")
REFERENCE = re.compile(r"([A-Za-z][A-Za-z0-9_-]{0,63})(?:@([0-9]+):([0-9]+))?\Z")
HANZI = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f]")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value, label):
    require(isinstance(value, str) and bool(value.strip()), label + " must be nonempty text")


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON key: " + key)
        obj[key] = value
    return obj


def load(path):
    def bad_number(value):
        raise ValueError("non-finite JSON value: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      object_pairs_hook=unique_object, parse_constant=bad_number)


def records(value, name, allow_empty=False):
    require(isinstance(value, list), name + " must be a list")
    require(allow_empty or bool(value), name + " must not be empty")
    indexed = {}
    folded = set()
    for record in value:
        require(isinstance(record, dict), name + " record must be an object")
        rid = record.get("id")
        require(isinstance(rid, str) and ID.fullmatch(rid), name + " has unsafe/invalid id")
        require(not RESERVED.fullmatch(rid), name + " has reserved filename id")
        require(rid not in indexed, name + " has duplicate id: " + rid)
        require(rid.casefold() not in folded, name + " has case-colliding id: " + rid)
        folded.add(rid.casefold())
        indexed[rid] = record
    return indexed


def prepare(bundle):
    require(isinstance(bundle, dict), "bundle must be an object")
    require(bundle.get("format") == "suh-delivery/1", "unsupported format")
    kind = bundle.get("kind")
    require(kind in ("scene", "previs", "prompt"), "unsupported kind")
    nonempty(bundle.get("title"), "title")
    sources = records(bundle.get("source_units"), "source_units")
    lines = records(bundle.get("dialogue", []), "dialogue", allow_empty=True)
    items = records(bundle.get("items"), "items")
    for src in sources.values():
        nonempty(src.get("text"), "source text")
    for line in lines.values():
        nonempty(line.get("speaker"), "dialogue speaker")
        nonempty(line.get("text"), "dialogue text")
        require(isinstance(line.get("placement", ""), str), "placement must be text")
        require("[dialogue:" not in line["text"], "dialogue text contains reserved marker")
    covered, spoken, rendered = set(), [], {}
    order = list(lines)
    progress = {did: 0 for did in order}
    modes = {}
    for iid, item in items.items():
        nonempty(item.get("body"), iid + " body")
        refs = item.get("source_ids")
        require(isinstance(refs, list) and bool(refs), iid + " needs source_ids")
        require(all(isinstance(s, str) and s in sources for s in refs), iid + " references unknown source")
        require(len(refs) == len(set(refs)), iid + " repeats source id")
        covered.update(refs)
        placements = item.get("dialogue_placements", {})
        require(isinstance(placements, dict), iid + " dialogue_placements must be an object")
        require(all(did in lines and isinstance(value, str) and value.strip()
                    for did, value in placements.items()), iid + " invalid dialogue placement override")
        used = set()
        def expand(match):
            parsed = REFERENCE.fullmatch(match.group(1))
            require(parsed is not None, iid + " has invalid dialogue reference: " + match.group(1))
            did, start, end = parsed.groups()
            require(did in lines, iid + " references unknown dialogue: " + did)
            line = lines[did]
            mode = "whole" if start is None else "fragment"
            require(did not in modes or modes[did] == mode, "cannot mix whole and fragmented dialogue: " + did)
            modes[did] = mode
            start, end = (0, len(line["text"])) if mode == "whole" else (int(start), int(end))
            require(0 <= start < end <= len(line["text"]), "dialogue fragment out of bounds: " + did)
            require(len(spoken) < len(order) and did == order[len(spoken)],
                    "dialogue occurrences/order must exactly match the effective source ledger")
            require(start == progress[did], "dialogue fragment missing, repeated or reversed: " + did)
            progress[did] = end
            used.add(did)
            if end == len(line["text"]):
                spoken.append(did)
            placement = placements.get(did, line.get("placement", ""))
            who = line["speaker"] + ("（" + placement + "）" if placement else "")
            text = line["text"][start:end]
            continuation = "继续说" if start else "说"
            if kind == "prompt":
                return who + continuation + "：{" + text + "}"
            return who + ("继续" if start else "") + "：“" + text + "”"
        body = TOKEN.sub(expand, item["body"])
        require("[dialogue:" not in body, iid + " has malformed dialogue marker")
        require(set(placements) <= used, iid + " has unused dialogue placement override")
        require(kind != "prompt" or "copy_text" not in item, "prompt copy must derive from body")
        copy = item.get("copy_text", body)
        nonempty(copy, iid + " copy_text")
        require("[dialogue:" not in copy, iid + " copy_text cannot contain dialogue markers")
        rendered[iid] = {"body": body, "copy_text": copy, "source_ids": refs}
    require(covered == set(sources), "uncovered declared sources: " + ", ".join(sorted(set(sources) - covered)))
    require(spoken == list(lines), "dialogue occurrences/order must exactly match the effective source ledger")
    return rendered


def digest(data):
    return hashlib.sha256(data).hexdigest()


def deliver(bundle, output, previous=None):
    rendered = prepare(bundle)
    prior = prepare(previous) if previous is not None else None
    if previous is not None:
        require(previous["kind"] == bundle["kind"], "previous kind differs")
    output = Path(output)
    require(not output.exists(), "output exists; choose a new version directory")
    payloads = {"Bundle.json": (json.dumps(bundle, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")}
    master = ["# " + bundle["title"], ""]
    for iid, item in rendered.items():
        master.extend(["## " + iid, "", item["body"], ""])
        payloads["items/" + iid + ".md"] = item["body"].encode("utf-8")
        payloads["copy/" + iid + ".txt"] = item["copy_text"].encode("utf-8")
    payloads["Master.md"] = "\n".join(master).encode("utf-8")
    checks = {
        "format": "suh-delivery-checks/1", "kind": bundle["kind"],
        "declared_source_coverage": "pass", "declared_dialogue_order_and_occurrences": "pass",
        "declared_dialogue_fragment_reassembly": "pass",
        "scope": "Only supplied ledger IDs and rendered dialogue markers are checked. Unmarked dialogue, original-source completeness, semantics, timing and media quality are not certified.",
        "not_checked": ["original_source_semantic_completeness", "unmarked_dialogue", "camera_and_scene_logic", "timing", "media", "adoption_authority"],
        "items": [{"id": iid, "source_ids": item["source_ids"]} for iid, item in rendered.items()],
        "dialogue_counts": [{"id": line["id"], "hanzi_count": len(HANZI.findall(line["text"]))}
                            for line in bundle.get("dialogue", [])],
        "count_scope": "Literal Han characters only. Numerals, abbreviations, spoken expansion and performance pauses require separate timing review; these counts are not durations.",
        "files": {name: {"bytes": len(data), "sha256": digest(data)} for name, data in payloads.items()}
    }
    if prior is not None:
        checks["revision"] = {
            "added": [i for i in rendered if i not in prior],
            "removed": [i for i in prior if i not in rendered],
            "changed": [i for i in rendered if i in prior and rendered[i] != prior[i]],
            "unchanged": [i for i in rendered if i in prior and rendered[i] == prior[i]],
            "source_ledger_changed": previous["source_units"] != bundle["source_units"],
            "dialogue_ledger_changed": previous.get("dialogue", []) != bundle.get("dialogue", []),
            "meaning": "Text/declaration difference only; does not infer dependency or approval."
        }
    payloads["Checks.json"] = (json.dumps(checks, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.mkdir(parents=True, exist_ok=False)
    for relative, data in payloads.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as handle:
            handle.write(data)
        require(target.read_bytes() == data, "readback failed: " + relative)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    try:
        checks = deliver(load(args.input), args.out, load(args.previous) if args.previous else None)
    except (ValueError, OSError) as error:
        parser.exit(2, "Delivery failed: " + str(error) + "\n")
    print(json.dumps({"saved": str(args.out.resolve()), "items": len(checks["items"]), "semantic_status": "not_checked"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
