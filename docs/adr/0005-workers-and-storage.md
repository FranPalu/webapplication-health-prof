# ADR 0005 — Separazione worker, storage e ricerca

Data: 2026-11-03. Stato: accettato, implementazione progressiva M1–M9.

## Contesto

OCR, imaging, scansioni ed ETL non devono bloccare le API interattive. I worker
e i ricercatori non devono ereditare accesso indiscriminato al database clinico.

## Decisione

Celery con Redis e code separate per comunicazioni, documenti, AI e ricerca;
outbox transazionale, ID opachi nei messaggi, task idempotenti e retry limitati.
Gli esiti esterni incerti richiedono riconciliazione prima della ripetizione.
Worker AI containerizzati separatamente con limiti di risorse e accesso di rete
ristretto; autorizzazione rivalutata prima dell'uso e pubblicazione dei dati.

Storage S3 compatibile privato, quarantena antivirus, chiavi dati per oggetto
protette da chiavi tenant tramite KMS. Nessuna chiave operativa in Git. Il KMS
locale di sviluppo non costituisce una soluzione produttiva certificata.
Ricerca su database e credenziali separati, senza query dirette degli utenti
ricercatori sul database clinico. Audit con checkpoint immutabili esterni.

## Conseguenze

Compose riproduce il percorso locale; worker pesanti arrivano nelle milestone
specifiche. Produzione richiede servizi e backup in UE, gestione delle chiavi,
monitoraggio code, scarti, dead-letter e procedure di replay. Test obbligatori
su duplicati, timeout, revoca durante il job e ripristino completo di dati/chiavi.
Non si promette esecuzione exactly-once: gli effetti devono essere idempotenti.
