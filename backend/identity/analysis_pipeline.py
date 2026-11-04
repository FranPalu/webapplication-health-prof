"""Bounded local extraction. Source text never reaches the summary model."""

import csv
import hashlib
import json
import os
import re
import subprocess
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader

PIPELINE = "lab-v1:extract-v1:rules-v1:qwen-q4km"
OCR_WEIGHTS = {
    "ita": "b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827",
    "eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}
QWEN_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
DISCLAIMER = "Analisi automatica preliminare – non è una diagnosi"
UNITS = {
    "glucosio": ("mg/dL", "mmol/L"),
    "glucose": ("mg/dL", "mmol/L"),
    "creatinina": ("mg/dL", "µmol/L"),
    "emoglobina": ("g/dL", "g/L"),
    "colesterolo": ("mg/dL", "mmol/L"),
}
NUMBER = r"[+-]?\d{1,10}(?:[.,]\d{1,8})?"
ROW = re.compile(
    rf"\s*(?P<operator>[<>]?)\s*(?P<value>{NUMBER})\s+(?P<unit>\S+)"
    rf"(?:\s+(?P<low>{NUMBER})\s*[-–]\s*(?P<high>{NUMBER}))?\s*"
)


def decimal(value):
    return Decimal(value.replace(",", "."))


def classify(value, lower, upper, operator):
    if operator == "<":
        return "below" if value <= lower else "ambiguous"
    if operator == ">":
        return "above" if value >= upper else "ambiguous"
    if value < lower:
        return "below"
    if value > upper:
        return "above"
    return "within"


def extract(pages):
    rows: list[dict] = []
    for page, item in enumerate(pages, 1):
        text, source = item[:2]
        for number, line in enumerate(text.splitlines()[:1000], 1):
            clean = line.strip().casefold()
            analyte = next((name for name in UNITS if clean.startswith(name + " ")), None)
            if not analyte:
                if any(char.isdigit() for char in clean) and len(rows) < 100:
                    rows.append(
                        {
                            "id": f"{page}:{number}",
                            "page": page,
                            "line": number,
                            "source": source,
                            "flag": "unrecognized",
                        }
                    )
                continue
            row = {
                "id": f"{page}:{number}",
                "page": page,
                "line": number,
                "source": source,
                "analyte": analyte,
                "flag": "ambiguous",
            }
            match = ROW.fullmatch(line.strip()[len(analyte) :])
            if match:
                unit = match["unit"].replace("μ", "µ")
                value = decimal(match["value"])
                row.update(value=str(value), operator=match["operator"], unit=unit)
                if unit not in UNITS[analyte]:
                    row["flag"] = "unit_mismatch"
                elif match["low"] is None:
                    row["flag"] = "missing_range"
                else:
                    lower, upper = decimal(match["low"]), decimal(match["high"])
                    if lower <= upper:
                        row.update(
                            low=str(lower),
                            high=str(upper),
                            flag=classify(value, lower, upper, match["operator"]),
                        )
            rows.append(row)
            if len(rows) >= 100:
                return rows
    return rows


def command(args, *, input_data=None, timeout=30):
    return subprocess.run(
        args,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
        check=True,
        env={
            key: os.environ[key]
            for key in ("PATH", "LANG", "TESSDATA_PREFIX", "OMP_THREAD_LIMIT")
            if key in os.environ
        },
    ).stdout


def pages_from(data, media_type):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        if media_type != "application/pdf":
            path = root / "image"
            path.write_bytes(data)
            text, confidence = ocr(path)
            return [(text, "ocr", confidence)]
        reader = PdfReader(BytesIO(data), strict=True)
        if not 0 < len(reader.pages) <= 12:
            raise ValueError("Page limit")
        path = root / "report.pdf"
        path.write_bytes(data)
        pages = []
        for index, page in enumerate(reader.pages, 1):
            text = (page.extract_text() or "")[:50000]
            if not text.strip():
                prefix = root / "page"
                command(
                    [
                        "pdftoppm",
                        "-f",
                        str(index),
                        "-l",
                        str(index),
                        "-scale-to",
                        "2400",
                        "-png",
                        "-singlefile",
                        str(path),
                        str(prefix),
                    ]
                )
                text, confidence = ocr(prefix.with_suffix(".png"))
                pages.append((text, "ocr", confidence))
            else:
                pages.append((text, "embedded", None))
        return pages


def ocr(path):
    root = Path(os.environ.get("TESSDATA_PREFIX", "/opt/tessdata"))
    for language, checksum in OCR_WEIGHTS.items():
        with (root / (language + ".traineddata")).open("rb") as weights:
            if hashlib.file_digest(weights, "sha256").hexdigest() != checksum:
                raise ValueError("OCR model checksum mismatch")
    output = command(
        [
            "tesseract",
            str(path),
            "stdout",
            "-l",
            "ita+eng",
            "--psm",
            "6",
            "-c",
            "tessedit_create_tsv=1",
        ]
    )
    lines: dict[tuple[str, ...], list[str]] = {}
    scores = []
    for word in csv.DictReader(output.decode().splitlines(), delimiter="\t"):
        if word.get("level") != "5" or not word.get("text"):
            continue
        key = tuple(word[field] for field in ("block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(word["text"])
        confidence = float(word["conf"])
        if 0 <= confidence <= 100:
            scores.append(confidence)
    text = "\n".join(" ".join(words) for words in lines.values())[:50000]
    return text, round(sum(scores) / len(scores), 2) if scores else None


def summary(rows):
    # Only known codes and deterministic classifications enter the model. The
    # model selects row IDs; server-owned text renders the resulting summary.
    eligible = {row["id"]: row for row in rows if row["flag"] in ("below", "above", "within")}
    if not eligible:
        return None
    path = Path("/models/qwen.gguf")
    expected = QWEN_SHA256
    if not path.is_file():
        return None
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            return None
    payload = [
        {"id": key, "analyte": row["analyte"], "flag": row["flag"]}
        for key, row in list(eligible.items())[:30]
    ]
    allowed = {row["id"] for row in payload}
    schema = {
        "type": "object",
        "required": ["rows"],
        "additionalProperties": False,
        "properties": {
            "rows": {
                "type": "array",
                "minItems": 1,
                "maxItems": 5,
                "items": {"enum": sorted(allowed)},
            }
        },
    }
    prompt = (
        '<|im_start|>system\nReturn only JSON: {"rows":["ID"]}. Select up to '
        "five IDs, prioritizing above and below. Use only supplied IDs.<|im_end|>\n"
        "<|im_start|>user\n" + json.dumps(payload) + "<|im_end|>\n<|im_start|>assistant\n"
    )
    try:
        result = json.loads(
            command(
                [
                    "llama-cli",
                    "-m",
                    str(path),
                    "-n",
                    "96",
                    "-t",
                    "2",
                    "--temp",
                    "0",
                    "--seed",
                    "42",
                    "--no-display-prompt",
                    "--no-conversation",
                    "--json-schema",
                    json.dumps(schema),
                    "--simple-io",
                    "-p",
                    prompt,
                ],
                input_data=b"",
                timeout=60,
            )
            .decode()
            .strip()
            .removesuffix(" [end of text]")
        )
        refs = result["rows"]
        if set(result) != {"rows"} or not isinstance(refs, list) or not 0 < len(refs) <= 5:
            return None
        if any(not isinstance(ref, str) or ref not in allowed for ref in refs) or len(
            set(refs)
        ) != len(refs):
            return None
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return None
    return {"rows": refs, "checksum": expected}


def suggested_text(draft):
    summary_result = draft.get("summary")
    if not summary_result:
        return ""
    flags = {
        "below": "sotto l’intervallo riportato",
        "above": "sopra l’intervallo riportato",
        "within": "nell’intervallo riportato",
    }
    rows = {row["id"]: row for row in draft["rows"]}
    lines = []
    for ref in summary_result["rows"]:
        row = rows[ref]
        lines.append(
            f"{row['analyte']}: {row['operator']}{row['value']} {row['unit']}, {flags[row['flag']]}."
        )
    return "\n".join(lines)
