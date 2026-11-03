# ADR 0002 — Tenancy relazionale e policy centralizzate

Data: 2026-11-03. Stato: accettato, implementazione M1–M3.

## Contesto

Il filtro owner esistente non rappresenta professionisti con più organizzazioni,
pazienti condivisi o grant fra strutture. Uno schema DB per tenant renderebbe
più complessi riferimenti e concessioni inter-organizzazione.

## Decisione

Schema condiviso PostgreSQL, tenant proprietario esplicito sulle risorse,
membership e relazioni di cura separate. Account globale; anagrafiche e fascicoli
per organizzazione, senza deduplicazione globale automatica per codice fiscale.
Un collegamento verificato può associare lo stesso paziente a più schede.

Policy deny-by-default centralizzate e applicate a queryset, singola risorsa,
creazione, export, storage e job. Ruolo amministrativo e membership non implicano
lettura clinica. Share concede solo diritti espliciti sulla risorsa registrata,
con riferimenti e tenant verificati. I vincoli DB proteggono le relazioni;
eventuale RLS sarà difesa aggiuntiva, non promessa come già implementata.

## Conseguenze e verifiche

Serve una matrice di test negativi per ogni endpoint: tenant assente/alterato,
ID esterno, ruolo incompatibile, relazione cessata, grant revocato/scaduto.
Anche conteggi e ricerca devono essere filtrati. Import legacy non può generare
consensi validi dai booleani esistenti. Le condivisioni transitano dal servizio
policy, senza connessioni DB privilegiate per il destinatario.
