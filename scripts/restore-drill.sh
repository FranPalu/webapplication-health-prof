#!/usr/bin/env bash
# Exercise dump and restore on two disposable databases in the local Compose stack.
set -euo pipefail
cd "$(dirname "$0")/.."
compose=("${DOCKER_BIN:-docker}" compose --env-file .env.dev)
suffix="$(python3 -c 'import secrets; print(secrets.token_hex(8))')"
source_db="claria_drill_source_$suffix"
target_db="claria_drill_target_$suffix"

db() {
    "${compose[@]}" exec -T db sh -c 'command="$1"; shift; exec "$command" -U "$POSTGRES_USER" "$@"' sh "$@"
}

source_created=false
target_created=false
cleanup() {
    local status=0
    if "$target_created"; then db dropdb --if-exists "$target_db" || status=1; fi
    if "$source_created"; then db dropdb --if-exists "$source_db" || status=1; fi
    return "$status"
}
trap cleanup EXIT

db createdb "$source_db"
source_created=true
db createdb "$target_db"
target_created=true
manage() {
    local database="$1"
    shift
    "${compose[@]}" exec -T -e "POSTGRES_DB=$database" backend python manage.py "$@"
}

manage "$source_db" migrate --noinput >/dev/null
manage "$source_db" seed_demo
manage "$source_db" shell -v 0 -c '
from django.conf import settings
from identity.models import User
from identity.security import audit, cipher

assert settings.DEBUG
account = User.objects.create_user("restore@patients.example", email_verified=True)
account.mfa_secret = cipher().encrypt(b"synthetic-restore-marker").decode()
account.save(update_fields=["mfa_secret"])
audit(account, "restore.drill")
'
db pg_dump --format=custom "$source_db" |
    db pg_restore --exit-on-error --single-transaction --dbname="$target_db"
manage "$target_db" migrate --check
manage "$target_db" verify_audit_chain
manage "$target_db" shell -v 0 -c '
from identity.models import AuditEvent, Patient, User
from identity.security import cipher

assert Patient.objects.filter(legacy_source="synthetic-seed").count() == 3
account = User.objects.get(email="restore@patients.example")
assert cipher().decrypt(account.mfa_secret.encode()) == b"synthetic-restore-marker"
assert AuditEvent.objects.filter(actor=account, action="restore.drill").exists()
print("Restored 3 synthetic patients, audit event and encrypted marker")
'
