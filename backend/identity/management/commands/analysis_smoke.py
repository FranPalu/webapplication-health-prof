"""Run the local lab pipeline with reproducible synthetic fixtures."""

from io import BytesIO

from django.core.management.base import BaseCommand, CommandError
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from identity.analysis_pipeline import extract, pages_from, suggested_text, summary

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


def scanned_pdf():
    image = Image.new("RGB", (1100, 460), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    for index, line in enumerate(LINES):
        draw.text((40, 40 + index * 72), line, fill="black", font=font)
    output = BytesIO()
    image.save(output, "PDF", resolution=150)
    return output.getvalue()


class Command(BaseCommand):
    help = "Validate extraction, OCR and the pinned local LLM using synthetic reports."

    def handle(self, *args, **options):
        for generator in (native_pdf, scanned_pdf):
            pages = pages_from(generator(), "application/pdf")
            rows = extract(pages)
            actual = [tuple(row.get(field) for field in FIELDS) for row in rows]
            matches = sum(row in actual for row in EXPECTED)
            f1 = 2 * matches / (len(actual) + len(EXPECTED))
            self.stdout.write(
                f"{generator.__name__}: exact row F1={f1:.3f} ({matches}/{len(EXPECTED)})"
            )
            if f1 < 0.95:
                raise CommandError("Golden extraction threshold missed.")
        safety = extract([("Creatinina non leggibile\nEmoglobina 14 g/dL", "embedded")])
        if "value" in safety[0] or "low" in safety[1]:
            raise CommandError("Missing data was inferred.")
        selected = summary(rows)
        if not selected or not suggested_text({"summary": selected, "rows": rows}):
            raise CommandError("Pinned local model did not return a valid summary.")
        self.stdout.write("Local Qwen: valid summary with verified row references.")
