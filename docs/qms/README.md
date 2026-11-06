# Sistema di gestione della qualità e del rischio · P1

Baseline di prodotto `40ee17e`. Edizione di lavoro del 6 novembre 2026. Perimetro Italia/UE. Autorità di rilascio e responsabili nominativi da assegnare dal fabbricante o dall'organizzazione titolare. Il fascicolo è impostato secondo l'approccio di ISO 13485, IEC 62304, ISO 14971, IEC 62366-1 e IEC 81001-5-1. Lo stato delle norme applicabili, eventuali edizioni armonizzate e la verifica per clausola appartengono alla revisione regolatoria.

- [Destinazione d'uso, utenti e confini](intended-use.md)
- [SAD e classi preliminari IEC 62304](software-architecture.md)
- [Gestione del rischio, FMECA e HAZOP](risk-management.md)
- [SRS, tracciabilità e piano V&V](verification-validation.md)
- [Procedure QMS e moduli operativi](procedures.md)
- [SOUP e componenti terzi](soup.md)
- [Qualificazione MDR/IVDR](../compliance/mdr-qualification.md)
- [Valutazione AI Act](../compliance/ai-act-assessment.md)
- [Clinical Validation Log](clinical-validation-log.md)
- [Evidenze di esecuzione P1](verification.md)

Il [registro versionato](register.json) contiene requisiti atomici, hazard, controlli osservati, riferimenti ai test e verifiche future. Per la revisione eseguire `python3 scripts/check_qms.py`. Per valutare il gate tecnico di rilascio reale usare `python3 scripts/check_qms.py --release`. Il gate resta rosso mentre esistono rischi bloccanti. Una revisione di questo fascicolo può essere approvata come artefatto di progetto anche con il rilascio clinico bloccato.

La revisione clinica, legale e regolatoria richiede professionisti abilitati e approvazioni reali. Nessuna valutazione simulata attribuisce lo stato di certificazione, conformità o autorizzazione clinica.
