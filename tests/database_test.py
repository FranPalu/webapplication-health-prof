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

# Clinical deletion cascades by owner and queues file cleanup; issued invoices protect history.
import json
def record(id, owner, kind, **data):
    conn.execute('INSERT INTO studio_records VALUES(?,?,?,?,?)',(id,owner,kind,json.dumps(data),'2026-10-09'))
record('patient-a','owner','patients',firstName='A')
record('patient-b','other','patients',firstName='B')
record('visit-a','owner','appointments',patientId='patient-a')
record('doc-a','owner','documents',patientId='patient-a',key='owner/file-a')
record('invoice-a','owner','invoices',patientId='patient-a',status='Emessa')
record('doc-b','other','documents',patientId='patient-b',key='other/file-b')
conn.execute('INSERT INTO appointment_slots VALUES(?,?,?)',('owner:slot','owner','visit-a'))
conn.commit()
try:
    with conn:
        conn.execute("DELETE FROM studio_records WHERE id='patient-a' AND owner='owner'")
    raise AssertionError('Issued invoice must block deletion')
except sqlite3.IntegrityError:
    pass
assert conn.execute('SELECT count(*) FROM file_deletions').fetchone()[0]==0
conn.execute("UPDATE studio_records SET payload=json_set(payload,'$.status','Bozza') WHERE id='invoice-a'")
conn.commit()
with conn:
    conn.execute("DELETE FROM studio_records WHERE id='patient-a' AND owner='owner'")
assert conn.execute("SELECT count(*) FROM studio_records WHERE owner='owner'").fetchone()[0]==0
assert conn.execute("SELECT count(*) FROM studio_records WHERE owner='other'").fetchone()[0]==2
assert conn.execute("SELECT count(*) FROM appointment_slots WHERE appointment_id='visit-a'").fetchone()[0]==0
assert conn.execute('SELECT key FROM file_deletions').fetchall()==[('owner/file-a',)]
try:
    with conn:
        record('orphan','owner','appointments',patientId='patient-a')
    raise AssertionError('Concurrent insert after deletion must fail')
except sqlite3.IntegrityError:
    pass
try:
    with conn:
        record('wrong-owner','owner','documents',patientId='patient-b',key='x')
    raise AssertionError('Cross-owner reference must fail')
except sqlite3.IntegrityError:
    pass
print('Patient checks passed: fiscal guard, cascade, owner isolation, file cleanup, concurrent insert guard.')
