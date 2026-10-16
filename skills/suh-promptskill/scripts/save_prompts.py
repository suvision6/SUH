#!/usr/bin/env python3
"""Export authored prompts without rewriting or evaluating their meaning."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


FORMAT = "suh-prompt-bundle/1"
LEGACY = "su-prompt-plan/2.2"
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10))}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"Non-finite JSON number: {value}")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def read_bundle(path: Path, legacy: bool = False):
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)
    allowed = LEGACY if legacy else FORMAT
    if not isinstance(data, dict) or data.get("format") != allowed:
        raise ValueError(f"Expected explicit format {allowed}")
    units = data.get("units")
    if not isinstance(units, list) or not units:
        raise ValueError("units must be a non-empty list")
    seen = set()
    for unit in units:
        if not isinstance(unit, dict):
            raise ValueError("Each unit must be an object")
        uid, prompt = unit.get("id"), unit.get("prompt_text")
        if not isinstance(uid, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", uid):
            raise ValueError("Unsafe unit id")
        if uid.casefold() in RESERVED or uid.casefold() in seen:
            raise ValueError(f"Reserved or case-colliding unit id: {uid}")
        seen.add(uid.casefold())
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError(f"Missing authored prompt_text: {uid}")
        # Validate UTF-8 before creating any output directory; do not strip/normalize.
        prompt.encode("utf-8")
    json_bytes(data)
    return data, raw


def markdown_bytes(units) -> bytes:
    parts = ["# Prompt正文\n\n"]
    for unit in units:
        prompt = unit["prompt_text"]
        longest = max((len(x) for x in re.findall(r"`+", prompt)), default=0)
        fence = "`" * max(3, longest + 1)
        parts.append(f"## {unit['id']}\n\n{fence}text\n{prompt}")
        if not prompt.endswith("\n"):
            parts.append("\n")
        parts.append(f"{fence}\n\n")
    return "".join(parts).encode("utf-8")


def export_bundle(input_path: Path, output: Path, legacy: bool = False):
    data, raw = read_bundle(input_path, legacy)
    payloads = {"Bundle.json": json_bytes(data), "Prompts.md": markdown_bytes(data["units"])}
    for unit in data["units"]:
        payloads[f"prompts/{unit['id']}.txt"] = unit["prompt_text"].encode("utf-8")
    # mkdir is exclusive even for a symlink; never follow an existing output directory.
    output.mkdir(exist_ok=False)
    (output / "prompts").mkdir()
    for name, content in payloads.items():
        with (output / name).open("xb") as stream:
            stream.write(content)
    for name, content in payloads.items():
        if (output / name).read_bytes() != content:
            raise OSError(f"Readback mismatch: {name}")
    report = {
        "format": "suh-prompt-integrity/1",
        "skill_version": (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip(),
        "input_sha256": digest(raw),
        "input_format": data["format"],
        "legacy_text_import": legacy,
        "file_integrity": "checked",
        "source_coverage": "not_checked",
        "dialogue_semantics": "not_checked",
        "platform_limits": "not_checked",
        "media_effects": "not_checked",
        "files": [{"path": name, "sha256": digest(content)} for name, content in payloads.items()],
    }
    with (output / "Integrity.json").open("xb") as stream:
        stream.write(json_bytes(report))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--legacy", action="store_true", help="Explicitly read authored su-prompt-plan/2.2")
    args = parser.parse_args(argv)
    try:
        report = export_bundle(args.input, args.output, args.legacy)
    except (ValueError, OSError, UnicodeError) as exc:
        print(json.dumps({"error": str(exc), "completed": False}, ensure_ascii=False))
        return 1
    print(json.dumps({"file_integrity": report["file_integrity"], "output": str(args.output),
                      "units": len(report["files"]) - 2, "semantic_and_media_review": "not_performed"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
