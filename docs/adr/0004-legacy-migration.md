# ADR 0004 — Import progressivo e cutover senza doppia scrittura

Data: 2026-11-03. Stato: accettato, implementazione M1/M3/M5/M6.

## Contesto

D1 contiene JSON e trigger SQLite; R2 contiene PDF. Non è stato verificato se
esistano dati operativi remoti. Non è quindi ammissibile azzerare il sistema o
trattare la demo come unica sorgente possibile.

## Decisione

Import offline versionato con manifest e dry-run, mappatura owner→organizzazione
approvata, chiave idempotente sorgente/owner/tipo/id e report di scarti. Nessun
merge automatico di pazienti o consenso inferito. Anagrafiche in M1, documenti
in M3, fatture in M5, agenda/comunicazioni in M6. Conservare snapshot fiscali e
provenienza; non applicare retroattivamente nuove regole ai documenti storici.

Legacy e nuovo backend in ambienti isolati; niente doppia scrittura o fallback
autorizzativo al legacy. Le funzioni non portate restano indisponibili nel nuovo
ambiente. Cutover operativo soltanto quando tutti i flussi necessari sono portati.

## Verifica e rollback

Prima del cutover: backup D1/R2 e prova di restore, sola lettura legacy, import
finale, conteggi per owner/tipo, riferimenti, hash dei file, totali contabili,
test di autorizzazione e accettazione. File mancanti o record incoerenti bloccano
la pubblicazione delle risorse interessate e risultano nel report.

Prima di scritture nel nuovo sistema il rollback può ripristinare il legacy.
Dopo nuove scritture serve riconciliazione esplicita e sospensione delle modifiche:
non esiste un rollback automatico sicuro fra modelli differenti. Importazione
provata due volte deve lasciare invariati conteggi e riferimenti.
