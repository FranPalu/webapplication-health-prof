# ADR 0012 · Registro qualità versionato e gate separati

**Stato** Accettato per P1 come meccanismo di repository.

Il registro in JSON consente di collegare hazard, requisiti, fase e test senza un sistema QMS esterno. Il controllo in CI verifica riferimenti, copertura dell'inventario rispetto alle versioni dichiarate e unit test. Il comando di rilascio clinico fallisce se esistono rischi bloccanti o accettazioni prive di riferimenti. Una modifica di stato nel registro resta soggetta a change control, evidenza e firme reali. Un esito tecnico positivo non costituisce autorizzazione.

La suite Django senza scanner e storage esegue prove funzionali senza la soglia di copertura, perché salta l'integrazione. La soglia locale dell'80% rimane nel job Compose con integrazione. Il target globale dell'85% rimane un requisito di rilascio. P1 aggiunge Bandit e Semgrep alla CI. Le regole pubbliche Semgrep vanno fissate o archiviate con digest per la release regolata.

[QMS](../qms/README.md) · [Piano V&V](../qms/verification-validation.md) · [Riesame clinico simulato](../qms/clinical-validation-log.md)
