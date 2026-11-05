# M9 — Verifica di rilascio

## Risultati del 5 novembre 2026

Docker Desktop su Mac arm64, PostgreSQL/PostGIS amd64 e due worker Gunicorn.
Otto rotte, 100 letture misurate per rotta e per livello di concorrenza.

- **8 richieste parallele.** Intervallo dei p95 da 214,53–346,23 ms a
  27,05–40,39 ms dopo il riuso delle connessioni.
- **24 richieste parallele.** Intervallo dei p95 da 614,18–956,01 ms a
  43,10–79,05 ms. Il massimo dopo la modifica è sulle condivisioni.
- **Affidabilità HTTP.** 800 risposte HTTP 200 per passaggio, prima e dopo.
- **Ripristino locale.** Recuperate tre anagrafiche sintetiche, un evento
  verificato nella catena di audit e un valore cifrato decifrato con la
  chiave locale.
- **Backend.** 49 test Django superati e copertura complessiva misurata
  dell'82,27% sul perimetro configurato. Migrazioni allineate.
- **Browser.** 22 scenari superati sul profilo standard, incluso il collaudo
  per i sei ruoli. Il caso con worker AI è separato dal profilo standard.
- **Analisi locale.** F1 pari a 1,000 su cinque righe PDF native e cinque
  righe scansionate. Il riepilogo Qwen è stato validato e il test isolato di
  imaging è riuscito. Le misure riguardano le fixture sintetiche.
- **Dipendenze JavaScript.** `pnpm audit --prod` ha riportato 23 avvisi
  prima degli aggiornamenti e zero dopo. Next.js è passato a 16.4.1 e Zod
  a 4.6.6. La scansione in CI blocca gli avvisi alti e critici sulle
  dipendenze di produzione. [Avviso Next.js](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw)
- **Dipendenze Python.** `pip-audit` non ha segnalato vulnerabilità note
  per i 65 pacchetti risolti da `backend/requirements.txt`. La CI ripete
  il controllo. Immagini di base e dipendenze dei container AI restano
  fuori dal perimetro di questa scansione.

## Riproduzione locale

Avviare `make dev`. Generare una fixture per il benchmark e passarla allo
script via stdin. Il file temporaneo contiene credenziali sintetiche e viene
rimosso all'uscita.

```sh
fixture="$(mktemp)"
trap 'rm -f "$fixture"' EXIT
docker compose --env-file .env.dev exec -T backend python manage.py shell -v 0 \
  < backend/tests/clinical_browser_fixture.py > "$fixture"
python3 scripts/benchmark-local.py --concurrency 8 < "$fixture"
python3 scripts/benchmark-local.py --concurrency 24 < "$fixture"
```

Ogni passaggio misura 100 richieste per rotta dopo 5 richieste di riscaldamento.
I percentili includono client HTTP, proxy, Django e database. Il benchmark
misura letture con un solo account paziente e una base sintetica piccola. Gli
elenchi di prenotazioni, farmacia e pagamenti possono essere vuoti. Lo script
segnala un errore se una rotta supera la soglia di 500 ms al p95 o restituisce
uno stato diverso da HTTP 200. Ripetere con dati sintetici di volume
rappresentativo e concorrenza mista prima di approvare il rilascio.

`scripts/restore-drill.sh` crea due database temporanei nello stack locale,
esegue migrazioni e seed nel primo, quindi trasferisce il dump al secondo.
Verifica le migrazioni, la catena di audit e la decifratura di un valore di
prova con la chiave applicativa locale. Il trap elimina i due database creati
dallo script. La prova usa il server PostgreSQL di sviluppo. Per il rilascio
servono anche ripristino su un ambiente separato, ripristino degli oggetti
clinici e delle chiavi da custodia indipendente, archivio di ricerca e tempi
di ripresa misurati.

## Verifiche di sicurezza e privacy aperte

- **Identità e privilegi.** I test esercitano CSRF, MFA, permessi e accessi negati
  tra organizzazioni. Verificare HTTPS, cookie e confine di fiducia del proxy
  sulla configurazione di produzione.
- **Manomissione e tracciabilità.** Il ripristino locale verifica la catena
  PostgreSQL. Servono checkpoint esterni con privilegi separati e una prova
  di rilevamento delle modifiche dopo un ripristino.
- **Esposizione dei dati.** Esaminare log, error tracking, backup ed export.
  Verificare che i servizi esterni ricevano soltanto i dati autorizzati.
- **Disponibilità.** Misurare letture e scritture con un carico misto.
  Simulare perdita di database, storage, coda e worker. Il proxy ha un
  controllo di readiness per PostgreSQL.
- **Verifica ASVS.** Registrare evidenza, esito e responsabile per i requisiti
  L2 applicabili. Servono anche scansioni di dipendenze, segreti e codice
  con verifica delle configurazioni di rilascio. [OWASP ASVS 5.0](https://asvs.owasp.org/)
- **Privacy.** Definire titolare, finalità, categorie, basi giuridiche, fornitori,
  residenza, retention e modalità di esercizio dei diritti. Completare
  portabilità, cancellazione con vincoli di conservazione e prova della
  procedura di gestione degli incidenti. Sono disponibili le
  [schede per registro, DPIA e gestione incidenti](compliance/privacy-operations.md)
  e le [note normative](compliance/regulatory-notes.md).

## Consegne ancora aperte

- **M4.** La validazione storica riguarda le fixture locali. Restano
  calibrazione clinica, conferma dei limiti di impiego e verifica sui formati
  di destinazione. [Collaudo M4](05-m4-validation.md)
- **M5–M7.** Pagamenti simulati e integrazioni esterne secondo le
  [limitazioni note](KNOWN_LIMITATIONS.md). Restano le prove di rilascio
  dell'archivio di ricerca con configurazione e dati rappresentativi.
- **M8.** Collaudo con lettore di schermo e revisione completa IT/EN.
  [Design system](design-system.md)
- **M9.** Ambiente di produzione, osservabilità, CI/CD di rilascio, scansioni,
  esercitazione completa di ripristino, flusso browser integrato tra più
  moduli, procedure privacy e valutazioni cliniche e normative.
