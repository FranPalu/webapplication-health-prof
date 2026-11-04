# Changelog

## 2026-11-04 — Portale e anteprime

- Nuova identità Health Collaboration, temi chiaro e scuro, anteprime per ruolo e indicazioni per la verifica email in Mailpit.

## 2026-11-04 — M2 (implementazione in verifica)

- Aggiunti grant di condivisione con destinatario individuale/organizzativo,
  scope, permessi, finalità, scadenza, revoca e controlli sui discendenti.
- Aggiunti consensi paziente versionati e append-only, messaggi sicuri, notifiche
  generiche, storico accessi e accesso break-glass limitato a 15 minuti.
- Esteso l'audit append-only con hash-chain sequenziale e comando di verifica;
  documentati i limiti e le decisioni M2.
- La revisione ha corretto la migrazione dei trigger append-only, limitato la
  visibilità delle richieste prima del consenso e impedito la riattivazione delle
  condivisioni derivate dopo una revoca del consenso a monte.
- Il break-glass richiede abilitazione organizzativa e ricontrolla i permessi
  a ogni lettura.

## 2026-11-04 — M1

- Backend Django con verifica email, TOTP, profili e accesso alle anagrafiche per relazione di cura.
- Setup Compose, seed sintetici, import legacy, OpenAPI e controlli PostgreSQL e browser in CI.
- Sostituito il tag MinIO indisponibile con SeaweedFS per lo storage S3 di sviluppo.

## 2026-11-03 — M0: audit e progettazione

- Aggiunti audit della baseline `ffccd98`, architettura Django/DRF con frontend
  React riutilizzato e roadmap M0–M9 con gate di accettazione.
- Registrate cinque decisioni architetturali, limitazioni e note normative iniziali.
- Documentati typecheck superato, lint con 19 errori/7 warning, 19 test Node
  passati con suite reminder bloccata dal runtime e controlli SQLite superati.
- Nessuna modifica applicativa, migrazione o integrazione attivata.
- M1 resta subordinata a «GO M1».
