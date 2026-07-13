"""
Registro pratiche FIN-01 — sostituisce SharePoint List.
Un semplice JSON file, una riga = una pratica. Facilmente migrabile in futuro
verso Google Sheet o Airtable senza cambiare il resto dell'agente:
basta riscrivere questo modulo mantenendo la stessa interfaccia.
"""
import json
import os
from datetime import datetime, timezone

REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "data", "registry.json")

STATI_VALIDI = [
    "Nuova", "Dati incompleti", "In raccolta fonti", "In analisi",
    "In revisione EZ SUPER", "Sintesi prodotta", "In generazione relazione completa",
    "Relazione completa prodotta", "Bozza prodotta", "In attesa di validazione",
    "Conclusa", "Archiviata", "Da monitorare",
]


def _load():
    if not os.path.exists(REGISTRY_PATH):
        return []
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(records):
    os.makedirs(os.path.dirname(REGISTRY_PATH), exist_ok=True)
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)


def _next_id():
    records = _load()
    today = datetime.now().strftime("%Y%m%d")
    seq = sum(1 for r in records if r["id"].startswith(f"FIN01-{today}")) + 1
    return f"FIN01-{today}-{seq:03d}"


def create_pratica(dati: dict) -> dict:
    """
    dati atteso (chiavi minime):
      strumento, isin_o_ticker, mercato, valuta, tesi_speculativa, orizzonte,
      capitale_disponibile, patrimonio_indicativo, perdita_massima_accettabile
    Le chiavi patrimoniali possono mancare: la pratica viene comunque creata
    con stato "Dati incompleti" e l'agente lo segnalerà nella Fase 0.
    """
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
    records = _load()
    records.append(record)
    _save(records)
    return record


def update_pratica(pratica_id: str, **fields):
    records = _load()
    for r in records:
        if r["id"] == pratica_id:
            r.update(fields)
            _save(records)
            return r
    raise KeyError(f"Pratica {pratica_id} non trovata")


def delete_pratica(pratica_id: str) -> bool:
    records = _load()
    nuovi = [r for r in records if r["id"] != pratica_id]
    if len(nuovi) == len(records):
        return False
    _save(nuovi)
    return True


def get_pratica(pratica_id: str) -> dict:
    for r in _load():
        if r["id"] == pratica_id:
            return r
    raise KeyError(f"Pratica {pratica_id} non trovata")


def list_pratiche(stato: str = None) -> list:
    records = _load()
    if stato:
        return [r for r in records if r["stato"] == stato]
    return records
