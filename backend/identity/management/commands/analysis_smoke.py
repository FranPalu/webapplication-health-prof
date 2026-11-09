"""Run the local lab pipeline with reproducible synthetic fixtures."""

import hashlib
import json
from io import BytesIO
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from identity.analysis_pipeline import (
    PIPELINE,
    PROMPT_VERSION,
    extract,
    pages_from,
    suggested_text,
    summary,
)
from identity.analysis_registry import manifest

LINES = (
    "Glucosio 110 mg/dL 60-100",
    "Creatinina 0,95 mg/dL 0,50-1,20",
    "Emoglobina 14 g/dL 12-16",
    "Colesterolo >210 mg/dL 100-200",
    "Glucose <60 mg/dL 60-100",
)
EXPECTED = [
    ("glucosio", "110", "mg/dL", "60", "100", "above"),
    ("creatinina", "0.95", "mg/dL", "0.50", "1.20", "within"),
    ("emoglobina", "14", "g/dL", "12", "16", "within"),
    ("colesterolo", "210", "mg/dL", "100", "200", "above"),
    ("glucose", "60", "mg/dL", "60", "100", "below"),
]
FIELDS = ("analyte", "value", "unit", "low", "high", "flag")


def native_pdf():
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=300)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    stream = DecodedStreamObject()
    lines = " ".join(f"({line}) Tj T*" for line in LINES)
    stream.set_data(f"BT /F1 14 Tf 18 TL 20 250 Td {lines} ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def scanned_pdf(*, rotation=0, degraded=False):
    image = Image.new("RGB", (1100, 460), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    for index, line in enumerate(LINES):
        draw.text((40, 40 + index * 72), line, fill="black", font=font)
    if rotation:
        image = image.rotate(rotation, expand=False, fillcolor="white")
    if degraded:
        image = image.resize((550, 230)).filter(ImageFilter.GaussianBlur(0.6)).resize((1100, 460))
    output = BytesIO()
    image.save(output, "PDF", resolution=150)
    return output.getvalue()


class Command(BaseCommand):
    help = "Validate extraction, OCR and the pinned local LLM using synthetic reports."

    def add_arguments(self, parser):
        parser.add_argument("--report", help="Write non-identifying synthetic evaluation JSON")

    def handle(self, *args, **options):
        results = []
        for label, generator in (
            ("native_pdf", native_pdf),
            ("scanned_pdf", scanned_pdf),
            ("rotation_3_degrees", lambda: scanned_pdf(rotation=3)),
            ("blur_and_downsample", lambda: scanned_pdf(degraded=True)),
        ):
            data = generator()
            pages = pages_from(data, "application/pdf")
            rows = extract(pages)
            actual = [tuple(row.get(field) for field in FIELDS) for row in rows]
            matches = sum(row in actual for row in EXPECTED)
            f1 = 2 * matches / (len(actual) + len(EXPECTED))
            self.stdout.write(f"{label}: exact row F1={f1:.3f} ({matches}/{len(EXPECTED)})")
            if any(not row.get("bbox") or not row.get("source_text") for row in rows):
                raise CommandError("Source geometry missing.")
            results.append(
                {
                    "case": label,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "exact_row_f1": f1,
                    "matched_rows": matches,
                    "expected_rows": len(EXPECTED),
                    "extracted_rows": len(rows),
                    "requires_confirmation": sum(row["requires_confirmation"] for row in rows),
                }
            )
            if label in ("native_pdf", "scanned_pdf") and f1 < 0.95:
                raise CommandError("Golden extraction threshold missed.")
        safety = extract([("Creatinina non leggibile\nEmoglobina 14 g/dL", "embedded")])
        if "value" in safety[0] or "low" in safety[1]:
            raise CommandError("Missing data was inferred.")
        selected = summary(rows)
        if not selected or not suggested_text({"summary": selected, "rows": rows}):
            raise CommandError("Pinned local model did not return a valid summary.")
        self.stdout.write("Local Qwen: valid summary with verified row references.")
        if options["report"]:
            Path(options["report"]).write_text(
                json.dumps(
                    {
                        "scope": "Synthetic extraction engineering evaluation; NOT clinical validation",
                        "pipeline": PIPELINE,
                        "prompt_version": PROMPT_VERSION,
                        "manifest_hash": manifest()[1],
                        "fixtures_version": "synthetic-lab-v2",
                        "results": results,
                        "summary_checksum": selected["checksum"],
                        "clinical_metrics": {
                            key: None
                            for key in [
                                "sensitivity",
                                "specificity",
                                "PPV",
                                "NPV",
                                "AUC",
                                "calibration",
                                "confidence_intervals",
                            ]
                        },
                        "subgroups": "Unavailable: fixtures have no age or sex and are not representative of patients",
                        "limitations": "Five fixed rows per rendering. F1 is extraction agreement, not diagnostic accuracy. No clinical confidence estimates.",
                        "clinical_review": "DA VALIDARE da professionista abilitato",
                    },
                    indent=2,
                )
                + "\n"
            )
