"""Synthetic source evidence, parser limits and deterministic summary tests."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from identity import analysis_pipeline as pipeline
from identity.management.commands.analysis_smoke import native_pdf


def test_native_pdf_keeps_verifiable_source_boxes():
    xhtml = b"""<html><body><page><flow><block><line>
    <word xMin="10" yMin="20" xMax="60" yMax="30">Glucosio</word>
    <word xMin="62" yMin="20" xMax="80" yMax="30">110</word>
    <word xMin="82" yMin="20" xMax="110" yMax="30">mg/dL</word>
    <word xMin="112" yMin="20" xMax="145" yMax="30">60-100</word>
    </line></block></flow></page></body></html>"""
    with patch.object(pipeline, "command", return_value=xhtml):
        pages = pipeline.pages_from(native_pdf(), "application/pdf")
    row = pipeline.extract(pages)[0]
    assert row["bbox"] == [10, 20, 145, 30]
    assert row["coordinate_system"] == "pdf_points_top_left"
    assert row["source_text"] == "Glucosio 110 mg/dL 60-100"
    assert row["confidence"] is None and row["requires_confirmation"]
    assert row["loinc"] == "2345-7" and row["ucum"] == "mg/dL"


def test_ocr_boxes_use_lowest_word_confidence_and_reject_tampered_weights(tmp_path, monkeypatch):
    weights = b"SYNTHETIC-WEIGHTS-NOT-A-MODEL"
    (tmp_path / "ita.traineddata").write_bytes(weights)
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path))
    monkeypatch.setattr(pipeline, "OCR_WEIGHTS", {"ita": hashlib.sha256(weights).hexdigest()})
    tsv = (
        "level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t10\t20\t40\t10\t97\tGlucosio\n"
        "5\t1\t1\t1\t52\t20\t20\t10\t50\t110\n"
        "5\t1\t1\t1\t74\t20\t40\t10\t96\tmg/dL\n"
        "5\t1\t1\t1\t116\t20\t40\t10\t96\t60-100\n"
    ).encode()
    with patch.object(pipeline, "command", return_value=tsv):
        pages = pipeline.pages_from(b"SYNTHETIC-IMAGE", "image/png")
    row = pipeline.extract(pages)[0]
    assert row["confidence"] == 50 and row["requires_confirmation"]
    assert row["bbox"] == [10, 20, 156, 30]
    assert row["coordinate_system"] == "image_pixels_top_left"
    (tmp_path / "ita.traineddata").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        pipeline.ocr(Path("synthetic.png"))


def test_pdf_limits_and_page_mismatch_fail_closed():
    from io import BytesIO

    from pypdf import PdfWriter

    pdf = PdfWriter()
    for _ in range(13):
        pdf.add_blank_page(600, 300)
    data = BytesIO()
    pdf.write(data)
    with pytest.raises(ValueError, match="Page limit"):
        pipeline.pages_from(data.getvalue(), "application/pdf")
    with (
        patch.object(pipeline, "command", return_value=b"<html></html>"),
        pytest.raises(ValueError, match="page mismatch"),
    ):
        pipeline.pages_from(native_pdf(), "application/pdf")


@pytest.mark.parametrize(
    ("value", "flag"),
    [("59", "below"), ("60", "within"), ("80", "within"), ("100", "within"), ("101", "above")],
)
@pytest.mark.parametrize("label", ["Glucosio", "Glucose"])
@pytest.mark.parametrize("space", [" ", "  ", "\t"])
def test_synthetic_boundary_and_layout_robustness(value, flag, label, space):
    line = space.join([label, value, "mg/dL", "60-100"])
    (row,) = pipeline.extract([(line, "embedded")])
    assert row["value"] == value and row["flag"] == flag
    text = pipeline.suggested_text({"rows": [row], "summary": {"rows": [row["id"]]}})
    assert f"{value} mg/dL" in text
