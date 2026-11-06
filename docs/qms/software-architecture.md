# SAD · Architettura software e classi di sicurezza

Baseline osservata in [audit P0](../p0/gap-analysis.md). Architettura generale in [SAD storica](../01-architecture.md). Identità e autorizzazione sono applicate da Django. Il browser Next usa cookie di sessione e API DRF dietro Nginx. PostgreSQL gestisce record, autorizzazioni, audit e job. Il backend accede a storage privato, scanner e chiavi. Worker Celery elaborano job con Redis. Il collaudo imaging usa un container offline distinto. Il rilascio ricerca passa da snapshot e workflow dedicato.

## Confini e comportamento in errore

- **Browser → API.** Trattare sessione, ID e input browser come non fidati. Le autorizzazioni si verificano nel backend. I ruoli UI sono di presentazione.
- **API → DB e storage.** Le autorizzazioni applicative filtrano tenant, relazione o grant. Lo storage documentale è privato. Le azioni sensibili richiedono audit prima della risposta dove implementato. Il ruolo proprietario DB e l'assenza di checkpoint indipendente sono limiti aperti.
- **API → job → pubblicazione.** L'input è versionato. I controlli di accesso sono rivalutati dal worker e nei percorsi di revisione. La bozza è separata dal parere attestato. Il percorso corrente di analisi richiede DEBUG e flag, e il paziente vede solo la pubblicazione esplicita. Il gate di firma elettronica resta da implementare.
- **Ricerca e sistemi esterni.** Rilasciare solo proiezioni autorizzate. Un sistema esterno non fornisce un'identità o esito clinico autorevole senza validazione di provenienza, profilo, scope e identificatori. Le integrazioni senza verifica rimangono disabilitate.
- **Errore, indisponibilità e retry.** Per i futuri flussi critici, stato incompleto e presa in carico mancata restano visibili fino a risoluzione. Retry idempotenti e recovery mantengono legame al paziente e alla versione. Il piano di downtime e le prove di failover sono in P10.

## Allocazione IEC 62304 proposta

**DA VALIDARE da professionista abilitato.** Stima di pianificazione per il prodotto clinico candidato. A indica che l'item non può contribuire a lesione o danno alla salute nel perimetro definito. B contempla lesione non grave. C contempla morte o lesione grave. Le classi dipendono da pericolo, contributo e controlli esterni al software. Per una decomposizione a classe inferiore servono interfacce, segregazione e razionale provati. La supervisione umana, da sola, non abbassa la classe.

| Sistema o item | Proposta | Razionale e vincolo |
| --- | --- | --- |
| Sistema clinico candidato e cartella/referti | C | Associazione o versione errata può guidare decisioni gravi |
| Identità, tenant, consenso, storage, audit e ripristino nel percorso clinico | C | Accesso alla persona sbagliata, alterazione o perdita di informazioni possono contribuire a danni gravi. La segregazione di sottocomponenti va dimostrata |
| Ingestione, terminologia, FHIR e interfacce cliniche | C | Errore di unità, soggetto o provenienza attraversa il confine di sistema |
| OCR, estrazione, AI, review, firma e pubblicazione | C | Falso negativo, falso positivo o pubblicazione prematura possono alterare l'assistenza |
| Alert critici, regole farmaci, telemonitoraggio e handover | C | Ritardi o dati errati possono avere conseguenze gravi |
| UI che mostra contesto, risultati o azioni cliniche | C | È parte del controllo d'identità, delle conferme e della percezione degli alert |
| Booking ordinario e farmacia con verifica esterna | B come ipotesi di item separato | Il ritardo può causare danno. Urgenze e priorità cliniche richiedono nuova valutazione. Gate farmaco dipende da verifica indipendente e segregazione |
| Pagamento e amministrazione separata | A come ipotesi di item separato | Nessun controllo clinico può dipendere dal pagamento o da questo item. Separazione da dimostrare |
| Ricerca aggregata separata e demo sintetica | A come ipotesi di item separato | Nessun input di questi ambienti determina azioni cliniche. Restano rischi privacy e integrità |

Le classi A/B sono candidate per la decomposizione, con trattamento conservativo C per gli item nel confine clinico senza segregazione provata. Questa classificazione software è distinta dalle classi MDR/IVDR. [Qualificazione preliminare](../compliance/mdr-qualification.md)
