"""Generate local-only secrets once. Never print secret values."""
import base64
import os
import secrets
from pathlib import Path

path = Path(__file__).resolve().parent.parent / '.env.dev'
if not path.exists():
    values = {
        'CLINICAL_MASTER_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'CLINICAL_SEARCH_KEY': secrets.token_urlsafe(32),
        'CLINICAL_IDENTITY_KEY': secrets.token_urlsafe(32),
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(48),
        'MFA_ENCRYPTION_KEY': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(),
        'DJANGO_DEBUG': 'true', 'DJANGO_ALLOWED_HOSTS': 'localhost,127.0.0.1,backend,testserver',
        'PUBLIC_ORIGIN': 'http://localhost:8080',
        'POSTGRES_DB': 'health', 'POSTGRES_USER': 'health',
        'POSTGRES_PASSWORD': secrets.token_urlsafe(32), 'POSTGRES_HOST': 'db', 'POSTGRES_PORT': '5432',
        'REDIS_URL': 'redis://redis:6379/0', 'EMAIL_HOST': 'mail', 'EMAIL_PORT': '1025',
        'DEFAULT_FROM_EMAIL': 'no-reply@health.example',
        'S3_ACCESS_KEY': secrets.token_urlsafe(18), 'S3_SECRET_KEY': secrets.token_urlsafe(32),
        'S3_ENDPOINT': 'http://storage:8333', 'S3_BUCKET': 'health-local', 'S3_REGION': 'eu-west-1',
    }
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write('\n'.join(f'{k}={v}' for k, v in values.items()) + '\n')
    print('Created .env.dev (local generated secrets, ignored by Git).')
else:
    existing = path.read_text()
    additions = []
    for name in ('CLINICAL_MASTER_KEY', 'CLINICAL_SEARCH_KEY', 'CLINICAL_IDENTITY_KEY'):
        if not any(line.startswith(name + '=') for line in existing.splitlines()):
            additions.append(f'{name}={base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}')
    if additions:
        with path.open('a') as stream:
            stream.write('\n' + '\n'.join(additions) + '\n')
    print('Using existing .env.dev.')
