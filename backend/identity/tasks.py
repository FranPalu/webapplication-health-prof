from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task

from identity.clinical import DocumentUnavailable
from identity.clinical_storage import offload
from identity.models import ClinicalDocumentVersion


@shared_task(ignore_result=True)
def offload_clinical_version(version_id):
    from datetime import timedelta

    from django.db.models import F
    from django.utils import timezone

    try:
        offload(version_id)
    except (BotoCoreError, ClientError, DocumentUnavailable):
        staged = ClinicalDocumentVersion.objects.filter(
            pk=version_id, object_key="", purged_at__isnull=True
        )
        failures = staged.values_list("offload_failures", flat=True).first()
        if failures is not None:
            staged.update(
                offload_after=timezone.now() + timedelta(minutes=2 ** min(failures + 1, 8)),
                offload_failures=F("offload_failures") + 1,
            )


@shared_task(ignore_result=True)
def reconcile_clinical_storage():
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    with transaction.atomic():
        now = timezone.now()
        staged = (
            ClinicalDocumentVersion.objects.filter(
                object_key="", purged_at__isnull=True, offload_after__lte=now
            )
            .select_for_update(skip_locked=True)
            .order_by("offload_after", "pk")
        )
        ids = list(staged.values_list("pk", flat=True)[:100])
        ClinicalDocumentVersion.objects.filter(pk__in=ids).update(
            offload_after=now + timedelta(minutes=5)
        )
    for version_id in ids:
        offload_clinical_version.delay(str(version_id))


@shared_task(ignore_result=True)
def reconcile_analysis_jobs():
    from django.utils import timezone

    from identity.analysis import enabled
    from identity.models import AnalysisJob

    if not enabled():
        return
    AnalysisJob.objects.filter(state="running", lease_until__lt=timezone.now()).update(
        state="queued", lease_until=None
    )
    queued = AnalysisJob.objects.filter(state="queued").order_by("created_at")
    for job_id in queued.values_list("pk", flat=True)[:50]:
        run_clinical_analysis.delay(str(job_id))


@shared_task(ignore_result=True, soft_time_limit=170, time_limit=180)
def run_clinical_analysis(job_id):
    import hashlib
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from identity.analysis import encode, requester_allowed
    from identity.analysis_pipeline import (
        DISCLAIMER,
        OCR_WEIGHTS,
        PIPELINE,
        PROMPT_VERSION,
        QWEN_SHA256,
        extract,
        pages_from,
        summary,
    )
    from identity.analysis_registry import manifest
    from identity.clinical_storage import read_content
    from identity.models import AnalysisDraft, AnalysisJob, AnalysisModel
    from identity.security import audit

    with transaction.atomic():
        job = AnalysisJob.objects.select_for_update().filter(pk=job_id, state="queued").first()
        if job is None:
            return
        organization = job.version.document.patient.organization
        allowed = requester_allowed(job, lock=True)
        if not allowed or job.pipeline != PIPELINE or job.attempts >= 3:
            job.state = "cancelled" if not allowed else "failed"
            job.save(update_fields=["state"])
            audit(job.requested_by, "analysis." + job.state, job.pk, organization)
            return
        job.attempts += 1
        attempt = job.attempts
        job.lease_until = timezone.now() + timedelta(minutes=4)
        job.state = "running"
        job.save(update_fields=["state", "attempts", "lease_until"])

    result = None
    try:
        content = read_content(job.version)
        if hashlib.sha256(content).hexdigest() != job.input_hash:
            raise ValueError("Input mismatch")
        pages = pages_from(content, job.version.media_type)
        notices: set[str] = set()
        rows = extract(pages, notices=notices)
        ocr_used = any(page[1] == "ocr" for page in pages)
        confidence = [
            {"page": number, "value": page[2], "source": "tesseract_mean_word_confidence"}
            for number, page in enumerate(pages, 1)
            if len(page) > 2 and page[2] is not None
        ]
        selected = summary(rows) if not notices else None
        if selected and selected.get("checksum") != QWEN_SHA256:
            raise ValueError("Summary model checksum mismatch")
        result = {
            "label": DISCLAIMER,
            "pipeline": PIPELINE,
            "prompt_version": PROMPT_VERSION,
            "manifest_hash": manifest()[1],
            "source_document_sha256": job.input_hash,
            "rows": rows,
            "ocr": OCR_WEIGHTS if ocr_used else {},
            "summary": selected,
            "notices": sorted(notices),
            "confidence": {"value": None, "source": "not_calibrated", "ocr_pages": confidence},
        }
        sealed = encode(result, organization.pk)
    except Exception:
        # Avoid logging parser errors, commands or OCR output.
        result = None

    with transaction.atomic():
        job = AnalysisJob.objects.select_for_update().get(pk=job_id)
        if job.state != "running" or job.attempts != attempt:
            return
        if not requester_allowed(job, lock=True):
            job.state = "cancelled"
        elif result is None:
            job.state = "queued" if attempt < 3 else "failed"
        else:
            model = None
            if result["summary"]:
                model, _ = AnalysisModel.objects.get_or_create(
                    name="Qwen2.5-1.5B-Instruct-GGUF",
                    revision="dd26da4/Q4_K_M",
                    checksum=result["summary"]["checksum"],
                    defaults={
                        "license": "Apache-2.0",
                        "intended_use": "Select evidence rows",
                        "limitations": "Uncalibrated; no clinical interpretation",
                    },
                )
            for language, checksum in result["ocr"].items():
                AnalysisModel.objects.get_or_create(
                    name=f"Tesseract tessdata_fast {language}",
                    revision="4.1.0",
                    checksum=checksum,
                    defaults={
                        "license": "Apache-2.0",
                        "intended_use": "OCR report text",
                        "limitations": "Layout and scan quality affect extraction",
                    },
                )
            AnalysisDraft.objects.create(job=job, model=model, **sealed)
            job.extraction_rows = len(result["rows"])
            job.uncertain_rows = sum(row["requires_confirmation"] for row in result["rows"])
            job.state = "ready"
        job.lease_until = None
        job.save(update_fields=["state", "lease_until", "extraction_rows", "uncertain_rows"])
        audit(job.requested_by, "analysis." + job.state, job.pk, organization)


@shared_task(ignore_result=True)
def appointment_reminders():
    from datetime import timedelta

    from django.db import transaction
    from django.utils import timezone

    from identity import appointment_reminders as delivery
    from identity.models import AppointmentBooking
    from identity.views import notify_user_id

    with transaction.atomic():
        now = timezone.now()
        bookings = (
            AppointmentBooking.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(
                cancelled_at__isnull=True,
                reminded_at__isnull=True,
                payer__is_active=True,
                slot__starts_at__gt=now,
                slot__starts_at__lte=now + timedelta(hours=24),
            )
            .order_by("slot__starts_at", "pk")[:100]
        )
        for booking in bookings:
            booking.reminded_at = now
            booking.save(update_fields=["reminded_at"])
            notify_user_id(booking.payer_id, "appointment.reminder", booking.pk)
            adapter = delivery.sms_adapter
            if adapter is not None:
                from functools import partial

                transaction.on_commit(
                    partial(
                        adapter.send_if_opted_in,
                        account_id=str(booking.payer_id),
                        idempotency_key=f"{booking.pk}:{booking.slot_id}:{booking.slot.starts_at.isoformat()}",
                    ),
                    robust=True,
                )


@shared_task(ignore_result=True)
def refresh_research_archive():
    import os

    from identity.research_archive import refresh

    dsn = os.environ.get("RESEARCH_DATABASE_DSN")
    if dsn:
        refresh(dsn)


@shared_task
def escalate_lab_results():
    from django.utils import timezone

    from identity.clinical_safety import escalate_due

    return escalate_due(timezone.now())
