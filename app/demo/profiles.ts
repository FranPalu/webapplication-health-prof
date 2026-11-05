export const profiles = {
  patient: {
    label: 'Paziente',
    title: 'Il mio percorso di cura',
    intro: 'Marta Riva · 58 anni · Caso sintetico DEMO-042',
    cards: [
      ['La tua équipe', 'Medicina e infermieristica', 'Elena Ferri, medico referente · Luca Serra, infermiere di percorso.'],
      ['Esami pubblicati', 'TC ed ecocardiogramma', 'La sintesi della TC è stata rivista dal radiologo. La cardiologa ha pubblicato una nota sulla qualità delle immagini eco.'],
      ['Le tue autorizzazioni', '1 richiesta in attesa', 'La condivisione con una seconda struttura attende una decisione.'],
    ],
  },
  professional: {
    label: 'Professionista',
    title: 'La mia attività clinica',
    intro: 'Équipe clinica · Documenti, condivisioni e consegne del turno.',
    cards: [
      ['Anagrafiche', '3 pazienti sintetici', 'L’accesso dipende dal rapporto di cura e dai permessi.'],
      ['Condivisioni', '2 attive', 'Le richieste nuove restano in attesa del consenso.'],
      ['Identità professionale', 'Verifica completata', 'Il profilo ha completato la verifica e usa il TOTP.'],
    ],
  },
  physician: {
    label: 'Medico',
    title: 'Cartella clinica e revisione esami',
    intro: 'Dott.ssa Elena Ferri · Medicina interna · Caso sintetico DEMO-042',
    cards: [
      ['Motivo del percorso', 'Dispnea da sforzo', 'Paziente sintetica di 58 anni. La cartella riunisce visita, TC torace ed ecocardiogramma.'],
      ['Radiologia', 'TC torace · Revisione completata', 'Il radiologo ha confrontato tre sezioni e aggiornato la sintesi.'],
      ['Cardiologia', 'Eco · Limite di qualità', 'La cardiologa ha documentato una vista parziale e lasciato la misura in sospeso.'],
    ],
  },
  nurse: {
    label: 'Infermiere',
    title: 'Consegne infermieristiche',
    intro: 'Luca Serra · Ambulatorio multidisciplinare · Turno del mattino',
    cards: [
      ['08:40 · Accoglienza', 'DEMO-042 presa in carico', 'Identità verificata. La paziente ha portato l’elenco dei farmaci in uso.'],
      ['10:15 · Consegna al medico', 'TC ed eco disponibili', 'Gli esami sono nel fascicolo. Da confermare con il medico la comunicazione alla paziente.'],
      ['12:00 · Passaggio di turno', 'Contatto in agenda', 'La collega del pomeriggio riceve la consegna e verifica la disponibilità per il controllo.'],
    ],
  },
  organization: {
    label: 'Amministrazione struttura',
    title: 'La mia organizzazione',
    intro: 'Gestisci i ruoli e le appartenenze della struttura.',
    cards: [
      ['Organizzazione', 'Centro Clarìa · 3 unità', 'Medicina interna, diagnostica per immagini e ambulatorio infermieristico.'],
      ['Team', '12 operatori', '5 medici, 5 infermieri e 2 amministrativi.'],
      ['Agenda e accettazione', '14 accessi programmati', '9 visite e 5 esami. Due appuntamenti attendono conferma.'],
    ],
  },
  platform: {
    label: 'Amministrazione piattaforma',
    title: 'Verifiche della piattaforma',
    intro: 'Verifiche professionali, richieste di accesso alla ricerca e audit.',
    cards: [
      ['Coda di verifica', '2 richieste in esame', 'Controllo manuale delle dichiarazioni professionali.'],
      ['Ricerca', '1 domanda in valutazione', 'La struttura di ricerca ha richiesto dati aggregati con finalità documentata.'],
      ['Audit', 'Ultima verifica alle 11:20', 'Esempio di consultazione del registro degli accessi e delle decisioni.'],
    ],
  },
  research: {
    label: 'Ricercatore',
    title: 'Spazio ricerca',
    intro: 'Giulia Neri · Unità di epidemiologia · Solo dati aggregati sintetici',
    cards: [
      ['Dataset', 'Osservazioni di laboratorio · 2025', 'Esempio di catalogo con anno, codice LOINC e conteggio di account distinti.'],
      ['Cella disponibile', '28 account distinti', 'Esempio di conteggio per emoglobina (LOINC 718-7).'],
      ['Cella soppressa', 'Sotto la soglia di 10', 'Le celle piccole vengono soppresse. Il profilo di ricerca mostra soltanto aggregati.'],
    ],
  },
  pharmacy: {
    label: 'Farmacia',
    title: 'Banco e prenotazioni',
    intro: 'Farmacia Clarìa Nord · Coda sintetica',
    cards: [
      ['Catalogo', '32 articoli disponibili', 'Aggiornamento delle disponibilità della mattina.'],
      ['Prenotazioni', '3 richieste da verificare', 'Una richiesta richiede il controllo della prescrizione collegata.'],
      ['Ritiro', '2 ordini pronti', 'Le notifiche di ritiro vengono inviate dopo la conferma.'],
    ],
  },
} as const;

export type Profile = keyof typeof profiles;
