"""
Motore di ragionamento — sostituisce Azure OpenAI + Power Automate "azione HTTP".
Chiama direttamente l'API Anthropic con il tool web_search lato server:
niente orchestrazione manuale del tool loop, il modello cerca da solo le fonti
ufficiali (KID, prospetto, Borsa Italiana, ecc.) durante la generazione.

Richiede la variabile d'ambiente ANTHROPIC_API_KEY.
"""
import os
import json
import re
import ssl
import certifi
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("FIN01_MODEL", "claude-sonnet-5")  # verifica il model id corrente su docs.anthropic.com
SYSTEM_PROMPT_PATH = os.path.join(os.path.dirname(__file__), "prompts", "fin01_system.md")
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

LOOKUP_SYSTEM_PROMPT = (
    "Sei un modulo di identificazione strumenti finanziari. Dato un ISIN o ticker, "
    "cerca sul web le fonti ufficiali (sito dell'emittente, Borsa Italiana, LSE, Xetra, SIX, "
    "altri listini) e identifica lo strumento. Presta attenzione: la valuta di negoziazione "
    "su una piazza può essere diversa dalla valuta base dello strumento o del sottostante "
    "(es. un ETP con sottostante in USD può negoziare in EUR su Borsa Italiana). Rispondi SOLO "
    "con un oggetto JSON valido, senza testo prima o dopo, senza blocchi markdown, con questa "
    "forma esatta:\n"
    '{"strumento": "nome completo", "emittente": "nome emittente", '
    '"valuta_base_strumento": "valuta base del prodotto/sottostante", '
    '"mercati": [{"nome": "es. Borsa Italiana", "valuta_negoziazione": "es. EUR"}], '
    '"trovato": true}\n'
    "Se non riesci a identificare con certezza lo strumento, rispondi con "
    '{"trovato": false, "motivo": "spiegazione breve"}.'
)


def lookup_strumento(identificativo: str) -> dict:
    """
    Dato un ISIN o ticker, interroga l'API con web_search per identificare
    nome strumento, emittente, valuta base ed elenco dei mercati di quotazione.
    Evita di chiedere all'utente dati che si possono derivare da soli.
    """
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY non impostata.")

    payload = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": LOOKUP_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Identifica: {identificativo}"}],
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    raw_text = "\n".join(text_blocks).strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        return {"trovato": False, "motivo": "Risposta non in formato JSON valido.", "raw": raw_text}


def _load_system_prompt() -> str:
    with open(SYSTEM_PROMPT_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _build_user_message(dati: dict) -> str:
    righe = [f"- {k}: {v}" for k, v in dati.items() if v not in (None, "")]
    return (
        "Analizza il seguente strumento secondo il protocollo FIN-01.\n\n"
        "Dati forniti dall'utente:\n" + "\n".join(righe) +
        "\n\nProduci le sezioni richieste in Markdown, secondo le istruzioni di sistema."
    )


DASHBOARD_RE = re.compile(
    r"<!--FIN01_DASHBOARD_START-->(.*?)<!--FIN01_DASHBOARD_END-->", re.DOTALL
)


def calcola_eas(componenti: dict) -> dict:
    """
    Calcolo deterministico dell'Evidence Adequacy Score a partire dalle cinque
    componenti fornite dal modello (0-100 ciascuna). Regola "a catena" (non media
    semplice): Attualità e Completezza documentale fungono da tetto sul risultato
    finale, perché un dato autorevole ma superato, o parziale, non deve poter
    "nascondersi" dietro una media alta delle altre componenti.

    Esempio che la regola deve gestire correttamente: Autorità=100, Completezza=100,
    Concordanza=100, Riproducibilità=100, Attualità=0 -> EAS finale vicino a 0,
    non vicino a 80 come darebbe una media semplice.
    """
    chiavi = ["autorita_fonti", "completezza_documentale", "attualita", "concordanza", "riproducibilita"]
    valori = [componenti.get(k) for k in chiavi]
    if any(v is None for v in valori):
        return {"valore": None, "gate": "non calcolabile", "motivo": "componenti EAS mancanti"}

    media = sum(valori) / len(valori)
    attualita = componenti["attualita"]
    completezza = componenti["completezza_documentale"]
    valore_finale = min(media, attualita, completezza)

    if valore_finale >= 80:
        gate = "verdetto pieno"
    elif valore_finale >= 60:
        gate = "verdetto condizionato"
    elif valore_finale >= 40:
        gate = "solo valutazione preliminare"
    else:
        gate = "nessun verdetto economico"

    return {"valore": round(valore_finale, 1), "gate": gate}


def calcola_composite(punteggi: dict) -> dict:
    """
    Calcola le tre dimensioni composite (Qualità esecutiva, Attrattività speculativa,
    Pericolosità) a partire dai punteggi elementari, con propagazione STRETTA
    dell'indeterminatezza: se anche un solo punteggio necessario è ND (None/null),
    l'intera dimensione composita diventa None ("non calcolabile"), invece di
    mediare solo le componenti disponibili — che darebbe un falso senso di
    completezza (vedi Caso C della VP-01: un'obbligazione convertibile con 3
    punteggi su 4 mancanti non deve risultare "buona" sulla base dell'unico
    disponibile).

    Nota: TMS è categoriale (Favorevole/Neutro/Sfavorevole), non un numero, quindi
    è escluso da questa formula per costruzione — non incluso nella media pesata
    di Attrattività speculativa, i cui pesi sono stati rinormalizzati di conseguenza
    (ASS e CSI sommano a 1.0 invece che a 0.8 come nella prima stesura su carta).
    """
    def media_pesata(componenti_pesi):
        valori_pesati = []
        for chiave, peso in componenti_pesi:
            v = punteggi.get(chiave)
            if v is None:
                return None
            valori_pesati.append(v * peso)
        return round(sum(valori_pesati), 1)

    return {
        "qualita_esecutiva": media_pesata([("IQS", 0.30), ("MSI", 0.25), ("LSI", 0.25), ("EQC", 0.20)]),
        "attrattivita_speculativa": media_pesata([("ASS", 0.5625), ("CSI", 0.4375)]),
        "pericolosita": media_pesata([("PDI", 0.60), ("RCI", 0.40)]),
    }


def calcola_fit_score(componenti: dict) -> dict:
    """
    Fit Score: coerenza tra strumento e tesi/orizzonte dichiarati dall'utente —
    non la qualità intrinseca dello strumento (quella è IQS). Dipende solo da
    due componenti oggettivamente valutabili dal modello sulla base dei dati
    dichiarati (orizzonte, strategia): non includono più esperienza o
    frequenza di monitoraggio, che sono giudizi dell'utente su se stesso, non
    fatti sulla compatibilità strumento/tesi. Quei due dati alimentano invece
    l'Indice di Difficoltà Gestionale (calcola_difficolta_gestionale), che
    NON influisce sul verdetto sullo strumento.
    """
    pesi = [("coerenza_orizzonte", 0.55), ("coerenza_strategia", 0.45)]
    valori = [componenti.get(k) for k, _ in pesi]
    if any(v is None for v in valori):
        return {"valore": None, "gate": "non calcolabile"}

    valore_finale = round(sum(componenti[k] * peso for k, peso in pesi), 1)
    if valore_finale >= 65:
        gate = "analisi ordinaria"
    elif valore_finale >= 40:
        gate = "procedere solo con modifiche"
    else:
        gate = "scartare o modificare strategia"
    return {"valore": valore_finale, "gate": gate}


MAPPA_ESPERIENZA = {
    "Nessuna/principiante": 20,
    "Intermedia": 55,
    "Esperta/professionale": 90,
}
MAPPA_FREQUENZA = {
    "Sporadicamente (mensile o meno)": 20,
    "Settimanale": 55,
    "Giornaliera/intraday": 90,
}


def calcola_difficolta_gestionale(dati: dict, dashboard: dict) -> dict:
    """
    Indice di Difficoltà Gestionale (IDG) — deliberatamente SEPARATO dal
    verdetto e dagli score sullo strumento. Non giudica se lo strumento è
    buono: segnala quanto potrebbe essere impegnativo da gestire per QUESTO
    utente specifico, dato ciò che ha dichiarato su esperienza e frequenza di
    monitoraggio rispetto alla pericolosità/complessità dello strumento (PDI).
    Un prodotto a leva 3x non diventa "peggiore" se l'utente è principiante:
    resta lo stesso strumento, con lo stesso PDI. Ma per un principiante sarà
    più difficile da gestire correttamente — è un'informazione sull'utente,
    non sullo strumento, e non deve mai retroagire sul verdetto operativo.
    """
    pdi = (dashboard.get("punteggi") or {}).get("PDI")
    esperienza = MAPPA_ESPERIENZA.get(dati.get("esperienza_investitore", ""))
    frequenza = MAPPA_FREQUENZA.get(dati.get("frequenza_monitoraggio", ""))
    if pdi is None or esperienza is None or frequenza is None:
        return {"valore": None, "livello": "non calcolabile"}

    capacita_utente = (esperienza + frequenza) / 2
    valore = round(max(0.0, min(100.0, pdi - capacita_utente)), 1)
    if valore <= 20:
        livello = "Bassa"
    elif valore <= 50:
        livello = "Media"
    else:
        livello = "Alta"
    return {"valore": valore, "livello": livello}


def applica_gates(dashboard: dict) -> dict:
    """
    Applica in sequenza il gate EAS e il gate Fit Score al verdetto del modello,
    in modo deterministico. Ogni gate può declassare ulteriormente il verdetto
    rispetto allo stato lasciato dal gate precedente; ogni intervento è
    registrato esplicitamente in dashboard["declassamenti"] (lista, mai un
    singolo evento silenzioso), con motivo leggibile.
    """
    dashboard["verdetto_modello"] = dashboard.get("verdetto")
    dashboard["declassamenti"] = []
    dashboard["composite"] = calcola_composite(dashboard.get("punteggi") or {})

    # Gate EAS: la base informativa è adeguata per un verdetto?
    eas = calcola_eas(dashboard.get("eas_componenti") or {})
    dashboard["eas"] = eas
    valore_eas = eas.get("valore")
    if valore_eas is not None:
        corrente = dashboard.get("verdetto")
        if valore_eas < 40 and corrente not in ("Scartare", "Approfondire prima di decidere"):
            dashboard["verdetto"] = "Approfondire prima di decidere"
            dashboard["declassamenti"].append({
                "gate": "EAS", "da": corrente, "a": dashboard["verdetto"],
                "motivo": f"EAS {valore_eas}/100: base informativa insufficiente per un verdetto pieno",
            })
        elif valore_eas < 60 and corrente == "Procedere":
            dashboard["verdetto"] = "Procedere solo se"
            dashboard["declassamenti"].append({
                "gate": "EAS", "da": corrente, "a": dashboard["verdetto"],
                "motivo": f"EAS {valore_eas}/100: verdetto ammesso solo con condizioni",
            })

    # Gate Fit Score: lo strumento è compatibile con orizzonte/strategia dell'utente?
    fit = calcola_fit_score(dashboard.get("fit_componenti") or {})
    dashboard["fit"] = fit
    valore_fit = fit.get("valore")
    if valore_fit is not None:
        corrente = dashboard.get("verdetto")
        if valore_fit < 40 and corrente not in ("Scartare", "Approfondire prima di decidere"):
            dashboard["verdetto"] = "Scartare"
            dashboard["declassamenti"].append({
                "gate": "Fit Score", "da": corrente, "a": dashboard["verdetto"],
                "motivo": f"Fit Score {valore_fit}/100: incompatibilità strutturale con orizzonte o strategia dichiarati",
            })
        elif valore_fit < 65 and corrente == "Procedere":
            dashboard["verdetto"] = "Procedere solo se"
            dashboard["declassamenti"].append({
                "gate": "Fit Score", "da": corrente, "a": dashboard["verdetto"],
                "motivo": f"Fit Score {valore_fit}/100: richiede condizioni per essere compatibile con l'utente",
            })

    dashboard["verdetto_declassato_da_gate"] = len(dashboard["declassamenti"]) > 0
    return dashboard


def extract_dashboard(report_md: str):
    """
    Estrae il blocco JSON di sintesi (verdetto, punteggi, importi) dal report,
    applica i gate deterministici (EAS, Fit Score), e restituisce
    (report_pulito, dashboard_dict_o_None). Se il blocco manca o non è JSON
    valido, ritorna il report invariato e None: l'app mostrerà comunque la
    relazione completa, solo senza il cruscotto.
    """
    match = DASHBOARD_RE.search(report_md)
    if not match:
        return report_md, None
    clean = (report_md[:match.start()] + report_md[match.end():]).strip()
    raw_json = match.group(1).strip()
    try:
        dashboard = json.loads(raw_json)
    except json.JSONDecodeError:
        return clean, None
    return clean, applica_gates(dashboard)


def _api_key() -> str:
    """
    Cerca la API key prima nella variabile d'ambiente (uso locale/CLI), poi nei
    secrets di Streamlit (necessario su Streamlit Cloud, dove i secrets non
    diventano automaticamente variabili d'ambiente del processo).
    """
    chiave = os.environ.get("ANTHROPIC_API_KEY")
    if chiave:
        return chiave
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        return None


def _call_api(system: str, user_content: str, max_tokens: int) -> dict:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY non impostata. Esporta la variabile d'ambiente "
            "(uso locale) o impostala nei secrets di Streamlit (Streamlit Cloud) "
            "prima di lanciare un'analisi reale."
        )
    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_content}],
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, context=SSL_CONTEXT) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    text_blocks = [b["text"] for b in data.get("content", []) if b.get("type") == "text"]
    search_calls = [b for b in data.get("content", []) if b.get("type") == "server_tool_use"]
    return {
        "report_md": "\n\n".join(text_blocks),
        "raw_response": data,
        "num_search_calls": len(search_calls),
        "stop_reason": data.get("stop_reason"),
    }


SINTESI_APPEND = (
    "\n\n## Istruzione per questa chiamata\n"
    "Per QUESTA chiamata scrivi SOLO la sezione 1 (Executive summary) e la sezione 2 "
    "(Verdetto operativo), seguite dal blocco dati per la schermata di sintesi. Non scrivere "
    "le sezioni dalla 3 alla 33: verranno prodotte in una chiamata successiva solo se richiesto. "
    "Esegui comunque tutte le ricerche sulle fonti ufficiali necessarie a fondare adeguatamente "
    "l'Executive summary e il Verdetto operativo — la sintesi deve essere solida quanto lo "
    "sarebbe se seguisse l'intera relazione, non una prima impressione approssimativa."
)

COMPLETA_APPEND_TEMPLATE = (
    "\n\n## Istruzione per questa chiamata\n"
    "Di seguito trovi l'Executive summary e il Verdetto operativo già prodotti in una chiamata "
    "precedente per questa stessa pratica. Scrivi ORA tutte le sezioni dalla 3 alla 33 incluse, "
    "mantenendo piena coerenza con quanto già scritto (stesso verdetto, stessi importi, stessa "
    "valutazione della tesi). Non ripetere le sezioni 1 e 2 né il blocco dati. Esegui tu stesso "
    "le ricerche necessarie sulle fonti ufficiali.\n\n"
    "--- Testo già prodotto (sezioni 1-2 e blocco dati) ---\n{sintesi}\n--- Fine testo già prodotto ---"
)


def run_sintesi(dati: dict, max_tokens: int = 16000) -> dict:
    """
    Prima chiamata, economica rispetto alla relazione completa: Executive summary +
    Verdetto operativo + cruscotto (incluse le 5 componenti EAS motivate). Fa comunque
    ricerca web reale per fondare il verdetto, ma non scrive le altre 31 sezioni.
    """
    system = _load_system_prompt() + SINTESI_APPEND
    return _call_api(system, _build_user_message(dati), max_tokens)


def run_completa(dati: dict, sintesi_md: str, max_tokens: int = 24000) -> dict:
    """
    Seconda chiamata, on-demand: le restanti 31 sezioni (3-33), coerenti con la sintesi
    già prodotta e mostrata all'utente.
    """
    system = _load_system_prompt() + COMPLETA_APPEND_TEMPLATE.format(sintesi=sintesi_md)
    return _call_api(system, _build_user_message(dati), max_tokens)


def run_analysis(dati: dict, max_tokens: int = 28000) -> dict:
    """
    Analisi FIN-01 completa in un'unica chiamata (usata dalla CLI). Ritorna un dict:
      { "report_md": str, "raw_response": dict, "num_search_calls": int, "stop_reason": str }
    Solleva RuntimeError se manca la API key o la chiamata fallisce.
    """
    return _call_api(_load_system_prompt(), _build_user_message(dati), max_tokens)
