import hashlib

from django.db import migrations


def publish(apps, schema_editor):
    model = apps.get_model("identity", "ConsentTextVersion")
    texts = {
        "it": (
            "Autorizzo il destinatario indicato ad accedere alla risorsa selezionata per la "
            "finalità e con i permessi riportati nella richiesta. Una condivisione di documento "
            "include le sue versioni presenti e future. Una cartella include le sottocartelle. "
            "L'intera cartella clinica include anche i referti strutturati. Le note psicologiche "
            "riservate sono escluse. Posso revocare il consenso in qualsiasi momento."
        ),
        "en": (
            "I authorize the named recipient to access the selected resource for the stated "
            "purpose and permissions. Document sharing includes existing and future versions. "
            "Folder sharing includes subfolders. Chart sharing also includes structured reports. "
            "Restricted psychology notes are excluded. I can withdraw consent at any time."
        ),
    }
    for locale, text in texts.items():
        model.objects.get_or_create(
            purpose="care_sharing",
            version=2,
            locale=locale,
            defaults={"text": text, "content_hash": hashlib.sha256(text.encode()).hexdigest()},
        )


class Migration(migrations.Migration):
    dependencies = [("identity", "0013_alter_share_scope_clinicalfolder_and_more")]
    operations = [migrations.RunPython(publish, migrations.RunPython.noop)]
