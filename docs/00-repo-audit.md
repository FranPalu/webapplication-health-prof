# M0 — Audit della repository

Aggiornamento del 6 novembre 2026 nella [gap analysis P0](p0/gap-analysis.md). Questo documento conserva la fotografia storica M0.

Data: 2026-11-03. Baseline: `ffccd98`. Perimetro: analisi locale del sorgente,
configurazione, migrazioni e controlli disponibili; nessun accesso a dati o servizi
di produzione. `AGENTS.md` era già presente come file non tracciato e non è stato modificato.

## Esito

Esiste un gestionale per uno studio di nutrizione, non un backend Django. Il suo
riuso riguarda soprattutto interfaccia, regole di dominio e test di regressione.
Il backend Django è una scelta esplicita del committente, documentata in
[ADR 0001](adr/0001-django-backend.md). La piattaforma sanitaria descritta in
`AGENTS.md` non è ancora implementata; M0 consegna solo documentazione.

## Inventario e convenzioni

- `package.json`: React 19.2.6, Next 16.3.4, TypeScript 5.9.3, Drizzle 0.45.2,
  Tailwind 4.2.1, Zod 3; pnpm 11.25.0, Node >=22.13.0. Versioni dichiarate,
  non attestazione di sicurezza delle dipendenze.
- `scripts/run-framework.mjs`, `vite.config.ts`, `build/`: esecuzione Vite/Vinext,
  integrazione Sites e Cloudflare. `start` usa Wrangler, non Next su Node.
- `app/Studio.tsx`: interfaccia concentrata in un componente, testi italiani,
  modalità demo in memoria e collegamento alle API. `components/ui/` offre
  componenti riutilizzabili; `app/globals.css` contiene lo stile dello studio.
- `app/api/`: studio, pazienti, file, PDF, integrazioni, invio, reminder e webhook.
- `lib/`: validazione, codice fiscale, appuntamenti, PDF, provider, reminder e
  pulizia dei file. Codice frequentemente compresso; presenza di `any`.
- `db/schema.ts`: record JSON per proprietario, audit, contatori fatture,
  slot appuntamenti e coda cancellazione file. `db/index.ts` lega Drizzle a D1;
  parte del backend usa SQL D1 direttamente in `lib/server.ts`.
- `drizzle/`: tre migrazioni SQL registrate nel journal. Trigger proteggono
  riferimenti paziente, fatture emesse e cancellazioni concorrenti.
- `tests/`: test Node e verifica Python delle migrazioni SQLite in memoria.
- `.github/workflows/ci.yml`: installazione bloccata sul lockfile, Node 24,
  typecheck e test Node/Python. Non include lint, build, copertura o E2E.
- `.github/workflows/reminders.yml`: scheduler separato. Le guide esistenti
  documentano setup e comunicazioni; non attestano un deployment operativo.
- `.env.example` e `.dev.vars.example`: variabili dei canali e feature flag;
  nessun nuovo segreto richiesto o generato in M0.

## Controlli riproducibili

Baseline locale Node `22.9.0`. pnpm rifiuta questo runtime: la versione minima
richiesta è `22.13.0`. Non sono state installate dipendenze o cambiate versioni.

```bash
node --version
node node_modules/typescript/bin/tsc --noEmit --incremental false
node node_modules/eslint/bin/eslint.js . --ignore-pattern dist --ignore-pattern .next
node --import tsx --test tests/*.test.ts
python3 tests/database_test.py
```

- Typecheck diretto: superato.
- ESLint: 19 errori, 7 warning; fra le cause `no-explicit-any`, `prefer-const`
  e variabili inutilizzate. Il controllo non è verde.
- Node: 19 test passati; `tests/reminders.test.ts` non caricato a causa di
  `ERR_UNKNOWN_BUILTIN_MODULE` per `node:sqlite`. Non equivale a suite superata.
- Python/SQLite: superati vincoli sugli slot, rollback, isolamento proprietario,
  blocco cancellazione con fatture emesse, cascade, cleanup e riferimenti concorrenti.
- Non verificati: build, browser, deployment, provider reali, load test,
  copertura, vulnerabilità delle dipendenze e scansione completa dei segreti.

In M1 uniformare Node a 24 come la CI, ripetere i comandi ufficiali pnpm e
correggere i fallimenti prima di avanzare. M0 registra i difetti preesistenti,
senza introdurre correzioni applicative fuori perimetro.

## Rischi e priorità

1. **Alta — confine di autenticazione.** `app/chatgpt-auth.ts` legge header
   `oai-authenticated-*`; la garanzia dipende dal proxy fidato. Non è stata
   dimostrata una vulnerabilità del deployment, ma riutilizzare tale fiducia
   su un server pubblico autonomo permetterebbe identità non verificate.
2. **Alta — autorizzazioni insufficienti per il prodotto.** `lib/server.ts`
   filtra per `owner`; manca il modello di organizzazione, ruolo, relazione di
   cura e delega. Nessun endpoint attuale va presentato come multi-tenant sanitario.
3. **Alta — consensi non granulari.** `lib/validation.ts` usa booleani privacy
   e comunicazioni, non evidenze versionate con finalità, ambito e revoca.
4. **Alta — documenti.** `app/api/files/route.ts` controlla dimensione e firma
   iniziale PDF; non implementa antivirus, envelope encryption per tenant,
   retention o versionamento. La cifratura infrastrutturale R2 non prova tali requisiti.
5. **Alta — audit.** `studio_audit` registra modifiche; mancano accessi in
   lettura, catena di hash, checkpoint e protezione esterna dall'alterazione.
6. **Media — scalabilità.** `readRecords` carica record per proprietario e
   `record` ricerca in memoria; `/api/studio` restituisce lo stato completo.
   Servono query indicizzate, paginazione e filtri autorizzativi prima della lettura.
7. **Media — input/errori.** I limiti su Content-Length non sono sufficienti
   per richieste senza quell'header; `failure` può propagare messaggi interni.
   Servono limiti effettivi sul corpo e risposte pubbliche sanitizzate.
8. **Media — cancellazione e fiscalità.** I trigger proteggono fatture emesse,
   ma non costituiscono una politica di conservazione clinica. ENPAB e branding
   dello studio non devono diventare regole universali per tutti i professionisti.

## Copertura dei requisiti

- **M1:** identità delegata e separazione owner presenti; organizzazioni, ruoli,
  onboarding, verifica professionale, password e MFA assenti.
- **M2:** preferenze comunicazioni e audit modifiche presenti; Share, consenso
  versionato, emergenze, conversazioni protette e dashboard accessi assenti.
- **M3:** PDF e archivio presenti; altri formati, FHIR, ricerca autorizzata,
  quarantena e cifratura applicativa assenti.
- **M4:** nessuna pipeline AI o revisione clinica implementata.
- **M5:** bozze fattura e numerazione presenti; Stripe/Connect, rimborsi,
  webhook pagamento e SDI assenti.
- **M6:** agenda e reminder presenti; portale paziente autenticato, disponibilità
  multi-organizzazione, farmacie e geografia assenti.
- **M7:** nessun archivio o processo di ricerca implementato.
- **M8:** UI responsive e componenti presenti; i18n completa, dashboard per ruolo
  e verifica WCAG 2.2 AA non presenti.
- **M9:** alcuni vincoli SQL e firme webhook presenti; hardening completo,
  restore, osservabilità, privacy operativa e prove di conformità assenti.

## Consegna

Vedere [architettura](01-architecture.md), [roadmap](02-roadmap.md),
[limitazioni](KNOWN_LIMITATIONS.md) e [note normative](compliance/regulatory-notes.md).
Nessuna funzionalità nuova è abilitata. Prossimo passo: M1 solo dopo «GO M1».
