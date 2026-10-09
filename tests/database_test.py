"""Check actual migration constraints and atomic rollback for booking conflicts."""
import sqlite3
from pathlib import Path
root=Path(__file__).resolve().parent.parent
conn=sqlite3.connect(':memory:')
for migration in sorted((root/'drizzle').glob('*.sql')):
    conn.executescript(migration.read_text())
conn.execute('INSERT INTO appointment_slots VALUES(?,?,?)',('owner:2026-10-10:840','owner','original'))
conn.execute('INSERT INTO appointment_slots VALUES(?,?,?)',('owner:2026-10-10:841','owner','other'))
conn.commit()
try:
    with conn:
        conn.execute('DELETE FROM appointment_slots WHERE appointment_id=?',('original',))
        conn.execute('INSERT INTO appointment_slots VALUES(?,?,?)',('owner:2026-10-10:841','owner','original'))
    raise AssertionError('Conflict must not be accepted')
except sqlite3.IntegrityError:
    pass
assert conn.execute('SELECT count(*) FROM appointment_slots WHERE appointment_id=?',('original',)).fetchone()[0]==1
with conn:
    conn.execute('INSERT INTO appointment_slots VALUES(?,?,?)',('another-owner:2026-10-10:840','another-owner','separate'))
assert conn.execute('SELECT count(*) FROM appointment_slots').fetchone()[0]==3
print('Database checks passed: overlap rejected, edit rollback, owner isolation.')
