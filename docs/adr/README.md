# Architecture Decision Records

Decisioni del 2026-11-03: accettate per l'architettura target, non ancora implementate.
La scelta Django è stata confermata esplicitamente dal committente; le altre
decisioni traducono il piano approvato in vincoli di implementazione.

- [0001 — Backend Django e riuso frontend](0001-django-backend.md)
- [0002 — Tenancy e autorizzazioni](0002-tenancy-and-authorization.md)
- [0003 — Autenticazione autonoma](0003-authentication.md)
- [0004 — Migrazione progressiva senza doppia scrittura](0004-legacy-migration.md)
- [0005 — Worker, storage e ricerca separati](0005-workers-and-storage.md)

Modificare una decisione richiede un nuovo ADR che espliciti quale sostituisce,
con motivazione, conseguenze e migrazione. Non riscrivere lo storico per far
apparire già implementata una scelta futura.
