"""Bounded local extraction. Source text never reaches the summary model."""

import csv
import hashlib
import json
import os
import re
import subprocess
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from pypdf import PdfReader

PIPELINE = "lab-v2:source-v1:ucum-v1:prompt-v2"
PROMPT_VERSION = "row-selection-v2"
MIN_OCR_CONFIDENCE = 85
LOINC = {
    ("glucosio", "mg/dL"): "2345-7",
    ("glucose", "mg/dL"): "2345-7",
    ("glucosio", "mmol/L"): "14749-6",
    ("glucose", "mmol/L"): "14749-6",
    ("creatinina", "mg/dL"): "2160-0",
    ("creatinina", "µmol/L"): "14682-9",
    ("emoglobina", "g/dL"): "718-7",
    ("emoglobina", "g/L"): "718-7",
    ("colesterolo", "mg/dL"): "2093-3",
    ("colesterolo", "mmol/L"): "14647-2",
}
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


def extract(pages, *, notices=None):
    rows: list[dict] = []
    for page, item in enumerate(pages, 1):
        text, source = item[:2]
        lines = text.splitlines()
        if notices is not None and len(lines) > 1000:
            notices.add("page_line_limit")
        for number, line in enumerate(lines[:1000], 1):
            geometry = item[3][number - 1] if len(item) > 3 and number <= len(item[3]) else {}
            evidence = {
                "source_text": line[:2000],
                "bbox": geometry.get("bbox"),
                "coordinate_system": geometry.get("coordinate_system"),
                "confidence": geometry.get("confidence"),
            }
            if len(rows) >= 100:
                if notices is not None:
                    notices.add("evidence_limit")
                return rows
            clean = line.strip().casefold()
            analyte = next(
                (name for name in UNITS if re.match(re.escape(name) + r"\s", clean)), None
            )
            if not analyte:
                if any(char.isdigit() for char in clean) and len(rows) < 100:
                    rows.append(
                        {
                            "id": f"{page}:{number}",
                            "page": page,
                            "line": number,
                            "source": source,
                            **evidence,
                            "requires_confirmation": True,
                            "flag": "unrecognized",
                        }
                    )
                continue
            row = {
                "id": f"{page}:{number}",
                "page": page,
                "line": number,
                "source": source,
                **evidence,
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
            row["loinc"] = LOINC.get((analyte, row.get("unit", "")))
            row["ucum"] = (
                ("umol/L" if row.get("unit") == "µmol/L" else row.get("unit"))
                if row["loinc"]
                else None
            )
            row["terminology_status"] = "verify_specimen_and_method"
            confidence = row["confidence"]
            row["requires_confirmation"] = (
                row["flag"] not in ("below", "above", "within")
                or row["terminology_status"] == "verify_specimen_and_method"
                or not row["loinc"]
                or row["bbox"] is None
                or (source == "ocr" and (confidence is None or confidence < MIN_OCR_CONFIDENCE))
            )
            rows.append(row)
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


class PDFEvidenceParser(HTMLParser):
    """Read bounded Poppler-generated XHTML without resolving XML entities."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pages = []
        self.lines = []
        self.words = []
        self.boxes = []
        self.in_word = False
        self.word = ""
        self.word_box = None

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "page":
            self.lines = []
        elif tag == "line":
            self.words, self.boxes = [], []
        elif tag == "word":
            self.in_word = True
            self.word = ""
            self.word_box = [float(data[key]) for key in ("xmin", "ymin", "xmax", "ymax")]

    def handle_data(self, data):
        if self.in_word:
            self.word += data

    def handle_endtag(self, tag):
        if tag == "word":
            self.in_word = False
            self.words.append(self.word)
            self.boxes.append(self.word_box)
        elif tag == "line" and self.words:
            self.lines.append(
                {
                    "text": " ".join(self.words),
                    "bbox": [
                        min(box[0] for box in self.boxes),
                        min(box[1] for box in self.boxes),
                        max(box[2] for box in self.boxes),
                        max(box[3] for box in self.boxes),
                    ],
                    "coordinate_system": "pdf_points_top_left",
                    "confidence": None,
                }
            )
        elif tag == "page":
            self.pages.append(self.lines)


def pages_from(data, media_type):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        if media_type != "application/pdf":
            path = root / "image"
            path.write_bytes(data)
            text, confidence, evidence = ocr(path)
            return [(text, "ocr", confidence, evidence)]
        reader = PdfReader(BytesIO(data), strict=True)
        if not 0 < len(reader.pages) <= 12:
            raise ValueError("Page limit")
        path = root / "report.pdf"
        path.write_bytes(data)
        parser = PDFEvidenceParser()
        rendered = command(["pdftotext", "-bbox-layout", "-enc", "UTF-8", str(path), "-"])
        if len(rendered) > 4_000_000:
            raise ValueError("Source evidence limit")
        parser.feed(rendered.decode())
        if len(parser.pages) != len(reader.pages):
            raise ValueError("Source page mismatch")
        pages = []
        for index, evidence in enumerate(parser.pages, 1):
            text = "\n".join(line["text"] for line in evidence)
            if len(text) > 50000:
                raise ValueError("Page text limit")
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
                text, confidence, evidence = ocr(prefix.with_suffix(".png"))
                pages.append((text, "ocr", confidence, evidence))
            else:
                pages.append((text, "embedded", None, evidence))
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
    lines: dict[tuple[str, ...], list[dict]] = {}
    for word in csv.DictReader(output.decode().splitlines(), delimiter="\t"):
        if word.get("level") != "5" or not word.get("text"):
            continue
        key = tuple(word[field] for field in ("block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(word)
    evidence: list[dict] = []
    scores = []
    for words in lines.values():
        confidence = [float(word["conf"]) for word in words if 0 <= float(word["conf"]) <= 100]
        scores.extend(confidence)
        evidence.append(
            {
                "text": " ".join(word["text"] for word in words),
                "bbox": [
                    min(int(word["left"]) for word in words),
                    min(int(word["top"]) for word in words),
                    max(int(word["left"]) + int(word["width"]) for word in words),
                    max(int(word["top"]) + int(word["height"]) for word in words),
                ],
                "coordinate_system": "image_pixels_top_left",
                "confidence": min(confidence) if len(confidence) == len(words) else None,
            }
        )
    text = "\n".join(line["text"] for line in evidence)
    if len(text) > 50000:
        raise ValueError("Page text limit")
    return text, round(sum(scores) / len(scores), 2) if scores else None, evidence


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
    refs = summary_result.get("rows")
    if (
        not isinstance(refs, list)
        or not 0 < len(refs) <= 5
        or any(not isinstance(ref, str) for ref in refs)
        or len(set(refs)) != len(refs)
    ):
        return ""
    for ref in refs:
        row = rows.get(ref)
        if (
            not row
            or row.get("flag") not in flags
            or not all(key in row for key in ("operator", "value", "unit", "analyte"))
        ):
            return ""
        lines.append(
            f"{row['analyte']}: {row['operator']}{row['value']} {row['unit']}, {flags[row['flag']]}."
        )
    return "\n".join(lines)
