"""Configuration and pure resource-to-speech planning."""

import copy
import csv
from dataclasses import dataclass
import math
from pathlib import Path
import re
import tomllib


DEFAULTS = {
    "voices": {"chinese": "zh-CN-XiaoxiaoNeural", "english": "en-US-AvaMultilingualNeural"},
    "rates": {"vocabulary": "+25%", "chinese": "+0%", "english": "+100%", "chinese_slow": "-20%"},
    "pauses": {"term_to_meaning": 0.05, "between_entries": 0.5, "between_sections": 1.5},
    "inputs": {"vocabulary": "vocab_list.csv", "chinese": "transcript.txt", "english": "transcript_english.txt"},
    "podcast": {
        "sections": ["chinese_slow", "vocabulary", "english", "chinese"],
        "omit_lines": [r"约\s*\d+\s*分钟播客单口文字稿", r"A roughly \d+-minute solo podcast script"],
    },
}


def load_config(paths: list[Path]) -> dict:
    config = copy.deepcopy(DEFAULTS)
    for path in paths:
        with path.open("rb") as stream:
            overrides = tomllib.load(stream)
        for table, values in overrides.items():
            if table not in config or not isinstance(values, dict):
                raise ValueError(f"{path}: unknown configuration table {table!r}")
            for key, value in values.items():
                if key not in config[table]:
                    raise ValueError(f"{path}: unknown setting {table}.{key}")
                config[table][key] = value
    for name, rate in config["rates"].items():
        if not isinstance(rate, str) or not re.fullmatch(r"[+-]\d+%", rate) or int(rate[:-1]) <= -100:
            raise ValueError(f"rates.{name} must be a signed percentage greater than -100%")
    for name, pause in config["pauses"].items():
        if type(pause) not in (int, float) or not math.isfinite(pause) or pause < 0:
            raise ValueError(f"pauses.{name} must be a finite nonnegative number")
    for table in ("voices", "inputs"):
        for name, value in config[table].items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{table}.{name} must be a nonempty string")
    sections = config["podcast"]["sections"]
    if not isinstance(sections, list) or not sections or any(
        not isinstance(s, str) or s not in DEFAULTS["podcast"]["sections"] for s in sections
    ) or len(set(sections)) != len(sections):
        raise ValueError("podcast.sections must be a nonempty list of unique supported sections")
    patterns = config["podcast"]["omit_lines"]
    if not isinstance(patterns, list) or any(not isinstance(p, str) for p in patterns):
        raise ValueError("podcast.omit_lines must be a list of regular expressions")
    for pattern in patterns:
        re.compile(pattern)
    return config


def read_transcript(path: Path, omit_lines: list[str]) -> list[str]:
    """Keep headings and paragraphs; omit only explicit full-line notes/markup."""
    lines = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if re.fullmatch(r"([-*_])(?:\s*\1){2,}", line):
            lines.append("")
            continue
        line = re.sub(r"^#{1,6}\s+", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if any(re.fullmatch(pattern, line) for pattern in omit_lines):
            continue
        lines.append(line)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(lines)) if p.strip()]
    if not paragraphs:
        raise ValueError(f"{path}: no spoken text remains")
    return paragraphs


def read_vocabulary(path: Path) -> list[tuple[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"chinese", "english"}.issubset(reader.fieldnames or []):
            raise ValueError(f"{path}: vocabulary requires chinese and english columns")
        entries = []
        for row in reader:
            if None in row or not row.get("chinese") or not row.get("english"):
                raise ValueError(f"{path}: malformed or incomplete CSV row at line {reader.line_num}")
            chinese, english = row["chinese"].strip(), row["english"].strip()
            if not chinese or not english:
                raise ValueError(f"{path}: blank term or meaning at line {reader.line_num}")
            entries.append((chinese, english))
    if not entries:
        raise ValueError(f"{path}: vocabulary is empty")
    return entries


@dataclass(frozen=True)
class Speech:
    text: str
    voice: str
    rate: str


@dataclass(frozen=True)
class Silence:
    seconds: float


def build_plan(folder: Path, config: dict) -> list[tuple[str, list[Speech | Silence]]]:
    plan = []
    for section in config["podcast"]["sections"]:
        items = []
        if section == "vocabulary":
            entries = read_vocabulary(folder / config["inputs"]["vocabulary"])
            for index, (chinese, english) in enumerate(entries):
                if index:
                    items.append(Silence(config["pauses"]["between_entries"]))
                items.extend([
                    Speech(chinese, config["voices"]["chinese"], config["rates"][section]),
                    Silence(config["pauses"]["term_to_meaning"]),
                    Speech(english, config["voices"]["english"], config["rates"][section]),
                ])
        else:
            language = "english" if section == "english" else "chinese"
            for paragraph in read_transcript(folder / config["inputs"][language], config["podcast"]["omit_lines"]):
                items.append(Speech(paragraph, config["voices"][language], config["rates"][section]))
        plan.append((section, items))
    return plan
