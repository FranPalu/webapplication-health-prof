# SOUP · Inventario di componenti terzi

Lo [snapshot leggibile come testo](soup.tsv) registra ecosistema, componente/versione, licenza dichiarata, fonte, ambito e rischio. Comprende le **874** voci npm del lockfile, le **66** dipendenze Python del backend, **3** versioni dichiarate nel Dockerfile imaging, **30** distribuzioni osservate nell'immagine imaging locale e **18** voci per modelli, strumenti, immagini base e servizi. Le righe dichiarate e quelle osservate dell'imaging sono intenzionalmente distinte. Per esempio `torch==2.7.1` è la versione richiesta e `2.7.1+cpu` la build osservata. I rischi sono preliminari e orientano il controllo in base all'ambito.

| Sorgente | Metodo e limite |
| --- | --- |
| npm | Identità e versione da `pnpm-lock.yaml`. Licenze dai manifest installati o dal metadata del registro per la versione esatta. Il grafo di produzione osservato si riferisce alla piattaforma di verifica. I pacchetti opzionali vanno rivalutati per la piattaforma di release |
| Python | Versioni da `backend/requirements.txt` e Dockerfile imaging. Metadata delle distribuzioni installate o di PyPI. Licenze dichiarate o classificatori upstream, da riesaminare per obblighi di distribuzione |
| Imaging | Inventario locale via `importlib.metadata` nel container di collaudo. La risoluzione transitiva di questo Dockerfile non è interamente congelata. Non assumere parità tra ricostruzioni |
| Immagini, OS e servizi | Tag/digest dichiarati nei Dockerfile e Compose, licenza del componente principale. P10 deve produrre SBOM per digest/architettura e rilevare versioni, licenze e anomalie dei pacchetti OS realmente distribuiti |
| Modelli | Versione e SHA-256 configurati. I diritti sui pesi di imaging e i dataset di training richiedono verifica indipendente prima di abilitazione o redistribuzione. [Registro tecnico dei modelli](../05-supervised-analysis.md) |

Lo scan P1 dell’immagine di collaudo ha trovato advisory aperti su PyTorch, pip e setuptools. Il profilo rimane separato dal prodotto e il riuso richiede aggiornamento o rimozione delle dipendenze, inventario per digest e nuova prova del modello in P4. [Esiti SCA](verification.md)

Per ogni aggiornamento riesaminare vulnerabilità, anomalie, compatibilità, licenza e controlli a valle. Rinnovare lo snapshot con `pnpm licenses list --json` e `--prod`, metadata Python e registro pubblico per identità mancanti, metadata dell'immagine imaging ed evidenze dei fornitori. Eseguire `python3 scripts/check_qms.py` per verificare che lockfile npm e pin Python siano coperti. L'inventario di progetto e la verifica licenze non equivalgono a una SBOM di rilascio.

Fonti delle licenze dei modelli. [Tesseract tessdata_fast](https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0) · [Qwen GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF) · [TorchXRayVision](https://github.com/mlmed/torchxrayvision).
