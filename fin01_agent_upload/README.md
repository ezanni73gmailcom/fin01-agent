# Agente Finanziario EIAOS — FIN-01

## Uso in locale
```
cd fin01_agent
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```

## BP-01 — completo (Fasi 1-4)

**Fase 1 — Stabilizzazione dei fondamenti**
- EAS (Evidence Adequacy Score) a catena: attualità e completezza fanno da
  tetto, non solo da media. Gate deterministico: EAS insufficiente declassa
  automaticamente il verdetto.
- TMS (timing) categoriale (Favorevole/Neutro/Sfavorevole), non un numero.

**Fase 2 — Gestione dell'incertezza**
- EQC (qualità emittente/controparte), nuovo punteggio con rubrica esplicita.
- Rubriche esplicite a fasce per PDI, RCI, EQC.
- Tre dimensioni composite (Qualità esecutiva, Attrattività speculativa,
  Pericolosità) con propagazione stretta: un solo ND in una dimensione la
  rende "non calcolabile" per intero.

**Fase 3 — Interazione con l'utente**
- Fit Score (coerenza orizzonte/strategia dichiarati vs strumento) — gate
  deterministico separato da EAS.
- Indice di Difficoltà Gestionale: separato dal verdetto, mai lo influenza —
  segnala solo quanto lo strumento potrebbe essere impegnativo da gestire
  per l'utente specifico, in base a esperienza e frequenza di monitoraggio
  dichiarate (ora campi obbligatori).
- Causa esplicita (A-E) per ogni dato non reperito, inclusa la causa E
  ("richiede accesso a banche dati professionali").

**Fase 4 — Rifattorizzazione architetturale**
- Classificazione S/T/Y/O/H multi-pesata (Strategica/Tattica/Yield/
  Opzionale/Hedging) prima di ogni punteggio.
- "Attrattività speculativa" diventa "Non applicabile" (non un numero
  fittizio) quando il peso combinato Tattica+Opzionale è basso — es. un ETF
  strategico non ha una tesi tattica da misurare.
- TMS mostrato come "non applicabile" per gli stessi strumenti.

Tutte le fasi sono state testate contro i tre casi reali della VP-01
(ETP a leva, ETF passivo, obbligazione convertibile) prima della consegna.

## Uso (interfaccia web)
```
streamlit run app.py
```
1. Identifica lo strumento (ISIN/ticker, ricerca automatica del mercato).
2. Tesi, orizzonte, esperienza e frequenza di monitoraggio (tutti obbligatori).
3. Dati patrimoniali.
4. "Crea pratica ed esegui analisi FIN-01" — prima chiamata: sintesi,
   verdetto, cruscotto completo (EAS, Fit, classificazione, composite, IDG).
5. "Genera relazione completa" solo se serve la due diligence estesa
   (33 sezioni).

## Uso (CLI, locale, senza cruscotto)
```
python cli.py nuova --file la_tua_pratica.json
python cli.py analizza FIN01-...
python cli.py lista
```

## Note tecniche
- `registry.py` = backend JSON locale. `registry_cloud.py` = backend Google
  Sheet (stessa interfaccia), selezionato automaticamente da `app.py` in
  base ai secrets `gsheet_id` + `gcp_service_account`.
- Tutti i calcoli deterministici (EAS, Fit, composite, classificazione, IDG)
  sono in `agent.py`, mai lasciati al modello — il modello fornisce solo i
  punteggi elementari motivati, il codice fa l'aritmetica.
- Il model id in agent.py (FIN01_MODEL) va verificato su
  docs.anthropic.com/en/docs/about-claude/models prima del primo uso reale.
