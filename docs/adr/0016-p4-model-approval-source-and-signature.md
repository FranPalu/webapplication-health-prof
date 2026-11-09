# ADR 0016 · Fonte verificabile, approvazione per impronta e firma esterna

Stato: accettato per collaudo sintetico; nessuna approvazione clinica reale.

L'approvazione del manifest da parte di un professionista verificato amministratore del tenant è un evento append-only. L'impronta comprende schede, prompt e codice dell'estrattore. Ogni nuova decisione invalida i job della decisione precedente, anche se si riabilita successivamente l'esecuzione. Un lock sull'organizzazione serializza decisioni, avvio, commit della bozza e pubblicazione. La revoca della relazione è ricontrollata dal worker. Le opinioni già scaricate non possono essere richiamate.

Pagina e riga non bastano per verificare un numero: Poppler e TSV Tesseract conservano testo e riquadro, con sistema di coordinate esplicito. La confidenza della riga OCR è il minimo delle parole, non una probabilità clinica. Le righe incerte e le mappature LOINC dedotte richiedono conferma esplicita, perché etichetta e unità non identificano campione/metodo. UCUM usa `umol/L`; nessuna conversione implicita. Estrazione troncata o vuota impedisce l'accettazione e la modifica, consentendo il rifiuto motivato.

Il LLM seleziona soltanto ID: i valori e il linguaggio del riepilogo sono costruiti dal server. Non riceve testo libero, numeri clinici o identificativi. La selezione può comunque omettere una riga: il revisore deve confrontare l'intera fonte.

L'attestazione interna non consente più la pubblicazione. Un manifest JSON canonico lega testo finale, autore, data e hash della fonte; la sua SHA-256 è il digest da verificare. Un adapter del deployment deve verificare firma, catena di fiducia, identità e contenuto CAdES o PAdES. Il provider non è incluso: assenza restituisce 503, pubblicazione senza prova restituisce 409. Prima della firma si ricontrollano identificativo registrato e data di nascita da fonte indipendente. Nei test il verificatore è un double dichiarato, non una firma legale.

Imaging rimane uno smoke test isolato senza rete, database o endpoint clinico. La verifica dei metadati non è un rilevatore OOD clinico. Non mostriamo punteggi grezzi come confidenza calibrata; diritti dei pesi, localizzazione e validazione restano aperti. La remediation delle dipendenze non rimuove questi limiti. L’inferenza usa soltanto stato tensoriale con loader restrittivo. La conversione dell’unico modello legacy verificato avviene in quarantena separata, con eccezione B614 puntuale, nessun input paziente e prova di equivalenza; vedere la procedura P4 di preparazione imaging.

Revisione clinica simulata: patologo clinico, radiologo, internista e risk manager. Rischi principali: unità/campione errati, omissione del LLM, falsa rassicurazione e firma del paziente sbagliato. **DA VALIDARE da professionista abilitato** nel [Clinical Validation Log](../qms/clinical-validation-log.md).
