from django.db import migrations

TABLES = ("analysisdraft", "analysisreview", "analysisopinion")
FUNCTION = """
CREATE FUNCTION guard_analysis_retention() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE linked_job uuid;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF TG_TABLE_NAME = 'identity_analysisopinion' THEN
            SELECT job_id INTO linked_job FROM identity_analysisreview WHERE id = OLD.review_id;
        ELSE
            linked_job := OLD.job_id;
        END IF;
        IF length(NEW.ciphertext) = 0 AND length(NEW.wrapped_key) = 0
           AND (to_jsonb(OLD) - 'ciphertext' - 'wrapped_key') =
               (to_jsonb(NEW) - 'ciphertext' - 'wrapped_key')
           AND EXISTS (
               SELECT 1 FROM identity_analysisjob j
               JOIN identity_clinicaldocumentversion v ON v.id = j.version_id
               WHERE j.id = linked_job AND v.purged_at IS NOT NULL
           ) THEN
            RETURN NEW;
        END IF;
    END IF;
    RAISE EXCEPTION 'Analysis records are immutable except for payload erasure after source purge';
END;
$$;
"""


def erase_existing(apps, schema_editor):
    for name, path in (
        ("AnalysisDraft", "job"),
        ("AnalysisReview", "job"),
        ("AnalysisOpinion", "review__job"),
    ):
        apps.get_model("identity", name).objects.filter(
            **{f"{path}__version__purged_at__isnull": False}
        ).update(ciphertext=b"", wrapped_key=b"")


class Migration(migrations.Migration):
    dependencies = [("identity", "0017_clinicaldocumentversion_offload_after_and_more")]
    operations = [
        migrations.RunSQL(FUNCTION, "DROP FUNCTION guard_analysis_retention()"),
        *[
            migrations.RunSQL(
                f"DROP TRIGGER {table}_immutable ON identity_{table}; "
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON identity_{table} "
                "FOR EACH ROW EXECUTE FUNCTION guard_analysis_retention();",
                f"DROP TRIGGER {table}_immutable ON identity_{table}; "
                f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON identity_{table} "
                "FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();",
            )
            for table in TABLES
        ],
        migrations.RunPython(erase_existing, migrations.RunPython.noop),
    ]
