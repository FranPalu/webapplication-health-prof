# ADR 0003 — Identità autonoma e sessioni server

Data: 2026-11-03. Stato: accettato, implementazione M1.

## Contesto

L'identità attuale dipende dagli header della piattaforma Sites. Il nuovo runtime
non può presumere l'esistenza dello stesso confine di fiducia. Il prodotto
richiede email/password, MFA e futura federazione.

## Decisione

Modello utente Django personalizzato prima della prima migrazione, password
Argon2, verifica email, sessioni server revocabili e protezione CSRF. Frontend
e API sullo stesso dominio, nessun token persistente in localStorage. Header
di identità legacy ignorati dal nuovo backend.

TOTP obbligatorio per professionisti e amministratori, segreti cifrati, recovery
code monouso protetti, verifica di replay e limitazione dei tentativi. Sessione
parziale fino al completamento MFA. Revoca sessioni e audit su recupero account
e reset MFA. Verifica professionale manuale distinta dalla verifica email.

Adapter OIDC/SPID/CIE e registri professionali espongono contratti documentati;
assenza di configurazione significa servizio disabilitato, non autenticazione
simulata. Nessun account viene creato fidandosi degli header del vecchio sistema.

## Conseguenze

Il portale diventa indipendente da Sites. Devono essere testati enrollment,
recovery, logout, session fixation, CSRF e accesso prima della verifica MFA.
Client non-browser potranno richiedere OAuth in una futura integrazione senza
indebolire la sessione web. In M0 non vengono generati account o credenziali.
