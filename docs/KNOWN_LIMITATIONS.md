# Limitazioni note

Aggiornato con la revisione pre-M3. La suite Django è stata eseguita su
PostgreSQL temporaneo. La verifica della CI GitHub resta separata.

- SPID/CIE, OIDC e registri professionali restano contratti senza provider attivi.
- La verifica degli iscritti è manuale. La demo legacy usa dati sintetici in memoria.
- L’audit M1 impedisce aggiornamenti e cancellazioni ordinarie nel DB. La catena
  di hash è disponibile da M2. I checkpoint esterni restano aperti.

## Funzionalità e controlli mancanti

- **M2:** grant attivi solo dopo consenso del paziente linkato; il registro si
  limita alle anagrafiche. M3 aggiunge audit documentale lato API. Testi seed da approvare legalmente. Il break-glass
  richiede relazione professionale con la struttura del paziente e non dispone
  di revisione amministrativa successiva. Email e notifiche sono generiche.
  Hash-chain globale senza checkpoint esterno; un amministratore DB privilegiato
  può alterare anche trigger e testa. Messaggi soltanto testuali e senza cifratura
  applicativa. Vedere [specifica M2](03-sharing-consent.md).
- **L05 / M3 in corso:** API documentale e ricerca per titolo disponibili. Mancano
  interfaccia portale, cartelle e grant per singolo documento, indice full-text e
  import R2. Il profilo FHIR espone solo Patient e DocumentReference. Restano
  aperti Organization, Practitioner, Consent, DiagnosticReport e Observation.
- **L06 / M3 in corso:** binari cifrati nel database. Restano aperti object storage,
  KMS e rotazione, retention con cancellazione controllata, restore e validazione
  strutturale dei formati. L'upload richiede ClamAV esterno. La verifica con uno
  scanner reale resta da completare. Vedere [documenti clinici](04-clinical-documents.md).
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
