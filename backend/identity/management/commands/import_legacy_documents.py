import hashlib
import json
import os
import re
import uuid
from pathlib import Path

import boto3
from botocore.config import Config
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from identity.clinical import MAX_BYTES, clinical_patients, media_type, scan, seal, search_tokens
from identity.clinical_formats import validated_text
from identity.models import ClinicalDocument, ClinicalDocumentVersion, User
from identity.security import audit
from identity.services import verified_professional


class Command(BaseCommand):
    help = "Reconcile a reviewed JSONL manifest with private R2 objects and imported patients."

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        names = ("LEGACY_R2_ENDPOINT", "LEGACY_R2_BUCKET", "LEGACY_R2_KEY", "LEGACY_R2_SECRET")
        if not all(os.environ.get(name) for name in names):
            raise CommandError("Set the four LEGACY_R2 variables before reconciliation.")
        bucket = os.environ["LEGACY_R2_BUCKET"]
        client = boto3.client(
            "s3",
            endpoint_url=os.environ["LEGACY_R2_ENDPOINT"],
            region_name="auto",
            aws_access_key_id=os.environ["LEGACY_R2_KEY"],
            aws_secret_access_key=os.environ["LEGACY_R2_SECRET"],
            config=Config(connect_timeout=3, read_timeout=10),
        )
        counts = {"verified": 0, "existing": 0, "imported": 0}
        with options["manifest"].open(encoding="utf-8") as manifest:
            for number, line in enumerate(manifest, 1):
                try:
                    result = self.reconcile(client, bucket, json.loads(line), options["apply"])
                except Exception:
                    raise CommandError(
                        f"Stopped on manifest line {number}. Check mapping, hash and scanner."
                    ) from None
                counts[result] += 1
        self.stdout.write(json.dumps(counts))

    def reconcile(self, client, bucket, row, apply):
        key, owner, expected = row["key"], row["owner"], row["sha256"]
        if not re.fullmatch(r"[0-9a-f]{64}", expected) or not key.startswith(owner + "/"):
            raise ValueError
        author = User.objects.get(pk=row["author"], is_active=True)
        if not verified_professional(author):
            raise ValueError
        patient = clinical_patients(author).get(
            legacy_source=row["source"],
            legacy_owner=owner,
            legacy_id=row["patient_legacy_id"],
            organization_id=row["organization"],
        )
        document_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"claria-r2:{client.meta.endpoint_url}/{bucket}/{key}"
        )
        response = client.get_object(Bucket=bucket, Key=key)
        with response["Body"] as body:
            content = body.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES or hashlib.sha256(content).hexdigest() != expected:
            raise ValueError
        detected = media_type(content)
        scan(content)
        extracted = validated_text(content, detected)
        title = row["title"].strip()
        if not 0 < len(title) <= 160:
            raise ValueError
        kind = row.get("kind", ClinicalDocument.Kind.OTHER)
        if kind not in ClinicalDocument.Kind.values:
            raise ValueError
        if not apply:
            existing = ClinicalDocument.objects.filter(pk=document_id).first()
            if existing:
                self.verify_existing(existing, patient, expected)
            return "verified"
        sealed = seal(content, patient.organization_id)
        with transaction.atomic():
            document, created = ClinicalDocument.objects.get_or_create(
                pk=document_id, defaults={"patient": patient, "author": author, "kind": kind}
            )
            if not created:
                self.verify_existing(document, patient, expected)
                return "existing"
            version = ClinicalDocumentVersion.objects.create(
                document=document,
                number=1,
                title=title,
                media_type=detected,
                size=len(content),
                search_tokens=search_tokens(extracted, patient.organization_id),
                **sealed,
            )
            audit(author, "clinical.imported", version.pk, patient.organization)
        return "imported"

    @staticmethod
    def verify_existing(document, patient, expected):
        if (
            document.patient_id != patient.pk
            or not document.versions.filter(number=1, sha256=expected).exists()
        ):
            raise ValueError
