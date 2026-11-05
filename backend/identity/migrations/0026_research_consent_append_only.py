from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("identity", "0025_researchconsentevent")]
    operations = [
        migrations.RunSQL(
            "CREATE TRIGGER research_consent_append_only BEFORE UPDATE OR DELETE "
            "ON identity_researchconsentevent FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()",
            "DROP TRIGGER research_consent_append_only ON identity_researchconsentevent",
        )
    ]
