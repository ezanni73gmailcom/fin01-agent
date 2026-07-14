# Agente Finanziario EIAOS — FIN-01

## Uso in locale (come finora)
```
cd fin01_agent
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app.py
```
Senza secrets configurati, l'app usa automaticamente il registro JSON locale
(registry.py) — il comportamento è identico a prima.

## Novità di questa versione (BP-01, Fase 1)
- **EAS a catena**: calcolato in Python (non dal modello), attualità e
  completezza fanno da tetto, non solo da media.
- **Gate EAS deterministico**: verdetto declassato automaticamente se l'EAS
  è insufficiente, sempre dichiarato esplicitamente.
- **TMS categoriale**: Favorevole/Neutro/Sfavorevole, non più un numero.
- **Regola della Non Sostituzione**: punteggi non reperibili sono `null`
  (ND), mai stimati.
- **Persistenza portabile**: il registro ora salva il testo delle relazioni
  direttamente (non più percorsi di file), così può girare sia su file
  locale sia su Google Sheet senza cambiare il resto del codice. Il .docx
  viene sempre generato al volo al momento del download, mai salvato
  permanentemente.

---

## Come mettere l'agente online (Streamlit Community Cloud + Google Sheet)

### Passo 1 — Crea il Google Sheet che farà da registro
1. Vai su [sheets.google.com](https://sheets.google.com), crea un foglio vuoto
   (qualsiasi nome, es. "FIN01 Registro").
2. Copia l'ID dall'URL: `https://docs.google.com/spreadsheets/d/QUESTO_ID/edit`

### Passo 2 — Crea un service account Google
1. Vai su [console.cloud.google.com](https://console.cloud.google.com), crea
   un progetto (o usane uno esistente).
2. Abilita le API "Google Sheets API" e "Google Drive API"
   (menu "API e servizi" → "Libreria").
3. Vai su "Credenziali" → "Crea credenziali" → "Account di servizio".
   Dagli un nome qualsiasi, nessun ruolo particolare necessario.
4. Apri l'account di servizio creato → scheda "Chiavi" → "Aggiungi chiave" →
   "Crea nuova chiave" → formato JSON. Si scarica un file .json: conservalo,
   non va mai messo su GitHub.
5. Apri il file JSON, copia il valore di `client_email`.
6. Torna sul Google Sheet creato al Passo 1 → "Condividi" → incolla quella
   email → dagli ruolo "Editor" → condividi.

### Passo 3 — Metti il codice su GitHub
Il repository è già inizializzato in locale con un primo commit. Serve solo
crearne uno vuoto su GitHub e collegarlo:
```
cd fin01_agent
# crea un repository PRIVATO vuoto su github.com (senza README/licenza),
# poi:
git remote add origin https://github.com/TUO-USERNAME/fin01-agent.git
git branch -M main
git push -u origin main
```
Il file .gitignore esclude già venv/, i dati locali e i secrets: non
finiscono mai su GitHub.

### Passo 4 — Deploy su Streamlit Community Cloud
1. Vai su [share.streamlit.io](https://share.streamlit.io), accedi con
   GitHub, "New app", seleziona il repository appena creato, file
   principale `app.py`.
2. Prima di avviare, apri "Advanced settings" → "Secrets" e incolla:
```toml
ANTHROPIC_API_KEY = "sk-ant-...(la tua key reale)..."
gsheet_id = "...(l'ID del foglio del Passo 1)..."

[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "...@....iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
universe_domain = "googleapis.com"
```
   (i valori di `[gcp_service_account]` si copiano 1:1 dal file JSON
   scaricato al Passo 2 — vedi `.streamlit/secrets.toml.example` nel
   repository come guida al formato esatto)
3. Clicca "Deploy". La prima analisi creerà da sola il foglio di lavoro
   "pratiche" dentro il Google Sheet, con le intestazioni corrette.

### Passo 5 — Limita l'accesso (importante: senza questo è pubblico)
Nelle impostazioni dell'app su Streamlit Cloud → "Sharing" → imposta l'app
come privata e aggiungi solo gli account Google (email) delle persone
autorizzate ad aprirla. Senza questo passaggio chiunque trovi l'URL può
usare la tua API key a tue spese.

---

## Uso da riga di comando (CLI, sempre locale)
```
python cli.py nuova --file la_tua_pratica.json
python cli.py analizza FIN01-...
python cli.py lista
```
La CLI usa sempre il registro JSON locale, indipendentemente dai secrets:
è pensata per uso e test in locale, non per il deploy condiviso.

## Roadmap (BP-01, fasi successive non ancora implementate)
- Fase 2 — propagazione dell'indeterminatezza nelle dimensioni composite,
  rubriche esplicite per PDI/RCI/EQC.
- Fase 3 — Fit Score multidimensionale, astensione con causa esplicita (A-E).
- Fase 4 — classificazione S/T/Y/O/H multi-pesata degli strumenti.

## Note tecniche
- `registry.py` = backend JSON locale. `registry_cloud.py` = backend Google
  Sheet, stessa interfaccia identica, selezionato automaticamente da `app.py`
  in base alla presenza dei secrets `gsheet_id` + `gcp_service_account`.
- Il model id in agent.py (FIN01_MODEL) va verificato su
  docs.anthropic.com/en/docs/about-claude/models prima del primo uso reale.
- `agent.calcola_eas()` e `agent.applica_gate_eas()` sono testati con casi
  limite (vedi commenti nel codice) prima di ogni consegna.

<!-- Aggiornamenti da qui in poi possono essere applicati automaticamente da Claude via token GitHub -->
