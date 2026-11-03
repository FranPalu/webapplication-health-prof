from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("identity", "0001_initial")]
    operations = [
        migrations.RunSQL(
            """
        CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Audit events are append-only'; END; $$;
        CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE ON identity_auditevent
        FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
        """,
            "DROP TRIGGER audit_append_only ON identity_auditevent; DROP FUNCTION reject_audit_mutation();",
        )
    ]
