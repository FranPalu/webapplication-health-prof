from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("identity", "0029_researchterminology")]
    operations = [
        migrations.RunSQL(
            "CREATE TRIGGER research_released_snapshot_immutable BEFORE UPDATE OR DELETE "
            "ON identity_researchreleasedsnapshot FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()",
            "DROP TRIGGER research_released_snapshot_immutable ON identity_researchreleasedsnapshot",
        )
    ]
