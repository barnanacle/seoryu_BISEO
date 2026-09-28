"""Named, reusable field transformations referenced by pack.json."""
from __future__ import annotations

import copy
import datetime
import re

UNKNOWN = "【확인 필요】"


def normalized_address(value: str) -> str:
    return re.sub(r"\s*\n\s*(?=\()", "", str(value).strip()).replace("\n", " ")


def _date_parts(value: str):
    match = re.fullmatch(r"\s*(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*", str(value))
    return match.groups() if match else None


def derive(fields: dict, target: str, rule: dict) -> str:
    name = rule["name"]
    source = str(fields.get(rule.get("source", ""), ""))
    if name == "parenthesized":
        value = str(fields.get(target, source))
        return "(" + value + ")" if value and not value.lstrip().startswith("(") else value
    if name == "normalized_address":
        return normalized_address(source or UNKNOWN)
    if name == "dot_date":
        parts = _date_parts(source)
        return ".   ".join(str(int(v)) for v in parts) + "." if parts else UNKNOWN
    if name == "date_component":
        parts = _date_parts(source)
        if not parts:
            return ""
        year, month, day = map(int, parts)
        datetime.date(year, month, day)
        return str((year, month, day)[int(rule["component"])])
    if name == "opinion_signature":
        if target in fields:
            return str(fields[target])
        direct, company, representative = (str(fields.get(key, "")) for key in rule["sources"])
        return direct or company + (" 대표 " + representative if representative else "") or UNKNOWN
    raise ValueError("알 수 없는 파생 규칙: " + name)


def normalize_fields(fields: dict, pack: dict) -> dict:
    result = copy.deepcopy(fields)
    cfg = pack.get("normalization", {})
    repeat = cfg.get("repeat")
    if repeat:
        key, prefix = repeat["field"], repeat["legacy_prefix"]
        title, body = repeat["item_fields"]
        if key not in result:
            indices = sorted({int(match.group(1)) for name in result
                              for match in [re.match(re.escape(prefix) + r"(\d+)_", name)] if match})
            result[key] = [{title: result.get(f"{prefix}{number}_{title}", UNKNOWN),
                            body: result.get(f"{prefix}{number}_{body}", UNKNOWN)} for number in indices]
        if not isinstance(result[key], list):
            raise ValueError(key + "은 배열이어야 합니다.")
        for item in result[key]:
            if not isinstance(item, dict) or not all(isinstance(item.get(name), str) for name in (title, body)):
                raise ValueError(key + " 항목에 " + title + "·" + body + " 문자열이 필요합니다.")
    for name, value in cfg.get("defaults", {}).items():
        result.setdefault(name, value)
    for name, rule in cfg.get("derived", {}).items():
        result[name] = derive(result, name, rule)
    for name in cfg.get("required", []):
        if not str(result.get(name, "")).strip():
            result[name] = UNKNOWN
    for name, spec in pack.get("fields", {}).items():
        if name in result and spec["type"] != "repeat" and not isinstance(result[name], str):
            raise ValueError("필드 값은 문자열이어야 합니다: " + name)
    return result


def form_values(fields: dict, pack: dict, *, page: int = 0):
    specs = pack["pages"][page]["fields"]
    values = {name: str(fields.get(name) or ("" if spec.get("blank_if_missing") else UNKNOWN))
              for name, spec in specs.items()}
    representative = False
    for name, rule in pack.get("transforms", {}).items():
        if name not in values:
            continue
        kind = rule["name"]
        if kind == "normalized_address":
            values[name] = normalized_address(values[name])
        elif kind == "korean_date":
            parts = _date_parts(values[name])
            if parts:
                year, month, day = map(int, parts)
                datetime.date(year, month, day)
                values[name] = f"{year}년    {month}월    {day}일"
            else:
                values[name] = UNKNOWN
        elif kind == "representative_signature":
            signature = str(fields.get(rule["representative"], "")).strip()
            company = str(fields.get(rule["company"], "")).strip()
            full = values[name].strip()
            if not signature and company and full.startswith(company + " 대표 "):
                signature = full[len(company + " 대표 "):].strip()
            if signature and len(signature) <= 5 and re.fullmatch(r"[가-힣]+", signature):
                values[name] = "대표   " + "   ".join(signature)
                representative = True
        else:
            raise ValueError("알 수 없는 서식 변환: " + kind)
    return values, representative
