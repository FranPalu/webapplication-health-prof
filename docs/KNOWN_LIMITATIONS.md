# Limitazioni note

Aggiornato: 2026-11-04, M1. I controlli applicativi M1 sono passati su GitHub
per il commit `4c2c019`. Il job Compose si è fermato sul download di MinIO.
La correzione usa SeaweedFS e richiede una nuova esecuzione del job.

- SPID/CIE, OIDC e registri professionali restano contratti senza provider attivi.
- La verifica degli iscritti è manuale. La demo legacy usa dati sintetici in memoria.
- L’audit M1 impedisce aggiornamenti e cancellazioni ordinarie nel DB. La catena
  di hash e i checkpoint esterni sono previsti in M2.

## Funzionalità e controlli mancanti

- **L05 / M2:** consensi versionati, Share, revoca, break-glass, audit letture e
  messaggistica clinica protetta non implementati. I booleani legacy non li sostituiscono.
- **L06 / M3:** upload solo PDF, controllo firma iniziale; assenti antivirus,
  cifratura applicativa per tenant, retention completa, ricerca e FHIR.
- **L07 / M4:** nessun modello AI, provider, registry, golden set o processo di
  revisione. Scelta del modello e relativo uso clinico devono essere verificati
  nella milestone; non c'è alcuna capacità diagnostica disponibile.
- **L08 / M5:** Stripe/Connect, SDI e rimborsi assenti. Fatture legacy richiedono
  configurazione fiscale verificata; ENPAB non è una regola per tutte le professioni.
- **L09 / M6:** portale paziente è un'anteprima interna; mancano prenotazione
  autonoma, farmacia, validazione ricette ufficiale e ricerca geografica.
- **L10 / M7:** nessun archivio ricerca, anonimizzazione validata o catalogo.
  Pseudonimi non equivalgono ad anonimato; export già scaricati non sono recuperabili
  tecnicamente tramite una semplice revoca.
- **L11 / M8:** interfaccia italiana e responsive, ma WCAG 2.2 AA, IT/EN complete,
  dashboard per tutti i ruoli e PWA non sono state verificate/implementate.
- **L12 / M9:** assenti prova di restore, audit immutabile esterno, osservabilità
  completa, workflow GDPR, CI/CD produttiva ed E2E completi.

## Integrazioni e prove esterne

- Email e WhatsApp hanno adapter e test con mock; credenziali, consegna reale,
  scheduler e webhook produttivi non verificati. Accettazione provider non è consegna.
- Non verificati deployment, dati remoti, residenza UE, DPA, scansione segreti
  completa, dipendenze vulnerabili o tempi p95. Non dedurre assenza di segreti o
  dati reali dall'assenza di evidenze durante questo audit.
- SPID/CIE, registri, SDI e sistemi ricette saranno interfacce documentate nelle
  rispettive milestone. Nessun endpoint finto è stato aggiunto in M0.
- Qualificazione MDR/AI Act, DPIA e procedure operative restano da valutare;
  vedere [note normative](compliance/regulatory-notes.md).

Ogni voce si chiude solo con evidenza di implementazione e verifica nel CHANGELOG.
Nessuna limitazione è risolta dalla sola aggiunta della documentazione M0.
