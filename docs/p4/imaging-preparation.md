# Preparazione imaging per il solo collaudo sintetico

Il runner di inferenza usa esclusivamente uno stato tensoriale verificato e `weights_only=True`. Il checkpoint originale upstream è un modello serializzato legacy, non leggibile dal loader restrittivo. Non addestriamo o modifichiamo pesi.

Salvare il checkpoint upstream v1 come `.analysis-models/xray.pt`, SHA-256 `56524913dd16a906422e8d8b66a7a5c46be1d82eb7ac012d8103776f1aa68899`. Verificarne provenienza e licenza prima di distribuirlo; i diritti dei pesi/dataset restano aperti. [Repository upstream](https://github.com/mlmed/torchxrayvision).

```sh
mkdir -p .analysis-models/converted
docker compose --env-file .env.dev --profile imaging-prepare build imaging-convert
docker compose --env-file .env.dev --profile imaging-prepare run --rm --no-deps imaging-convert
```

La conversione ha rete disabilitata, nessun database, nessuna variabile `.env.dev` nel container, radice in sola lettura e sola directory `converted` scrivibile. Se il filesystem del deployment nega la scrittura all'UID 65534, assegnare soltanto quella directory all'UID del container; non aprire permessi sulla cartella dei segreti o sull'intero archivio.

Il convertitore confronta l'hash **prima** della deserializzazione, accetta esattamente l'architettura prevista, rifiuta postprocessing non previsto, salva soltanto tensori e confronta il forward con una fixture zero. Il loader legacy è un'eccezione SAST **B614** puntuale, motivata in `convert_legacy.py` e verificata da `test_conversion.py`. Non è un'eccezione per l'inferenza o per file degli utenti. Restano la fiducia nel checkpoint upstream e nel runtime di quarantena; il rilascio clinico è bloccato. Nessuna soppressione globale di B614.

Con il runtime fissato in questo Dockerfile il file `converted/xray-state.pt` deve avere SHA-256 `9557a4685000af1490869d2abb19be6a651beb57feff6c1da8cf88bef28eb068`. Un output diverso viene rifiutato dal runner e richiede riesame del processo, non aggiornamento automatico dell'hash atteso. La prima conversione è stata confrontata anche con lo smoke sintetico pre-conversione; i 18 punteggi coincidono.

```sh
.venv/bin/python scripts/analysis-imaging-fixture.py
docker compose --env-file .env.dev --profile imaging-test build imaging-smoke
docker compose --env-file .env.dev --profile imaging-test run --rm --no-deps imaging-smoke
python3 -m unittest discover -s infra/imaging -p test_contract.py
docker run --rm --network none --read-only --tmpfs /tmp:size=32m,mode=1777 --entrypoint python health-collaboration-imaging-smoke -m unittest test_conversion
```

I risultati ripetibili non sono accuratezza clinica. Il runner dichiara confidenza e localizzazione nulle, nessun rilevatore OOD clinico e `clinical_usable=false`. **DA VALIDARE da professionista abilitato**: CV-P4-05 nel Clinical Validation Log.
