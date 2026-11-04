# Changelog

## 2026-11-04 — M3 documenti clinici e interoperabilità

- Portale documentale con cartelle, versioni, ricerca per titolo o testo PDF, condivisione e consenso v2.
- ClamAV, validazione strutturale, trasferimento durevole a S3, wrapping KMS, rotazione e retention amministrata.
- Letture FHIR R4 per sette risorse e creazione API dei referti strutturati.
- Import R2 idempotente con manifest e verifica degli hash.

## 2026-11-04 — Prima consegna M3

- API per documenti clinici con scansione obbligatoria, cifratura per tenant, versioni e archiviazione.
- Ricerca autorizzata per titolo e lettura FHIR R4 di Patient e DocumentReference.

## 2026-11-04 — Leggibilità e anagrafica

- Codice Fiscale nella griglia principale; verifica catastale facoltativa espandibile.
- Token di contrasto per finestre, campi, tabelle, notifiche e stati nei due temi; caratteri più leggibili.
- Controlli browser del contrasto del modulo paziente e del layout mobile.

## 2026-11-04 — Correzioni interazioni demo

- Corretto il focus dei moduli: digitazione continua nella conferma di eliminazione e nelle schede.
- Solo Light mode e Dark mode, con conversione della precedente preferenza Sistema.
- Test browser su modifica ed eliminazione paziente con rimozione dei dati collegati; chiarito il ripristino della demo al ricaricamento.

## 2026-11-04 — Clarìa

- Identità Clarìa e palette condivisa dal portale e dal gestionale dimostrativo.
- Verifica email con collegamento esplicito, recupero dopo ricaricamento e istruzioni per link scaduti.

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
