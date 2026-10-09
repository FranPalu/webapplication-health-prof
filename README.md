# Clarissa Bandini · Studio

Web application per l’organizzazione di uno studio di nutrizione: agenda, pazienti, documenti PDF, bozze di fattura e comunicazioni. Interfaccia in italiano, responsive, palette salvia e prugna. Il progetto include un’anteprima dimostrativa autosufficiente.

## Stato della consegna

Questa è una prima versione funzionale da revisionare, **non un sistema clinico completo già attivato**. La pubblicazione Sites è stata bloccata da un errore interno del servizio, prima della creazione del progetto. Nessuna repository GitHub è stata creata: il collegamento disponibile non espone la creazione di repository. Il sorgente è completo nel pacchetto e il commit locale conserva lo stato della consegna.

### Implementato

- Agenda per giorno e mese, creazione/modifica/cancellazione/completamento incontri, 20/30/45/60 minuti, studio/online, fuso Europe/Rome.
- Controllo sovrapposizioni nel client e sul server; prenotazione atomica di ogni minuto tramite chiavi univoche D1.
- Schede paziente, ricerca e filtro percorso; raccolta semplificata dati anagrafici, fiscali, contatti e preferenze.
- CF: formato, checksum originale, omocodia, data di nascita, sesso, nome/cognome, codice catastale inserito. Nessuna interrogazione dell’Anagrafe Tributaria; la corrispondenza con il luogo dipende dal codice inserito.
- Documenti: upload PDF fino a 10 MB con controllo firma, archivio R2 privato, download autorizzato; PDF da testo redatto dalla professionista.
- Bozze fatture e PDF; numerazione server atomica per anno; raccolta pagamento e opposizione. Le fatture emesse sono un flusso da collaudare fiscalmente: **regime, diciture, bollo, contributi e qualifiche non sono ancora configurati per lo studio reale**.
- Email reminder e allegati PDF tramite adapter Resend; WhatsApp reminder tramite template Meta. Nessun invio senza credenziali e preferenza del paziente; la demo blocca gli invii.
- Motore di reminder server con claim univoco, endpoint protetto da segreto e conversione ora legale/solare. Il job ricorrente non è stato attivato.
- Accesso backoffice basato sull’identità Sites; ogni query è limitata all’utente. Audit per modifiche anagrafiche, visite e documenti.
- Esperienza paziente mostrata in **anteprima interna allo studio**.

### Ancora da completare per l’uso reale

1. Creare repository GitHub e pubblicare su un ambiente con D1/R2 e identità configurata.
2. Portale con login paziente e autorizzazioni separate; prenotazione autonoma, richieste/cancellazioni, disponibilità e accesso ai soli documenti del paziente. L’anteprima presente non offre questi controlli e non va esposta pubblicamente.
3. Verificare qualifica professionale, iscrizione, partita IVA, regime fiscale e diciture dei documenti con la professionista e il consulente. Una laurea in Psicologia da sola non è presentata come titolo di psicologa.
4. Collegare Resend (dominio/mittente verificati) e WhatsApp Business (numero, template approvato e parametri data/ora). Collaudare con destinatari di test.
5. Attivare un job HTTPS ricorrente sul motore di reminder. Completare webhook firmati per consegna/fallimento e gestione degli errori: «Accettato dal provider» **non significa consegnato**. Attualmente gli invii falliti o incerti non vengono ritentati automaticamente.
6. Completare l’adapter Sistema TS sulle specifiche aggiornate per l’esatta categoria professionale, abilitazione/delega, cifratura richiesta, credenziali, ambiente test, ricevute, rettifiche e opposizione. Il pulsante TS risponde esplicitamente che l’invio è inattivo, senza creare false ricevute.
7. Completare gestione documenti da smartphone/WhatsApp attraverso link protetti del portale; attualmente l’invio PDF implementato è email, non WhatsApp.
8. Definire informative, basi giuridiche, modalità di comunicazione sanitaria, accordi fornitori, conservazione/cancellazione, backup/ripristino e controllo accessi prima di caricare dati reali. Le caselle privacy/preferenze registrano informazioni, non sostituiscono i documenti richiesti.
9. Ampliare verifiche end-to-end e sicurezza del sistema pubblicato. La QA nel browser non è stata disponibile nell’ambiente della consegna.

## Avvio

Richiede Node >=22.13 e pnpm. Il lockfile `pnpm-lock.yaml` è il riferimento.

```bash
pnpm install --frozen-lockfile
pnpm typecheck
pnpm test
pnpm build
pnpm dev
```

Per l’anteprima autosufficiente, senza backend:

```bash
node scripts/create-preview.mjs /percorso/assoluto/Clarissa_Bandini_Anteprima.html
```

Aprire l’HTML nel browser. Dati fittizi, modifiche in memoria nella sessione; PDF scaricabili, nessun invio esterno.

## Backend

Vinext/React/TypeScript su Cloudflare Workers, D1 per record e contatori, R2 per PDF. `.openai/hosting.json` dichiara `DB` e `BUCKET`; non contiene `project_id`, perché il servizio non ha creato alcun progetto. Il deploy attraverso Sites dovrà ottenere e registrare l’ID reale prima del push/publishing. Le migrazioni sono in `drizzle/`. Non creare tabelle nelle richieste HTTP.

Per lo sviluppo locale, leggere le istruzioni D1 del starter nel file `docs/STARTER_SETUP.md`. Il binding dell’identità di produzione è gestito da Sites: non usare header simulati su un server accessibile pubblicamente.

## Segreti

Solo server, attraverso il provider di hosting. Nomi in `.env.example`; nessun valore reale in Git, browser o archivio.

- `RESEND_API_KEY`, `MAIL_FROM`
- `WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_TEMPLATE`, `META_GRAPH_VERSION`
- `REMINDER_JOB_SECRET`
- `FISCAL_ISSUANCE_ENABLED`: l’emissione sul server è bloccata fino alla configurazione e al collaudo fiscale; solo allora impostare `true`.

Il template WhatsApp è in italiano, con due parametri BODY: data dell’appuntamento, ora. Configurare una versione Graph supportata verificata al momento dell’attivazione.

Scheduler: `POST /api/reminders/run` con `Authorization: Bearer <REMINDER_JOB_SECRET>`. Un job ricorrente dovrebbe invocarlo ogni 10 minuti, tramite una credenziale conservata dal servizio di scheduling. Il motore seleziona appuntamenti tra l’istante previsto del reminder e l’inizio visita. Non manda reminder per visite annullate, completate o già iniziate, né a indirizzi dimostrativi. Il segreto va mantenuto fuori dalla repository. L’endpoint non è stato attivato o collaudato in produzione.

## Test

11 test di dominio: CF e omocodia, coerenza anagrafica, date impossibili, prenotazioni, ora legale, struttura PDF e integrità della demo. Test aggiuntivo SQLite dei vincoli sulle prenotazioni: `python3 tests/database_test.py`. Build e typecheck completati con successo. Invii esterni e TS non sono stati collaudati con account reali.

## Repository GitHub

Nome proposto: `clarissa-bandini-studio`; visibilità consigliata: privata. Dopo la creazione autorizzata della repository, aggiungere l’origine e fare push del commit sorgente, escludendo runtime, `.env`, build, file clinici e dati locali. La workflow GitHub Actions esegue installazione, typecheck e test. La creazione effettiva è ancora pendente.

## Fonti per le integrazioni

Questi riferimenti servono alla successiva configurazione; non attestano la conformità del prodotto.

- Specifiche Sistema TS: https://sistemats1.sanita.finanze.it/portale/spese-sanitarie
- Documentazione normativa/disciplinare: https://def.finanze.it/DocTribFrontend/getAttoNormativoDetail.do?ACTION=getArticolo&articolo=Allegato+1&codiceOrdinamento=600000010000000&id=%7B1726D4FE-6F34-466D-AF36-29D59BBA6F49%7D
- Meta WhatsApp Cloud API, raccolta ufficiale: https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api
- Esempi ufficiali Meta: https://github.com/fbsamples/whatsapp-api-examples
- Resend API: https://resend.com/docs/api-reference/emails/send-email
