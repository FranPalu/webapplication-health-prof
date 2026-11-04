# Note normative preliminari

Data: 2026-11-03. Stato: requisiti di progettazione e attività da svolgere.
Questo documento non è un parere legale né una dichiarazione di conformità.

## Implementato e pianificato

Il legacy ha isolamento per owner, alcune validazioni, preferenze di comunicazione,
audit delle modifiche e protezione dalla cancellazione di pazienti con fatture
emesse. Questi elementi non costituiscono un programma completo di conformità.
M0 aggiunge solo documentazione. I controlli target sono descritti in
[architettura](../01-architecture.md); i mancanti in [limitazioni](../KNOWN_LIMITATIONS.md).

## Privacy e dati sanitari

Trattare dati clinici, metadati identificanti e documenti come informazioni ad
alta sensibilità. Per ogni finalità documentare titolare/responsabile, base
giuridica, condizione applicabile ai dati sanitari, destinatari e conservazione.
Non assumere che il consenso sia l'unica base possibile per ogni trattamento.
Separare assistenza, condivisione facoltativa, comunicazioni e ricerca; revoca
dei consensi non equivale automaticamente a cancellazione di documenti soggetti
a conservazione. Il software deve rappresentare queste distinzioni.

Prima dei dati reali: revisione legale/DPO, DPIA, registro trattamenti, informative
versionate, accordi con fornitori, verifica subprocessori e residenza UE inclusi
backup, log e assistenza. Definire tempi e basi della retention, legal hold,
portabilità, richieste di cancellazione e gestione delle violazioni. I template
M9 richiedono compilazione e approvazione da parte del titolare, non solo generazione.

Riferimento primario: [GDPR — Regolamento (UE) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj),
in particolare articoli 5, 6, 9, 25, 28, 30, 32–35 e diritti degli interessati.

## AI, MDR e sicurezza clinica

L'uso previsto e le funzionalità effettive devono essere valutati da specialisti
regolatori prima di attivare analisi cliniche. Un disclaimer e la supervisione
umana non escludono da soli la qualificazione come software dispositivo medico
o gli obblighi applicabili all'AI. Non attribuire automaticamente una classe.

Definire destinazione d'uso, utilizzatori, popolazioni, dati di ingresso, limiti,
errori prevedibili e gestione del rischio; valutare qualificazione/classificazione
MDR, evidenze cliniche, eventuale marcatura CE e obblighi lungo il ciclo di vita.
Per AI Act verificare ruolo del fornitore/deployer, classificazione, requisiti
e calendario applicabile al rilascio, senza fissare qui scadenze non validate.

Controlli progettati in M4: modelli pre-addestrati con licenze/versioni fissate,
provenienza degli output, golden set, revisione accetta/modifica/rifiuta, parere
finale distinto e monitoraggio degli esiti. Nessuna diagnosi o decisione
terapeutica autonoma. L'attestazione applicativa del revisore non è presentata
come firma elettronica qualificata; eventuali requisiti di firma vanno specificati.

Fonti primarie: [MDR — Regolamento (UE) 2017/745](https://eur-lex.europa.eu/eli/reg/2017/745/oj)
e [AI Act — Regolamento (UE) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj).

## Ricerca, interoperabilità e standard

Consenso ricerca esplicito come requisito di prodotto; valutazione legale del
protocollo e delle basi applicabili resta separata. HMAC e generalizzazione sono
misure di pseudonimizzazione; k-anonymity e soppressione non provano anonimato.
Documentare rischio di re-identificazione, query combinate, export, revoca e
obblighi dei destinatari. Verificare licenze e condizioni di LOINC, SNOMED CT,
ICD-10, dataset pubblici e modelli prima della distribuzione.

API FHIR non equivale ad accreditamento o interoperabilità operativa FSE.
Verificare requisiti AgID/FSE, disposizioni del Garante e specifiche dei sistemi
ufficiali per SPID/CIE, albi, ricette, SDI e Sistema TS prima delle integrazioni.
Non simulare esiti ufficiali. Valutare applicabilità e perimetro di ISO 27001,
ISO 13485 e IEC 62304; non dichiarare certificazioni o aderenza non dimostrate.

## Gate prima dell'uso clinico

Responsabile prodotto e titolare devono disporre di: esiti revisione legale e
regolatoria, DPIA e accordi completati, valutazione sicurezza, prova restore,
runbook incidenti, validazione clinica pertinente e documentazione dei rischi
residui. La chiusura tecnica M9 non sostituisce queste approvazioni.

Limite della verifica M0: gli URL EUR-Lex sono riferimenti normativi ufficiali;
il tentativo di lettura del 2026-11-03 ha incontrato una verifica anti-bot.
Non è stata completata una verifica articolo per articolo o del testo consolidato;
va ripetuta nella revisione legale prima del rilascio.


### Evidenze tecniche M4

Il collaudo locale separa bozze automatiche, revisione e pareri attestati.
I pazienti ricevono solo il parere pubblicato. Imaging confinato a fixture
autorizzate. La pipeline non invia dati a provider esterni. Prima di un rilascio
su dati reali occorre documentare uso previsto, valutazione clinica, DPIA,
retention di bozze e copie derivate, verifica delle licenze e applicabilità di
MDR e AI Act. La firma interna attesta il testo nell'applicazione.
