# M2 — Condivisioni, consensi e collaborazione

## Modello e API

Le API sono sotto `/api/v1`: `shares/`, `shares/{id}/patient/`,
`shares/{id}/download/`, `shares/{id}/messages/`, `shares/{id}/revoke/`,
`consents/texts/`, `consents/`, `notifications/`, `patients/access-history/` e
`break-glass/`. Le richieste che modificano dati richiedono la sessione e CSRF
già introdotti in M1.

Un grant individua il paziente, il concedente, un utente professionista o
un'organizzazione destinataria, lo scope, i permessi, la finalità, una scadenza
facoltativa e un eventuale grant padre. Il destinatario deve avere la membership
attiva nell'organizzazione o una verifica professionale valida. Le risorse
condivisibili in M2 sono soltanto anagrafiche paziente; i documenti sono rinviati
a M3. `item` e `chart` sono mantenuti nel modello, ma entrambi risolvono alla
sola anagrafica finché M3 non estende il registro.

Un grant resta inattivo finché il paziente collegato non registra un evento di
consenso per la versione del testo presentata. Gli eventi non si aggiornano:
revoca e nuovo consenso sono nuove righe. La verifica del consenso e di tutti i
grant antenati avviene ad ogni accesso, inclusi messaggi e download. Un grant
derivato non può aumentare i permessi né superare la scadenza del padre; la
revoca esplicita marca anche i discendenti come revocati.

I testi iniziali IT/EN sono segnaposto operativi da revisionare prima dell'uso:
non sono parere legale, non selezionano né sostituiscono la base giuridica ai
sensi degli articoli 6 e 9 GDPR. La revisione del DPO/consulente è necessaria.

## Audit e break-glass

Ogni `AuditEvent` riceve una sequenza e un hash SHA-256 calcolato su campi
canonici e hash precedente. Un lock PostgreSQL sulla testa globale serializza
le append; il trigger M1/M2 impedisce update e delete ordinari. Migrazioni
ricalcolano la catena storica. Verificare con:

```sh
make dev
docker compose --env-file .env.dev exec backend python manage.py verify_audit_chain
```

Il break-glass richiede professionista verificato, membership nella struttura,
MFA della sessione, motivazione specifica e durata di 15 minuti. Le aperture e
le letture sono auditate; il paziente collegato riceve una notifica generica.
Non c'è ancora un workflow amministrativo di revisione e gli hash non sono
ancorati a checkpoint o storage immutabile esterno.

## Limiti del rilascio M2

- I download restituiscono solo JSON dell'anagrafica, non file clinici.
- Non sono implementati cartelle gerarchiche, risorse cliniche generiche o
  condivisione di documenti; M3 aggiungerà il registro dei documenti.
- Il messaggio sicuro è testo append-only senza allegati, cifratura applicativa
  o stato di lettura. Il provider email invia solo un avviso generico.
- La catena è globale e può serializzare molte scritture; non è un checkpoint
  indipendente e non protegge da un amministratore DB capace di alterare anche
  schema, trigger e testa.
- Il break-glass è limitato ai professionisti con membership nell'organizzazione
  del paziente; non c'è accesso inter-organizzazione né revisione successiva.
- Testi e procedure devono essere valutati rispetto a finalità, ruoli, basi
  giuridiche, tempi di conservazione e informative effettive del titolare.
