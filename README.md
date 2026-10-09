# Clarissa Bandini · Studio

Web application in italiano per l’organizzazione di uno studio di nutrizione: agenda, schede pazienti, documenti PDF, bozze di fattura e comunicazioni. Interfaccia responsive, palette salvia e prugna.

## Stato del progetto

Il sorgente è pubblicato nella repository GitHub pubblica [FranPalu/webapplication-health-prof](https://github.com/FranPalu/webapplication-health-prof). È una prima versione funzionale da revisionare; non è ancora configurata per l’uso clinico reale.

### Funzioni incluse

- Agenda per giorno e mese, incontri in studio o online, durate variabili e fuso Europe/Rome.
- Controllo sovrapposizioni lato client e server; prenotazione atomica degli slot nel database.
- Schede paziente con dati anagrafici, fiscali, contatti, preferenze di comunicazione e percorso.
- Controlli sul codice fiscale: formato, checksum, omocodia, data, sesso, nome e cognome; nessuna interrogazione dell’Anagrafe Tributaria.
- Upload e download protetti di PDF, archivio documenti, generazione di PDF dal testo redatto dalla professionista.
- Bozze fattura, numerazione, dati di pagamento e opposizione. L’emissione fiscale è disattivata finché la configurazione non è verificata.
- Adapter per reminder email e WhatsApp Business e motore predisposto per l’esecuzione pianificata. I servizi richiedono credenziali e collaudo.
- Backoffice con identità gestita dalla piattaforma Sites, dati separati per account e registro delle modifiche.
- Anteprima interna dell’esperienza paziente.

Il riferimento alla nutrizione e ai disturbi alimentari non attribuisce a Clarissa il titolo professionale di psicologa sulla sola base della laurea in Psicologia.

### Da attivare prima dell’uso reale

1. Pubblicare l’app su un ambiente con database D1, archivio R2 e identità configurata. La precedente creazione Sites non è riuscita e non è ancora attiva.
2. Completare il portale paziente con accessi individuali, autorizzazioni per scheda, prenotazione e documenti.
3. Verificare qualifica, partita IVA, regime, diciture e bollo con la professionista e il consulente fiscale.
4. Collegare e collaudare email e WhatsApp Business con mittente e template approvati. L’accettazione del messaggio da parte del provider non prova la consegna.
5. Configurare il job ricorrente per i reminder e completare i webhook di esito. Gli invii falliti o incerti richiedono attualmente verifica manuale.
6. Integrare e collaudare il Sistema Tessera Sanitaria per la corretta categoria professionale, abilitazione, credenziali e specifiche aggiornate. Nessuna trasmissione TS è attiva.
7. Completare revisione privacy, basi giuridiche, informative, accordi fornitori, conservazione e procedure di backup prima di inserire dati reali.

## Avvio e controlli

Richiede Node >=22.13 e pnpm.

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
python3 tests/database_test.py
pnpm build
pnpm dev
```

Per generare una demo autonoma senza backend:

```bash
node scripts/create-preview.mjs /percorso/assoluto/Clarissa_Bandini_Anteprima.html
```

La demo contiene solo dati fittizi, conserva le modifiche in memoria e non invia comunicazioni.

## Dati e integrazioni

Cloudflare Workers, D1 per i dati strutturati e R2 per i PDF. Le migrazioni sono in `drizzle/`; `.openai/hosting.json` dichiara i binding DB e BUCKET. L’emissione fiscale è disattivata per impostazione predefinita.

I segreti sono server-side e non vanno inseriti nel repository:

- `RESEND_API_KEY`, `MAIL_FROM`
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_TEMPLATE`, `META_GRAPH_VERSION`
- `REMINDER_JOB_SECRET`
- `FISCAL_ISSUANCE_ENABLED`, da abilitare solo dopo configurazione e collaudo fiscale

Il motore automatico espone `POST /api/reminders/run`, protetto da `REMINDER_JOB_SECRET`; serve un job esterno ricorrente. La rotta e i collegamenti esterni non sono collaudati in produzione.

## Repository e CI

La repository è pubblica, sulla branch `main`. La GitHub Action `Studio checks` esegue typecheck e test a ogni push e pull request. Nessun dato reale di pazienti o segreto operativo è incluso nel progetto.

## Riferimenti tecnici

- Sistema TS: https://sistemats1.sanita.finanze.it/portale/spese-sanitarie
- WhatsApp Cloud API: https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api
- Esempi ufficiali Meta: https://github.com/fbsamples/whatsapp-api-examples
- Resend API: https://resend.com/docs/api-reference/emails/send-email
