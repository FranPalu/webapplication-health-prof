"""Bounded structural validation and text extraction after malware screening."""

import re
from io import BytesIO

import pydicom
from PIL import Image
from pypdf import PdfReader
from rest_framework.exceptions import ValidationError


def validated_text(content, media_type):
    try:
        if media_type == "application/pdf":
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or not 0 < len(reader.pages) <= 250:
                raise ValueError
            fragments = []
            remaining = 100_000
            for page in reader.pages:
                text = page.extract_text()[:remaining]
                fragments.append(text)
                remaining -= len(text)
                if remaining <= 0:
                    break
            return " ".join(fragments)
        if media_type in ("image/png", "image/jpeg"):
            with Image.open(BytesIO(content), formats=["PNG", "JPEG"]) as image:
                expected = "PNG" if media_type == "image/png" else "JPEG"
                if image.format != expected or image.width * image.height > 24_000_000:
                    raise ValueError
                image.verify()
            with Image.open(BytesIO(content), formats=[expected]) as image:
                image.load()
        else:
            dataset = pydicom.dcmread(BytesIO(content), stop_before_pixels=True)
            pydicom.dataset.validate_file_meta(dataset.file_meta, enforce_standard=True)
            if (
                not dataset.get("SOPInstanceUID")
                or dataset.SOPInstanceUID != dataset.file_meta.MediaStorageSOPInstanceUID
                or dataset.get("SOPClassUID") != dataset.file_meta.MediaStorageSOPClassUID
            ):
                raise ValueError
    except Exception as exc:
        raise ValidationError("Invalid or unsupported file structure.") from exc
    return ""


def terms(text):
    return set(re.findall(r"[^\W_]{2,64}", text.casefold()))
