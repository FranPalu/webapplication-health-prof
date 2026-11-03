# ADR 0001 — Backend Django e riuso frontend

Data: 2026-11-03. Stato: accettato, implementazione da M1.

## Contesto

Il gestionale è TypeScript/Vinext su Workers con D1/R2. Il committente ha scelto
Django fra mantenimento Cloudflare, backend Node/PostgreSQL e backend Django.
Non esiste ancora codice Django; una riscrittura del frontend non è necessaria.

## Decisione

Django 5.2 LTS + DRF + PostgreSQL/PostGIS, monolite modulare API-first. Django ORM
e migrazioni sostituiscono Drizzle nel nuovo backend. React, TypeScript, componenti
e stile vengono mantenuti, con Next.js su Node e routing same-origin verso DRF.
Node 24 allinea sviluppo e CI; patch e dipendenze Python saranno fissate in M1
dopo verifica sulle fonti ufficiali. Moduli AI/ETL separati come processi worker.

## Alternative e conseguenze

Node/PostgreSQL ridurrebbe la riscrittura del dominio; Cloudflare conserverebbe
il deployment esistente ma richiederebbe comunque servizi esterni per i worker.
Django segue la preferenza esplicita e permette un backend Python comune ai
servizi di elaborazione. Il costo è mantenere due toolchain e portare le regole
di dominio: i test legacy diventano vettori di regressione, non vengono eliminati
prima della verifica di parità. Nessuna sostituzione del backend in M0.
