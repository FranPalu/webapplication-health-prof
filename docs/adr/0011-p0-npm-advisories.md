# ADR 0011 · Correzione degli avvisi npm alti

**Stato** Accettato per P0.

La scansione del lockfile completo ha trovato 28 avvisi alti nelle dipendenze di sviluppo. L'aggiornamento conserva Next e Vinext e allinea React, React DOM e React Server DOM Webpack a 19.2.8 per rispettare i vincoli del renderer. Vite passa a 8.1.6. Gli override limitati alle major già presenti fissano le versioni corrette di undici, ws, brace-expansion, js-yaml e image-size. Il lockfile è rigenerato con pnpm 11.25.0 e la policy esistente sull'età minima dei rilasci.

La prova di uscita usa installazione congelata, lint, type-check, test, build ed E2E su Node 24. Il grafo completo è sottoposto al gate high anche in CI. Gli avvisi residui e la copertura delle scansioni sono in [Evidenze P0](../p0/verification.md). Rivedere gli override quando i pacchetti a monte incorporano le correzioni.
