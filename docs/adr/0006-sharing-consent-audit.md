# ADR 0006 — Consensi espliciti e grant di condivisione

- **Stato:** accettato per M2
- **Data:** 2026-11-04
- **Contesto:** M1 limita l'accesso clinico con relazioni di cura, ma non offre
  concessioni esplicite e revocabili fra attori né una prova del consenso.
- **Decisione:** introdurre grant con destinatario utente/organizzazione, scope,
  permessi, finalità, scadenza, grant padre e revoca; i grant restano inattivi
  finché il paziente collegato accetta una versione immutabile del testo.
  Ogni richiesta di dati condivisi verifica consenso, scadenza, revoca e catena
  dei grant. Le revoche sono eventi separati, mai update dello storico.
- **Audit:** estendere il log append-only a una catena SHA-256 con contatore
  monotono e lock PostgreSQL globale. La sequenza rende verificabili gli eventi
  e i trigger bloccano modifiche ordinarie; il checkpoint indipendente resta
  necessario in una fase successiva.
- **Break-glass:** accesso professionale autenticato con MFA, membership nella
  struttura del paziente, motivo obbligatorio, durata di 15 minuti e audit.
  In assenza di workflow di revisione, non consente accesso tra strutture.
- **Conseguenze:** M2 condivide solo anagrafiche paziente, non documenti o
  cartelle. I testi iniziali sono seed dimostrativi da sottoporre a revisione;
  la registrazione del consenso non determina da sola la base giuridica GDPR.
- **Alternative considerate:** attivazione automatica del grant alla creazione
  (respinta perché non prova il consenso); permessi derivati dalla membership
  (respinta perché la membership non equivale a relazione di cura); audit solo
  append-only senza hash (respinto perché non rende rilevabile una riscrittura
  coordinata del log a livello applicativo).
