# Limitazioni note

P2 implementa identificazione, episodi ambulatoriali e storico dei referti in un perimetro limitato. La riconciliazione reversibile collega schede mantenendone distinti i dati. Restano aperti fusione canonica, rappresentanza, cartella estesa, cataloghi e profili, firma e conservazione. [Limiti P2](10-clinical-record-p2.md)

P1 mantiene il rilascio clinico bloccato. Destinazione e classi sono preliminari, i responsabili sono ruoli da designare e gli hazard attendono evidenze e accettazione. Lo snapshot SOUP copre le versioni dichiarate, con SBOM per immagini, pacchetti OS e verifica dei diritti dei pesi imaging ancora aperte. Il profilo imaging offline ha advisory aperti su PyTorch, pip e setuptools. Resta limitato alle fixture sintetiche isolate fino a remediation e nuova prova P4. [Fascicolo P1](qms/README.md)

La [gap analysis P0](p0/gap-analysis.md) aggiorna lo stato verificato. Restano aperti il ruolo DB runtime a privilegi minimi, il checkpoint indipendente dell’audit, la copertura negativa per endpoint, la firma clinica, i gate di sicurezza in CI e sette avvisi npm moderati o bassi nel grafo completo. Vedere gli [esiti di verifica](p0/verification.md).

- Le operazioni nei portali dimostrativi riguardano dati fittizi e salvano
  lo stato nel browser. Il portale autenticato usa i dati e le autorizzazioni
  del backend.

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
- **L05 / M3:** ricerca testuale per PDF con testo incorporato. OCR e ricerca nel
  contenuto delle immagini richiedono M4. FHIR R4 espone letture per le sette
  risorse previste. I profili di integrazione e la terminologia richiedono
  validazione con i sistemi destinatari.
- **L06 / M3:** storage S3 e ClamAV verificabili in locale. AWS KMS e import R2
  richiedono credenziali e configurazione esterne. La retention richiede una policy
  per tenant. DICOM è verificato a livello di metadati. Vedere
  [documenti clinici](04-clinical-documents.md).
- **L07 / M4:** workflow referti attivabile solo in DEBUG per il collaudo.
  Imaging limitato a fixture autorizzate nel container disconnesso. Analiti,
  impaginazioni e confronto degli intervalli limitati alle forme supportate.
  L'attestazione è interna. Restano da validare sul campo la pipeline, i termini
  dei pesi imaging, la retention delle copie derivate e il rilascio clinico.
  Vedere [guida M4](05-supervised-analysis.md).
- **L08 / M5 in corso:** simulazione interna via API, inclusi rimborsi integrali.
  Restano portale, documenti contabili e integrazione reale.
  Vedere [simulazione M5](06-payments-sandbox.md).
- **L09 / M6:** SMS e verifica ufficiale NRE richiedono adapter di deployment.
  Allegati PDF e NRE sono utilizzabili quando è collegato un verificatore.
  Vedere [guida M6](07-bookings-pharmacy.md).
- **L10 / M7:** rilascio limitato alla proiezione aggregata fissa, disabilitato
  per default. Gli export già consegnati non sono richiamabili. Cataloghi
  terminologici completi e verifica dei profili FHIR dipendono dal deployment.
  Vedere [nota tecnica M7](research-anonymization.md).
- **L11 / M8:** riepiloghi dei sei profili, manifest installabile e uno scenario
  Django per ruolo. Restano il collaudo con lettore di schermo e la verifica
  completa delle traduzioni IT/EN dei moduli.
  Vedere [design system](design-system.md).
- **L12 / M9:** ripristino PostgreSQL verificato su dati sintetici nello stack locale.
  Restano il ripristino completo di storage e chiavi, audit immutabile esterno,
  osservabilità completa, workflow GDPR, CI/CD produttiva ed E2E integrato.
  Vedere il [rapporto di verifica](09-release-verification.md).

## Integrazioni e prove esterne

- Email e WhatsApp hanno adapter e test con mock; credenziali, consegna reale,
  scheduler e webhook produttivi non verificati. Accettazione provider non è consegna.
- Restano da verificare deployment, dati remoti, residenza UE, DPA, segreti,
  immagini dei container e p95 con carico produttivo. Il rapporto M9
  documenta il perimetro delle scansioni delle dipendenze e del carico locale.
- SPID/CIE, registri, SDI e sistemi ricette saranno interfacce documentate nelle
  rispettive milestone. Nessun endpoint finto è stato aggiunto in M0.
- Qualificazione MDR/AI Act, DPIA e procedure operative restano da valutare;
  vedere [note normative](compliance/regulatory-notes.md).

Ogni voce si chiude solo con evidenza di implementazione e verifica nel CHANGELOG.
Nessuna limitazione è risolta dalla sola aggiunta della documentazione M0.
