# Revisione delle interazioni demo — 4 novembre 2026

Il gestionale in /demo/agenda usa dati sintetici in memoria: ricaricare la pagina ripristina il campione iniziale. Non è un archivio clinico persistente. Invii email/WhatsApp e Sistema TS restano disabilitati nella demo.

## Correzioni
Il componente Modal dipendeva dall'identità della callback onClose: ogni modifica del form rieseguiva il ripristino del focus e selezionava il pulsante Chiudi. Separata la callback aggiornata dal ciclo di apertura/chiusura della finestra. La correzione riguarda tutti i moduli, inclusa la conferma testuale di eliminazione.

L'eliminazione conserva il blocco per fatture emesse; in quel caso occorre archiviare il percorso. Per le bozze vengono rimossi paziente, appuntamenti, documenti, bozze e messaggi collegati.

Il selettore offre solo Light mode e Dark mode. La vecchia preferenza Sistema viene convertita in Light mode. La scelta resta condivisa fra login e demo.

## Verifiche ripetibili
Eseguire Playwright con E2E_BASE_URL=http://localhost:8080 e MAILPIT_URL=http://localhost:8025 sulla stack locale. I test demo verificano digitazione senza perdita di focus, modifica anagrafica, eliminazione con record collegati, temi e navigazione fra ruoli. I test identità coprono registrazione, verifica email, login/logout e onboarding con MFA. Le funzioni delle milestone successive restano soggette ai limiti già documentati.
