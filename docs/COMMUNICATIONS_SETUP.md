# Email, WhatsApp e reminder automatici

Il codice è predisposto; le credenziali e il collaudo dei provider devono essere completati nello studio. La presenza di una chiave non dimostra che il provider sia operativo. Nessun invio viene eseguito in modalità demo.

## 1. Variabili del server

In locale copia `.dev.vars.example` in `.dev.vars` nella radice del progetto e riavvia `pnpm dev`. Il file è escluso da Git. In produzione configura gli stessi valori nel secret manager del runtime Cloudflare/hosting. Non inserire credenziali nei componenti React, nelle variabili pubbliche, nei commit o nelle issue.

- Email: `RESEND_API_KEY`, `MAIL_FROM` (es. `Studio Bandini <studio@dominio-verificato.it>`).
- WhatsApp: `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_TEMPLATE`, `META_GRAPH_VERSION` (versione supportata dalla propria app Meta), `WHATSAPP_LANGUAGE=it`.
- Ricevute: `RESEND_WEBHOOK_SECRET`, `META_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`.
- Job: `REMINDER_JOB_SECRET` casuale di almeno 32 byte; `REMINDER_AUTOMATION_ENABLED=false` fino al collaudo.

Genera un segreto del job con `openssl rand -hex 32` e salvalo nel secret manager e nei GitHub Actions secrets, senza committarlo.

## 2. Email con Resend

1. Configura il dominio del mittente in Resend e verifica i record DNS richiesti (SPF/DKIM).
2. Crea una API key con permessi di invio; configura chiave e mittente nel server.
3. Configura il webhook HTTPS `https://DOMINIO-STUDIO/api/webhooks/email` per `email.sent`, `email.delivered`, `email.bounced`, `email.failed`, `email.complained` e copia il signing secret in `RESEND_WEBHOOK_SECRET`.
4. Il webhook verifica firma Svix sul corpo originale e timestamp entro cinque minuti. Eventi ripetuti o fuori ordine non fanno regredire lo stato.
5. Dopo aver collegato lo studio, usa una scheda di collaudo con un indirizzo controllato dalla professionista e la preferenza email registrata. Prepara un reminder e invialo esplicitamente. Verifica consegna nel provider e nel registro dell’app.

Fatture e PDF (massimo 5 MB per email) usano lo stesso template del download. Oggetto e testo dell’email non riportano diagnosi. I documenti sono allegati, non link pubblici.

## 3. WhatsApp Business Cloud API

1. Configura l’app Meta, il WhatsApp Business Account e il numero mittente.
2. Crea un token server con i permessi richiesti da WhatsApp, il Phone Number ID e scegli la versione Graph API supportata dalla tua app.
3. Fai approvare un template di categoria Utility nella lingua configurata, con **due parametri nel corpo, in quest’ordine: data e ora**. Esempio da sottoporre a Meta:

   `Lo studio di Clarissa Bandini ti ricorda l’appuntamento del {{1}} alle {{2}}. Per modifiche contatta lo studio. A presto!`

   Il reminder WhatsApp usa questo template, anche per le visite online; il testo generico non include il luogo. Niente diagnosi o contenuto del piano alimentare.
4. Configura callback `https://DOMINIO-STUDIO/api/webhooks/whatsapp`, verify token uguale a `WHATSAPP_VERIFY_TOKEN` e sottoscrizione al campo `messages`. Il server verifica `X-Hub-Signature-256` con `META_APP_SECRET`.
5. Registra il cellulare in formato internazionale (es. `+39…`) e la preferenza WhatsApp del paziente. Collauda prima con un numero controllato dallo studio e autorizzato in Meta.

La configurazione attuale invia **reminder WhatsApp**; gli allegati clinici e le fatture sono inviati tramite email. I messaggi WhatsApp in ingresso non vengono archiviati come chat: il webhook gestisce le ricevute di invio/consegna/lettura.

## 4. Scheduler GitHub Actions

Il workflow `.github/workflows/reminders.yml` è predisposto ogni 15 minuti ed è inizialmente inattivo.

Nelle impostazioni GitHub → Secrets and variables → Actions:

- Repository variable `STUDIO_URL`: URL HTTPS raggiungibile dell’app, senza slash finale.
- Repository secret `REMINDER_JOB_SECRET`: stesso valore del server.
- Repository variable `REMINDERS_ENABLED`: `true` **solo dopo il collaudo**.
- Server `REMINDER_AUTOMATION_ENABLED`: `true`.

Esegui prima il workflow manualmente da Actions → Reminder appuntamenti → Run workflow. L’endpoint richiede il bearer secret e può operare senza sessione utente. Deve essere raggiungibile dal job: un hosting protetto da un login esterno può bloccarlo prima che la richiesta arrivi al codice; in quel caso usare uno scheduler interno autorizzato che chiami la stessa funzione. Non rendere pubblico l’intero studio per far passare il job.

GitHub può ritardare i job pianificati e disabilitarli per inattività del repository. In produzione con orari rigorosi usare un servizio di scheduling con monitoraggio. La schermata Impostazioni indica l’ultima esecuzione e considera lo scheduler operativo solo se il job è abilitato e il heartbeat è più recente di 45 minuti.

Il job seleziona gli incontri nella finestra di anticipo impostata e non ancora iniziati (Europe/Rome). Salta pazienti archiviati, visite completate/annullate e contatti senza preferenza. Preferisce WhatsApp se configurato e autorizzato, altrimenti email. La claim atomica impedisce doppioni su esecuzioni concorrenti; un errore o timeout non provoca un reinvio automatico, perché il provider potrebbe aver già ricevuto la richiesta. Controllare il registro/provider prima di qualsiasi intervento manuale. Resend riceve anche una chiave di idempotenza. La modifica di data/ora genera un nuovo promemoria.

## 5. Database e aggiornamenti

Dopo aver aggiornato il codice, eseguire `pnpm build` e applicare **solo le migrazioni pendenti**. Per un database locale già inizializzato con `0000` e `0001`:

```bash
node --import ./scripts/sites-env.mjs ./node_modules/wrangler/bin/wrangler.js d1 execute DB --local --config dist/server/wrangler.json --persist-to .wrangler/state --file drizzle/0002_patient_lifecycle.sql
```

Per un database vuoto applicare prima le migrazioni `0000_superb_roland_deschain.sql` e `0001_warm_katie_power.sql`. Per produzione applicare la stessa migrazione al binding/database reale tramite gli strumenti dell’hosting; il comando sopra modifica solo il database locale.

La migrazione aggiunge protezioni sui riferimenti al paziente e una coda per eliminare file dall’archivio. Quando un paziente viene eliminato senza fatture emesse, la transazione rimuove scheda, appuntamenti/slot, documenti, bozze e messaggi. Le fatture emesse e gli invii in corso bloccano la cancellazione. I file vengono eliminati subito quando l’archivio è disponibile; gli errori restano in coda e vengono ritentati dal job. Il registro di audit conserva ID e operazione, senza contenuti clinici. L’archiviazione mantiene invece lo storico e sospende i reminder; gli appuntamenti esistenti restano visibili e occupano lo slot finché non vengono annullati.

## 6. Fatture e modelli

- Nuove fatture: compenso + contributo integrativo ENPAB 4%, arrotondato ai centesimi; bollo calcolato sul totale esente comprensivo di contributo, secondo la configurazione fiscale attuale dell’app.
- Le vecchie fatture senza campo ENPAB mantengono gli importi salvati: non vengono ricalcolate retroattivamente.
- Completa iscrizione all’Ordine, dati professionali e dicitura fiscale nelle Impostazioni. Questi valori sono fotografati nel documento alla creazione.
- Il profilo fiscale implementato resta quello delle prestazioni sanitarie esenti: la configurazione non sostituisce un motore IVA per tutte le attività professionali. L’emissione rimane protetta da `FISCAL_ISSUANCE_ENABLED`, da abilitare dopo verifica del regime applicabile e collaudo.
- Piano alimentare: scegli un modello quotidiano, settimanale o personalizzato e premi **Inserisci struttura**. I contenuti sono redatti dalla professionista. **Anteprima PDF** permette di verificarli prima dell’archiviazione.
- Sistema Tessera Sanitaria e accesso autonomo dei pazienti restano da integrare: nessun falso esito di trasmissione.

Riferimenti: [ENPAB, contributo integrativo](https://enpab.it/regolamento-di-disciplina-delle-funzioni-di-previdenza/), [Resend](https://resend.com/docs), [verifica Svix](https://www.svix.com/guides/receiving/receive-webhooks-with-svix-cli/), [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api/).
