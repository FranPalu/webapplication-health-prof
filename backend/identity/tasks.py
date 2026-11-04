from botocore.exceptions import BotoCoreError, ClientError
from celery import shared_task

from identity.clinical import DocumentUnavailable
from identity.clinical_storage import offload
from identity.models import ClinicalDocumentVersion


@shared_task(
    ignore_result=True,
    autoretry_for=(BotoCoreError, ClientError, DocumentUnavailable),
    retry_backoff=True,
    max_retries=5,
)
def offload_clinical_version(version_id):
    offload(version_id)


@shared_task(ignore_result=True)
def reconcile_clinical_storage():
    staged = ClinicalDocumentVersion.objects.filter(object_key="", purged_at__isnull=True).order_by(
        "created_at"
    )
    for version_id in staged.values_list("pk", flat=True)[:100]:
        offload_clinical_version.delay(str(version_id))
