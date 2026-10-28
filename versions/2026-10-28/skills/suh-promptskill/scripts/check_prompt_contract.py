#!/usr/bin/env python3
"""Read-only Prompt format, planned Cut time and duration checks (Python 3.9+).

Agent-authored context, separate from delivery Bundles:
  {"format":"suh-prompt-contract/1", "has_storyboard":true,
   "timestamp_policy":"required", "units":[{"id":"G01",
   "total_duration_seconds":"7", "prompt_path":"G01.txt"}]}
Use exactly one of prompt_text / prompt_path per unit. Relative paths resolve
against the context file, never the current working directory. Totals remain in
this execution context; no total-duration field is imposed on the Prompt body.
Without storyboard, not_applicable permits an absent/null total unless actual
Cut ranges are written. Storyboard totals are mandatory, including exemptions.
Every declared generation-unit total must be an integer number of seconds and
within the selected profile's inclusive range. The default profile is the
package's references/Generation-profile.json, sourced from the current user
request. --profile selects an explicit replacement with required source fields;
it cannot disable the integer-total user rule. No rounding or rewriting occurs.
Cut boundaries inside that integer total may still be fractional seconds.

Policy: required; explicit_user_omission (requires timestamp_omission with role
"user", source and excerpt); not_applicable (only without storyboard). Evidence
fields are declarations, not verified natural-language authorization. No title
or keyword, including "quick test", is interpreted as an exemption.

Structural headings occupy separate lines. Cut headers use Cut 1, Cut 2, ...;
recommended timed form: Cut 1｜0—3.5秒. Decimal seconds, hyphen/en/em dash,
tilde/Chinese tilde/至 and s/秒 are accepted. A header may end in a colon and
its action may follow that colon or a vertical bar. No clock/frame timecodes.
Literal {...} spans are ignored when finding structural headings and markers.

stdout is JSON. Exit 0: listed deterministic checks passed; 1: body contract
errors; 2: malformed/unreadable context. This is not generation, dialogue,
source, capacity, artistic, authorization or media certification.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sys


FORMAT = "suh-prompt-contract/1"
PROFILE_FORMAT = "suh-generation-profile/1"
DEFAULT_PROFILE = Path(__file__).resolve().parents[1] / "references" / "Generation-profile.json"
REPORT_FORMAT = "suh-prompt-contract-report/1"
HEADINGS = ("生成目标", "参考素材职责", "主体、关系与场景", "镜头脚本", "声音与台词", "保持一致")
REQUIRED = ("生成目标", "主体、关系与场景", "镜头脚本", "保持一致")
NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
TOKEN = r"(?:" + NUMBER + r"|[+-]?(?:s?NaN|Inf(?:inity)?))"
RANGE = re.compile(r"^(?P<start>" + TOKEN + r")\s*(?:秒|s)?\s*"
                   r"(?:—|–|-|~|～|至)\s*(?P<end>" + TOKEN + r")\s*(?:秒|s)"
                   r"\s*(?:(?:[：:｜|])\s*.*)?$", re.IGNORECASE)
HEADING = re.compile(r"^\s*【([^】\n]+)】\s*$")
CUT_START = re.compile(r"^\s*(?:#{1,6}\s+)?(?:\*\*)?Cut(?=$|\s|[0-9｜|：:])", re.IGNORECASE)
CUT_HEADER = re.compile(r"^Cut\s+([0-9]+)(.*)$")
NOT_CHECKED = [
    "storyboard_context_truth", "content_based_total_estimation",
    "timestamp_omission_request_semantics_and_authenticity",
    "dialogue_fidelity_placement_and_completeness", "source_coverage",
    "live_platform_capabilities_and_profile_applicability", "media_frame_accuracy", "artistic_quality",
]


class InputError(ValueError):
    """Context cannot be used as a deterministic-check input."""


def nonempty_string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise InputError(label + " must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeError as exc:
        raise InputError(label + " must contain valid UTF-8 text") from exc
    return value


def decimal_seconds(value, label):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise InputError(label + " must be a finite decimal number")
    raw = str(value).strip()
    try:
        number = Decimal(raw)
    except InvalidOperation as exc:
        raise InputError(label + " must be a finite decimal number") from exc
    if not number.is_finite() or not re.fullmatch(NUMBER, raw):
        raise InputError(label + " must be a finite decimal number")
    return number


def keys(value, allowed, label):
    if not isinstance(value, dict):
        raise InputError(label + " must be an object")
    extra = set(value) - set(allowed)
    if extra:
        raise InputError(label + " has unsupported fields: " + ", ".join(sorted(extra)))


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def reject_constant(value):
    raise InputError("Non-finite JSON number: " + value)


def load_context(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object,
                      parse_float=lambda value: decimal_seconds(value, "JSON decimal"),
                      parse_constant=reject_constant)


def load_profile(path=None):
    """Load a sourced range; never infer an entry/provider from task words."""
    path = Path(path) if path is not None else DEFAULT_PROFILE
    data = load_context(path)
    keys(data, ("format", "id", "scope", "duration_seconds", "source"), "profile")
    if data.get("format") != PROFILE_FORMAT:
        raise InputError("Expected explicit profile format " + PROFILE_FORMAT)
    for field in ("id", "scope"):
        nonempty_string(data.get(field), "profile." + field)
    source = data.get("source")
    keys(source, ("kind", "reference", "summary"), "profile.source")
    for field in ("kind", "reference", "summary"):
        nonempty_string(source.get(field), "profile.source." + field)
    bounds = data.get("duration_seconds")
    keys(bounds, ("min", "max"), "profile.duration_seconds")
    minimum = decimal_seconds(bounds.get("min"), "profile.duration_seconds.min")
    maximum = decimal_seconds(bounds.get("max"), "profile.duration_seconds.max")
    if minimum <= 0 or maximum < minimum:
        raise InputError("Profile duration range must be positive and ordered (min <= max)")
    if any(value != value.to_integral_value() for value in (minimum, maximum)):
        raise InputError("Profile duration range endpoints must be integer seconds")
    return {"id": data["id"], "scope": data["scope"], "path": str(path.resolve()),
            "duration_seconds": {"min": str(minimum), "max": str(maximum)},
            "source": source,
            "applicability": "agent_selected_source_declaration_not_automatically_verified"}


def prepare_context(data, base_dir):
    keys(data, ("format", "has_storyboard", "timestamp_policy", "timestamp_omission", "units"), "context")
    if data.get("format") != FORMAT:
        raise InputError("Expected explicit format " + FORMAT)
    if type(data.get("has_storyboard")) is not bool:
        raise InputError("has_storyboard must be an explicit boolean")
    policy = data.get("timestamp_policy")
    if policy not in ("required", "explicit_user_omission", "not_applicable"):
        raise InputError("timestamp_policy must be required, explicit_user_omission or not_applicable")
    if data["has_storyboard"] and policy == "not_applicable":
        raise InputError("A storyboard cannot use timestamp_policy=not_applicable")
    if policy == "explicit_user_omission":
        evidence = data.get("timestamp_omission")
        keys(evidence, ("role", "source", "excerpt"), "timestamp_omission")
        if evidence.get("role") != "user":
            raise InputError("timestamp_omission.role must explicitly be user")
        nonempty_string(evidence.get("source"), "timestamp_omission.source")
        nonempty_string(evidence.get("excerpt"), "timestamp_omission.excerpt")
    elif "timestamp_omission" in data:
        raise InputError("timestamp_omission is only valid with explicit_user_omission")
    units = data.get("units")
    if not isinstance(units, list) or not units:
        raise InputError("units must be a non-empty list")
    prepared, seen = [], set()
    for i, unit in enumerate(units):
        label = "units[{}]".format(i)
        keys(unit, ("id", "total_duration_seconds", "prompt_text", "prompt_path"), label)
        uid = nonempty_string(unit.get("id"), label + ".id")
        if uid in seen:
            raise InputError("Duplicate unit id: " + uid)
        seen.add(uid)
        total = None
        if unit.get("total_duration_seconds") is not None or data["has_storyboard"] or policy != "not_applicable":
            total = decimal_seconds(unit.get("total_duration_seconds"), label + ".total_duration_seconds")
            if total <= 0:
                raise InputError(label + ".total_duration_seconds must be positive")
        if ("prompt_text" in unit) == ("prompt_path" in unit):
            raise InputError(label + " must contain exactly one of prompt_text / prompt_path")
        if "prompt_path" in unit:
            path = Path(nonempty_string(unit["prompt_path"], label + ".prompt_path"))
            if not path.is_absolute():
                path = Path(base_dir) / path
            prompt = path.read_text(encoding="utf-8-sig")
            source = str(path.resolve())
        else:
            prompt, source = unit["prompt_text"], "inline:prompt_text"
        nonempty_string(prompt, label + ".prompt_text")
        prepared.append((uid, total, prompt, source))
    return prepared


def structural_lines(text):
    """Mask literal brace spans, preserving offsets/newlines; do not parse speech."""
    depth, result = 0, []
    for char in text:
        if char == "{":
            depth += 1
            result.append(" ")
        elif char == "}" and depth:
            depth -= 1
            result.append(" ")
        elif depth and char not in "\r\n":
            result.append(" ")
        else:
            result.append(char)
    return "".join(result).splitlines()


def check_unit(uid, total, prompt, source, has_storyboard, policy, profile):
    errors, headings, cuts = [], [], []
    lines = structural_lines(prompt)
    original_lines = prompt.splitlines()

    def error(code, message, line=None):
        issue = {"code": code, "message": message}
        if line is not None:
            issue["line"] = line
        errors.append(issue)

    if total is not None:
        if total != total.to_integral_value():
            error("total_duration_not_integer", "Declared generation-unit total must be an integer number of seconds; do not round it automatically.")
        bounds = profile["duration_seconds"]
        if not Decimal(bounds["min"]) <= total <= Decimal(bounds["max"]):
            error("total_duration_out_of_profile_range", "Declared generation-unit total must be within the selected profile's inclusive {}–{} second range.".format(bounds["min"], bounds["max"]))

    for index, line in enumerate(lines, 1):
        heading = HEADING.fullmatch(line)
        if heading:
            headings.append((heading.group(1), index))
        if re.search(r"\[dialogue:[^\]\n]*(?:\]|$)", line, re.IGNORECASE):
            error("unexpanded_dialogue_marker", "Expand the literal [dialogue:...] marker in the actual body.", index)
        if CUT_START.match(line):
            normalized = re.sub(r"^\s*(?:#{1,6}\s+)?", "", line).replace("**", "").strip()
            match = CUT_HEADER.fullmatch(normalized)
            cut = {"number": None, "line": index, "start_seconds": None, "end_seconds": None}
            cuts.append(cut)
            if not match:
                error("cut_header_invalid", "Use numbered Cut headers: Cut 1, Cut 2, ...", index)
                continue
            number, tail = match.groups()
            cut["number"] = number
            if number != str(len(cuts)):
                error("cut_number_sequence", "Cut numbers must be consecutive canonical integers starting at 1.", index)
            tail = tail.strip()
            if not tail or tail in ("：", ":"):
                continue
            # A colon introduces untimed prose; a bar introduces a planned range.
            if tail[0] in "：:":
                tail = tail[1:].strip()
                if not tail or not re.match(r"[+\-.0-9]|s?NaN|Inf", tail, re.IGNORECASE):
                    continue
            elif tail[0] in "｜|":
                tail = tail[1:].strip()
            timed = RANGE.fullmatch(tail)
            if not timed:
                error("cut_time_invalid", "Expected a finite seconds range such as 0—3.5秒, or an untimed Cut header.", index)
                continue
            try:
                start = decimal_seconds(timed.group("start"), "Cut start")
                end = decimal_seconds(timed.group("end"), "Cut end")
            except InputError as exc:
                error("cut_time_invalid", str(exc), index)
                continue
            cut["start_seconds"], cut["end_seconds"] = str(start), str(end)
            if start < 0 or end <= start:
                error("cut_interval_not_positive", "Cut intervals must start at or after zero and have positive duration.", index)

    structured = has_storyboard or bool(cuts) or bool(headings)
    if structured:
        names = [name for name, _ in headings]
        for name in REQUIRED:
            if name not in names:
                error("section_missing", "Missing required standalone heading 【" + name + "】.")
        seen, last = set(), -1
        for name, line in headings:
            if name == "未采用素材":
                error("section_forbidden", "【未采用素材】 is not part of the requested final Prompt body.", line)
                continue
            if name not in HEADINGS:
                error("section_unknown", "Unknown body heading 【" + name + "】.", line)
                continue
            order = HEADINGS.index(name)
            if name in seen:
                error("section_duplicate", "Duplicate body heading 【" + name + "】.", line)
            if order < last:
                error("section_order", "Body headings are not in the required order.", line)
            seen.add(name)
            last = max(last, order)
        if headings and any(line.strip() for line in original_lines[:headings[0][1] - 1]):
            error("body_prefix", "Read the independent Prompt body without a document title or code fence.")
        for position, (name, line) in enumerate(headings):
            stop = headings[position + 1][1] - 1 if position + 1 < len(headings) else len(original_lines)
            if not any(part.strip() for part in original_lines[line:stop]):
                error("section_empty", "Body heading 【" + name + "】 has no content.", line)
        if any(re.match(r"^\s*(?:`{3,}|~{3,})", line) for line in lines):
            error("body_code_fence", "Check the independent Prompt body, without surrounding code fences.")
        for cut in cuts:
            preceding = [name for name, line in headings if line < cut["line"]]
            if not preceding or preceding[-1] != "镜头脚本":
                error("cut_outside_script", "Cut headers must be inside 【镜头脚本】.", cut["line"])

    if has_storyboard and not cuts:
        error("storyboard_cuts_missing", "A storyboard requires numbered Cuts, including a single continuous shot.")
    timed = [cut for cut in cuts if cut["start_seconds"] is not None]
    if timed and len(timed) != len(cuts):
        error("cut_times_partial", "Do not mix timed and untimed Cuts, even with an omission declaration.")
    elif cuts and not timed and policy == "required":
        error("cut_times_required", "All storyboard Cuts need planned ranges unless the user explicitly requested omission.")
    if timed:
        if total is None:
            raise InputError("Unit " + uid + " contains actual Cut ranges and requires total_duration_seconds")
        if Decimal(timed[0]["start_seconds"]) != 0:
            error("cut_start_not_zero", "The planned Cut timeline must start at zero.", timed[0]["line"])
        for previous, current in zip(timed, timed[1:]):
            prior_end, start = Decimal(previous["end_seconds"]), Decimal(current["start_seconds"])
            if start < prior_end:
                error("cut_overlap_or_reverse", "Planned Cuts overlap or run in reverse order.", current["line"])
            elif start > prior_end:
                error("cut_gap", "Planned Cuts must have no gaps.", current["line"])
        if Decimal(timed[-1]["end_seconds"]) != total:
            error("cut_end_total_mismatch", "The final Cut end must equal this unit's declared planned total.", timed[-1]["line"])
    timing = "checked" if timed else ("omitted_by_explicit_declaration" if cuts and policy == "explicit_user_omission" else "not_applicable")
    if any(issue["code"].startswith(("cut_", "storyboard_")) for issue in errors):
        timing = "failed"
    duration_check = "not_applicable" if total is None else "checked_against_declared_profile"
    if any(issue["code"].startswith("total_duration_") for issue in errors):
        duration_check = "failed"
    return {"id": uid, "total_duration_seconds": str(total) if total is not None else None, "prompt_source": source,
            "structure": "structured" if structured else "natural_paragraphs",
            "cut_count": len(cuts), "timing": timing, "duration_check": duration_check,
            "cuts": cuts, "errors": errors}


def report_base(status):
    return {"format": REPORT_FORMAT, "status": status,
            "check_scope": "deterministic_prompt_structure_planned_cut_timing_and_declared_duration_profile",
            "context_basis": "agent_declarations_not_automatically_inferred_or_verified",
            "not_checked": list(NOT_CHECKED)}


def check_context(data, base_dir=Path("."), profile_path=None):
    profile = load_profile(profile_path)
    prepared = prepare_context(data, base_dir)
    units = [check_unit(*unit, data["has_storyboard"], data["timestamp_policy"], profile) for unit in prepared]
    report = report_base("failed" if any(unit["errors"] for unit in units) else "passed")
    report.update({"has_storyboard": data["has_storyboard"], "timestamp_policy": data["timestamp_policy"],
                   "timestamp_omission_evidence": "declared_fields_present_semantics_not_checked"
                   if data["timestamp_policy"] == "explicit_user_omission" else "not_applicable",
                   "total_duration_rule": "integer_seconds_user_requirement",
                   "generation_profile": profile, "units": units})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, required=True, help="Agent-authored context JSON; read only")
    parser.add_argument("--profile", type=Path, help="Explicit sourced duration profile; defaults to the package's current user profile")
    args = parser.parse_args(argv)
    try:
        report = check_context(load_context(args.input), args.input.resolve().parent, args.profile)
    except (ValueError, OSError, UnicodeError) as exc:
        report = report_base("invalid_input")
        report.update({"errors": [{"code": "invalid_input", "message": str(exc)}], "units": []})
        code = 2
    else:
        code = 0 if report["status"] == "passed" else 1
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
