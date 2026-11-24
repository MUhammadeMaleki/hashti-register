#!/usr/bin/env bash
set -euo pipefail
umask 077
[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
[[ -L /srv/hashti/current && -f /etc/hashti/hashti.env ]] || { echo 'Install the release first.' >&2; exit 1; }
[[ ! -e /root/hashti-admin-credentials ]] || { echo 'Credentials file already exists.' >&2; exit 1; }
set -a
. /etc/hashti/hashti.env
set +a
cd /srv/hashti/current/backend
.venv/bin/python - <<'PY'
import os
import secrets
from sqlalchemy import select
from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.models import User
from app.seed import bootstrap_admin

settings = Settings()
engine = build_engine(settings.database_url.get_secret_value())
try:
    with build_session_factory(engine)() as session:
        if session.scalar(select(User.id).where(User.username == 'admin')) is not None:
            raise SystemExit('Admin account already exists; no password was changed.')
        session.rollback()
        password = secrets.token_urlsafe(30)
        fd = os.open('/root/hashti-admin-credentials', os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as output:
                output.write(f'Username: admin\nPassword: {password}\n')
            bootstrap_admin(session, username='admin', full_name='مدیر هشتی', password=password)
        except BaseException:
            os.unlink('/root/hashti-admin-credentials')
            raise
finally:
    engine.dispose()
print('Admin created. Retrieve /root/hashti-admin-credentials over your own SSH session.')
PY
