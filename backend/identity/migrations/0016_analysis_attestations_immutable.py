from django.db import migrations

TABLES = ("analysisdraft", "analysisreview", "analysisopinion", "analysispublication")


class Migration(migrations.Migration):
    dependencies = [("identity", "0015_analysisopinion_analysisjob_analysismodel_and_more")]
    operations = [
        migrations.RunSQL(
            f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON identity_{table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()",
            reverse_sql=f"DROP TRIGGER {table}_immutable ON identity_{table}",
        )
        for table in TABLES
    ]
