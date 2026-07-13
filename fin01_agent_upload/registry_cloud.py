"""
Registro pratiche FIN-01 — backend Google Sheet, per la persistenza su
Streamlit Cloud (il filesystem locale lì è "usa e getta": si azzera ad ogni
riavvio del container). Stessa identica interfaccia di registry.py:
create_pratica, update_pratica, delete_pratica, get_pratica, list_pratiche.

Richiede in st.secrets:
  gsheet_id = "id_del_foglio_google"   (dalla URL: .../d/QUESTO_ID/edit)
  [gcp_service_account]
  ... contenuto del file JSON del service account Google, come tabella TOML ...

Il foglio deve essere condiviso in modifica con l'email del service account
(campo "client_email" nel JSON delle credenziali).
"""
import json
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
WORKSHEET_NAME = "pratiche"

STATI_VALIDI = [
    "Nuova", "Dati incompleti", "In raccolta fonti", "In analisi",
    "In revisione EZ SUPER", "Sintesi prodotta", "In generazione relazione completa",
    "Relazione completa prodotta", "Bozza prodotta", "In attesa di validazione",
    "Conclusa", "Archiviata", "Da monitorare",
]

# Campi che contengono strutture (dict/list) e vanno serializzati come JSON in cella
CAMPI_JSON = ["dati_iniziali", "score", "dashboard", "note"]
COLONNE = [
    "id", "data_apertura", "stato", "dati_iniziali", "decisione_finale",
    "score", "dashboard", "sintesi_md", "relazione_md", "note",
]


def _client():
    import streamlit as st
    info = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc


def _worksheet():
    import streamlit as st
    gc = _client()
    sh = gc.open_by_key(st.secrets["gsheet_id"])
    try:
        return sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=len(COLONNE))
        ws.append_row(COLONNE)
        return ws


def _row_to_record(row: dict) -> dict:
    record = dict(row)
    for campo in CAMPI_JSON:
        valore = record.get(campo)
        if valore:
            try:
                record[campo] = json.loads(valore)
            except json.JSONDecodeError:
                record[campo] = None
        else:
            record[campo] = None
    for campo in ["sintesi_md", "relazione_md", "decisione_finale"]:
        if record.get(campo) == "":
            record[campo] = None
    return record


def _record_to_row(record: dict) -> dict:
    row = dict(record)
    for campo in CAMPI_JSON:
        if row.get(campo) is not None:
            row[campo] = json.dumps(row[campo], ensure_ascii=False)
        else:
            row[campo] = ""
    for campo in ["sintesi_md", "relazione_md", "decisione_finale"]:
        if row.get(campo) is None:
            row[campo] = ""
    return {k: row.get(k, "") for k in COLONNE}


def _next_id() -> str:
    ws = _worksheet()
    records = ws.get_all_records(expected_headers=COLONNE)
    today = datetime.now().strftime("%Y%m%d")
    seq = sum(1 for r in records if str(r.get("id", "")).startswith(f"FIN01-{today}")) + 1
    return f"FIN01-{today}-{seq:03d}"


def create_pratica(dati: dict) -> dict:
    record = {
        "id": _next_id(),
        "data_apertura": datetime.now(timezone.utc).isoformat(),
        "stato": "Nuova",
        "dati_iniziali": dati,
        "decisione_finale": None,
        "score": {},
        "dashboard": None,
        "sintesi_md": None,
        "relazione_md": None,
        "note": [],
    }
    if not all(dati.get(k) for k in ("capitale_disponibile", "patrimonio_indicativo", "perdita_massima_accettabile")):
        record["stato"] = "Dati incompleti"

    ws = _worksheet()
    riga = _record_to_row(record)
    ws.append_row([riga[c] for c in COLONNE])
    return record


def _trova_riga_indice(ws, pratica_id: str) -> int:
    """Ritorna l'indice di riga (1-based, header incluso) o solleva KeyError."""
    celle = ws.col_values(1)  # colonna "id"
    for i, valore in enumerate(celle):
        if valore == pratica_id:
            return i + 1
    raise KeyError(f"Pratica {pratica_id} non trovata")


def update_pratica(pratica_id: str, **fields):
    ws = _worksheet()
    idx = _trova_riga_indice(ws, pratica_id)
    valori_attuali = ws.row_values(idx)
    record_attuale = _row_to_record(dict(zip(COLONNE, valori_attuali + [""] * (len(COLONNE) - len(valori_attuali)))))
    record_attuale.update(fields)
    riga = _record_to_row(record_attuale)
    ws.update(f"A{idx}:{chr(ord('A') + len(COLONNE) - 1)}{idx}", [[riga[c] for c in COLONNE]])
    return record_attuale


def delete_pratica(pratica_id: str) -> bool:
    ws = _worksheet()
    try:
        idx = _trova_riga_indice(ws, pratica_id)
    except KeyError:
        return False
    ws.delete_rows(idx)
    return True


def get_pratica(pratica_id: str) -> dict:
    ws = _worksheet()
    idx = _trova_riga_indice(ws, pratica_id)
    valori = ws.row_values(idx)
    return _row_to_record(dict(zip(COLONNE, valori + [""] * (len(COLONNE) - len(valori)))))


def list_pratiche(stato: str = None) -> list:
    ws = _worksheet()
    tutte = ws.get_all_records(expected_headers=COLONNE)
    records = [_row_to_record(r) for r in tutte]
    if stato:
        return [r for r in records if r["stato"] == stato]
    return records
