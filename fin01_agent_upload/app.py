"""
Interfaccia web dell'Agente Finanziario EIAOS — sostituisce l'uso del terminale.
Avvio: streamlit run app.py  (si apre da solo nel browser)
"""
import os
import tempfile
import streamlit as st
import plotly.graph_objects as go

import agent
import report_docx
import validation

# Selezione automatica del backend: Google Sheet se configurato nei secrets
# (necessario su Streamlit Cloud, dove il filesystem locale è "usa e getta"),
# altrimenti JSON locale (uso su una macchina propria, es. venv locale).
try:
    _USA_CLOUD = "gsheet_id" in st.secrets and "gcp_service_account" in st.secrets
except Exception:
    _USA_CLOUD = False

if _USA_CLOUD:
    import registry_cloud as registry
else:
    import registry

st.set_page_config(page_title="Agente Finanziario EIAOS — FIN-01", layout="centered")

ORIZZONTI = [
    "Intraday / pochi giorni",
    "1-4 settimane",
    "1-3 mesi",
    "3-6 mesi",
    "6-12 mesi",
    "Oltre 12 mesi",
    "Altro (specifica sotto)",
]

VERDETTO_COLORI = {
    "Procedere": "#1a9c5a",
    "Procedere solo se": "#4caf9e",
    "Attendere": "#e8a33d",
    "Approfondire prima di decidere": "#5b7fbd",
    "Scartare salvo evento specifico": "#d97b4f",
    "Scartare": "#c0392b",
}

import re as _re


def _parse_importo(testo: str) -> float:
    if not testo:
        return 0.0
    m = _re.search(r"[\d.,]+", str(testo))
    if not m:
        return 0.0
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return 0.0


def _docx_bytes(pratica: dict):
    """Genera il .docx al volo dal testo salvato nel registro (mai da un percorso
    file persistente, che su Streamlit Cloud non sopravviverebbe a un riavvio)."""
    relazione_md = pratica.get("relazione_md") or pratica.get("sintesi_md")
    if not relazione_md:
        return None
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        report_docx.build_docx(relazione_md, pratica, tmp_path)
        with open(tmp_path, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp_path)


for key, default in [
    ("lookup_done", False), ("lookup_result", None), ("identificativo", ""),
    ("pratica_attiva", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _render_verdict_badge(dashboard: dict):
    verdetto = dashboard.get("verdetto", "n/d")
    colore = VERDETTO_COLORI.get(verdetto, "#5b7fbd")
    confidenza = dashboard.get("confidenza", "n/d")
    sintesi = dashboard.get("sintesi", "")
    eas = dashboard.get("eas") or {}
    eas_valore = eas.get("valore")
    eas_gate = eas.get("gate", "n/d")

    eas_riga = ""
    if eas_valore is not None:
        eas_riga = f"&nbsp;•&nbsp; EAS: {eas_valore}/100 ({eas_gate})"
    else:
        eas_riga = "&nbsp;•&nbsp; EAS: non calcolabile (componenti mancanti)"

    st.markdown(
        f"""
        <div style="border-left: 6px solid {colore}; background: rgba(255,255,255,0.04);
                    padding: 18px 22px; border-radius: 8px; margin-bottom: 8px;">
            <div style="font-size: 0.8rem; letter-spacing: 0.05em; opacity: 0.7; text-transform: uppercase;">
                Verdetto operativo &nbsp;•&nbsp; Confidenza: {confidenza}{eas_riga}
            </div>
            <div style="font-size: 1.6rem; font-weight: 700; color: {colore}; margin: 4px 0 8px 0;">
                {verdetto}
            </div>
            <div style="font-size: 0.95rem; opacity: 0.9;">{sintesi}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if dashboard.get("verdetto_declassato_da_gate"):
        st.info(
            f"Il verdetto del modello era **{dashboard.get('verdetto_modello')}**: è stato declassato "
            f"automaticamente a **{verdetto}** perché l'EAS ({eas_valore}/100) non è sufficiente a "
            f"sostenerlo. Questo intervento è deterministico, non un'opinione del modello."
        )


LABEL_PUNTEGGI = {
    "IQS": "Qualità dell'opportunità",
    "ASS": "Asimmetria rischio/rendimento",
    "CSI": "Forza del catalizzatore",
    "MSI": "Struttura di mercato",
    "LSI": "Sicurezza della liquidità",
    "RCI": "Concentrazione del rischio",
    "PDI": "Pericolosità del prodotto",
}


def _render_radar(punteggi: dict):
    chiavi_disponibili = [k for k, v in punteggi.items() if v is not None]
    chiavi_nd = [k for k, v in punteggi.items() if v is None]

    if chiavi_nd:
        etichette_nd = ", ".join(LABEL_PUNTEGGI.get(k, k) for k in chiavi_nd)
        st.caption(f"Non determinabile (dato non reperito, nessuna stima sostitutiva): {etichette_nd}")

    if not chiavi_disponibili:
        st.caption("Nessun punteggio calcolabile con i dati reperiti.")
        return

    labels = [LABEL_PUNTEGGI.get(k, k) for k in chiavi_disponibili]
    valori = [punteggi[k] for k in chiavi_disponibili]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=valori + [valori[0]], theta=labels + [labels[0]], fill="toself", name="Punteggi"))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        showlegend=False,
        margin=dict(l=30, r=30, t=20, b=20),
        height=380,
    )
    st.plotly_chart(fig, width="stretch")


TMS_COLORI = {"Favorevole": "#1a9c5a", "Neutro": "#8a8a8a", "Sfavorevole": "#c0392b"}


def _render_tms(tms: str):
    colore = TMS_COLORI.get(tms, "#8a8a8a")
    st.markdown(
        f"""<span style="background: {colore}22; color: {colore}; padding: 4px 12px;
        border-radius: 999px; font-size: 0.85rem; font-weight: 600;">Timing: {tms or 'n/d'}</span>""",
        unsafe_allow_html=True,
    )


def _render_importi(importi: dict, capitale_utente: float):
    valuta = importi.get("valuta", "")
    etichette = ["Minimo sensato", "Massimo prudente", "Massimo aggressivo", "Sconsigliato oltre"]
    chiavi = ["minimo_sensato", "massimo_prudente", "massimo_aggressivo", "sconsigliato_oltre"]
    valori = [importi.get(k) or 0 for k in chiavi]
    colori_barre = ["#5b7fbd", "#4caf9e", "#e8a33d", "#c0392b"]

    fig = go.Figure(go.Bar(x=valori, y=etichette, orientation="h", marker_color=colori_barre))
    if capitale_utente:
        fig.add_vline(x=capitale_utente, line_dash="dash", line_color="white",
                      annotation_text=f"Tuo capitale: {capitale_utente:g} {valuta}", annotation_position="top")
    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10), height=280,
        xaxis_title=f"Importo ({valuta})",
    )
    st.plotly_chart(fig, width="stretch")


def render_dashboard(dashboard: dict, capitale_utente: float = 0):
    st.subheader("Schermata di sintesi")
    _render_verdict_badge(dashboard)
    _render_tms(dashboard.get("tms"))
    st.write("")
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Profilo di rischio/opportunità (0-100)")
        _render_radar(dashboard.get("punteggi", {}))
    with col2:
        st.caption("Dimensionamento della posizione")
        _render_importi(dashboard.get("importi", {}), capitale_utente)
    if dashboard.get("orizzonte_coerente_con_strumento") is False:
        st.warning("L'orizzonte temporale dichiarato non è coerente con la natura dello strumento.")


# ---------- Sidebar: registro pratiche ----------
with st.sidebar:
    st.header("Registro pratiche")
    pratiche = sorted(registry.list_pratiche(), key=lambda r: r["data_apertura"], reverse=True)
    if not pratiche:
        st.caption("Nessuna pratica ancora creata.")
    for p in pratiche:
        dati = p["dati_iniziali"]
        isin = dati.get("isin_o_ticker", "?")
        descr = (dati.get("strumento", "?") or "?")[:45]
        with st.expander(f"{isin} — {descr}"):
            st.caption(f"ID pratica: {p['id']}")
            st.write(f"**Descrizione completa:** {dati.get('strumento', '?')}")
            st.write(f"**Stato:** {p['stato']}")
            if p.get("dashboard"):
                v = p["dashboard"].get("verdetto", "")
                colore = VERDETTO_COLORI.get(v, "#5b7fbd")
                st.markdown(f"<span style='color:{colore}; font-weight:600;'>{v}</span>", unsafe_allow_html=True)
            if p.get("relazione_md") or p.get("sintesi_md"):
                dati_docx = _docx_bytes(p)
                if dati_docx:
                    st.download_button(
                        "Scarica relazione (.docx)", dati_docx, file_name=f"{p['id']}_relazione.docx",
                        key=f"dl_{p['id']}",
                    )

            if st.button("Apri questa pratica", key=f"apri_{p['id']}", width="stretch"):
                st.session_state["pratica_attiva"] = p["id"]
                st.rerun()

            conferma_key = f"conferma_elim_{p['id']}"
            if st.session_state.get(conferma_key):
                st.warning("Eliminare definitivamente questa pratica e la relazione associata?")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("Sì, elimina", key=f"conf_si_{p['id']}", width="stretch"):
                        registry.delete_pratica(p["id"])
                        st.session_state.pop(conferma_key, None)
                        if st.session_state.get("pratica_attiva") == p["id"]:
                            st.session_state["pratica_attiva"] = None
                        st.rerun()
                with cc2:
                    if st.button("Annulla", key=f"conf_no_{p['id']}", width="stretch"):
                        st.session_state.pop(conferma_key, None)
                        st.rerun()
            else:
                if st.button("Elimina pratica", key=f"del_{p['id']}", width="stretch"):
                    st.session_state[conferma_key] = True
                    st.rerun()


# ---------- Corpo principale ----------
st.title("Agente Finanziario EIAOS")
st.caption("Protocollo FIN-01 — due diligence strutturata su strumenti finanziari")
st.caption(
    "Questa relazione è un supporto analitico alla decisione, basato su fonti pubbliche: "
    "non costituisce consulenza finanziaria personalizzata né garanzia di risultato. Le "
    "decisioni di impiego di capitale restano interamente a carico di chi le assume; "
    "verifica sempre i dati con le fonti ufficiali prima di agire."
)

st.subheader("1. Identifica lo strumento")
col1, col2 = st.columns([3, 1])
with col1:
    identificativo = st.text_input(
        "ISIN o Ticker", value=st.session_state["identificativo"], placeholder="es. XS3388189477",
    )
with col2:
    st.write("")
    st.write("")
    cerca = st.button("Identifica", width="stretch")

if cerca and identificativo.strip():
    st.session_state["identificativo"] = identificativo.strip()
    with st.spinner("Ricerca fonti ufficiali in corso..."):
        try:
            st.session_state["lookup_result"] = agent.lookup_strumento(identificativo.strip())
        except RuntimeError as e:
            st.error(str(e))
            st.session_state["lookup_result"] = None
    st.session_state["lookup_done"] = True

manuale = st.checkbox(
    "Inserisci i dati dello strumento manualmente (usa se l'identificazione automatica fallisce o lo strumento non è quotato)"
)

strumento = mercato = valuta_strumento = ""

if manuale:
    strumento = st.text_input("Nome strumento")
    mercato = st.text_input("Mercato di quotazione")
    valuta_strumento = st.text_input("Valuta di negoziazione su quel mercato", value="EUR")

elif st.session_state["lookup_done"] and st.session_state["lookup_result"]:
    r = st.session_state["lookup_result"]
    if r.get("trovato"):
        st.success(f"Identificato: {r.get('strumento')} — {r.get('emittente', '')}")
        strumento = st.text_input("Nome strumento (verifica/correggi)", value=r.get("strumento", ""))
        mercati_disponibili = r.get("mercati", [])
        if len(mercati_disponibili) > 1:
            opzioni = [f"{m.get('nome')} ({m.get('valuta_negoziazione')})" for m in mercati_disponibili]
            scelta = st.selectbox("Mercato di quotazione (più piazze disponibili — scegli)", opzioni)
            m_scelto = mercati_disponibili[opzioni.index(scelta)]
            mercato, valuta_strumento = m_scelto.get("nome"), m_scelto.get("valuta_negoziazione")
        elif len(mercati_disponibili) == 1:
            mercato = mercati_disponibili[0].get("nome")
            valuta_strumento = mercati_disponibili[0].get("valuta_negoziazione")
            st.info(f"Mercato: {mercato} — valuta di negoziazione: {valuta_strumento}")
        else:
            mercato = st.text_input("Mercato di quotazione")
            valuta_strumento = st.text_input("Valuta di negoziazione", value=r.get("valuta_base_strumento", "EUR"))
    else:
        st.warning(f"Identificazione non riuscita: {r.get('motivo', 'motivo non specificato')}. Usa l'inserimento manuale sopra.")

if strumento and mercato and valuta_strumento:
    st.divider()
    st.subheader("2. Tesi e orizzonte (obbligatori)")
    tesi_speculativa = st.text_area(
        "Tesi speculativa", placeholder="Descrivi in poche frasi perché ritieni interessante questo strumento ora",
        height=100,
    )
    orizzonte_scelta = st.selectbox("Orizzonte temporale ipotizzato", ORIZZONTI)
    orizzonte = orizzonte_scelta
    if orizzonte_scelta == "Altro (specifica sotto)":
        orizzonte = st.text_input("Specifica l'orizzonte")

    st.divider()
    st.subheader("3. Dati patrimoniali")
    valuta_dati = st.selectbox("Valuta dei tuoi dati patrimoniali", ["EUR", "USD"], index=0)
    st.caption("Valori indicativi: determinano le soglie di rischio nella relazione, non serve la precisione al centesimo.")
    c1, c2, c3 = st.columns(3)
    with c1:
        capitale_disponibile = st.number_input(f"Capitale disponibile ({valuta_dati})", min_value=0.0, step=100.0)
    with c2:
        patrimonio_indicativo = st.number_input(f"Patrimonio indicativo ({valuta_dati})", min_value=0.0, step=1000.0)
    with c3:
        perdita_massima_accettabile = st.number_input(f"Perdita massima accettabile ({valuta_dati})", min_value=0.0, step=100.0)

    st.divider()
    genera = st.button("Crea pratica ed esegui analisi FIN-01", type="primary", width="stretch")

    if genera:
        dati = {
            "strumento": strumento,
            "isin_o_ticker": st.session_state["identificativo"],
            "mercato": mercato,
            "valuta": valuta_strumento,
            "tesi_speculativa": tesi_speculativa,
            "orizzonte": orizzonte,
            "capitale_disponibile": f"{capitale_disponibile} {valuta_dati}",
            "patrimonio_indicativo": f"{patrimonio_indicativo} {valuta_dati}",
            "perdita_massima_accettabile": f"{perdita_massima_accettabile} {valuta_dati}",
        }
        mancanti = validation.validate_dati(dati)
        if mancanti:
            st.error(f"Completa questi campi obbligatori prima di procedere: {', '.join(mancanti)}")
        else:
            pratica = registry.create_pratica(dati)
            with st.spinner("Ricerca fonti ufficiali e redazione di sintesi e verdetto..."):
                try:
                    risultato = agent.run_sintesi(dati)
                except Exception as e:
                    st.error(f"Errore durante l'analisi: {e}")
                    st.stop()

            sintesi_pulita, dashboard = agent.extract_dashboard(risultato["report_md"])
            troncato = risultato.get("stop_reason") == "max_tokens" and not dashboard

            registry.update_pratica(
                pratica["id"], stato="Sintesi prodotta", sintesi_md=sintesi_pulita,
                dashboard=dashboard, note=[{"troncato": troncato}] if troncato else [],
            )
            if troncato:
                st.warning(
                    "La sintesi è stata troncata per limite di lunghezza prima del blocco dati finale: "
                    "il cruscotto potrebbe non essere disponibile per questa pratica."
                )
            st.session_state["pratica_attiva"] = pratica["id"]
            st.rerun()


# ---------- Pratica attiva: sintesi, cruscotto, e generazione relazione completa on-demand ----------
if st.session_state.get("pratica_attiva"):
    try:
        pratica_attiva = registry.get_pratica(st.session_state["pratica_attiva"])
    except KeyError:
        pratica_attiva = None
        st.session_state["pratica_attiva"] = None

    if pratica_attiva:
        st.divider()
        dati_attivi = pratica_attiva["dati_iniziali"]
        st.subheader(f"Pratica {pratica_attiva['id']} — {dati_attivi.get('strumento', '?')}")

        dashboard = pratica_attiva.get("dashboard")
        capitale_attivo = _parse_importo(dati_attivi.get("capitale_disponibile", ""))
        if dashboard:
            render_dashboard(dashboard, capitale_utente=capitale_attivo)
        else:
            note = pratica_attiva.get("note") or []
            era_troncato = any(isinstance(n, dict) and n.get("troncato") for n in note)
            if era_troncato:
                st.warning(
                    "Il cruscotto non è disponibile: la sintesi era stata troncata per limite "
                    "di lunghezza prima del blocco dati finale."
                )
            else:
                st.caption("Cruscotto non disponibile per questa pratica (il modello non ha restituito il blocco dati atteso).")

        if pratica_attiva.get("sintesi_md"):
            with st.expander("Executive summary e verdetto operativo (sezioni 1-2)"):
                st.markdown(pratica_attiva["sintesi_md"])

        if pratica_attiva["stato"] == "Relazione completa prodotta" and pratica_attiva.get("relazione_md"):
            dati_docx = _docx_bytes(pratica_attiva)
            if dati_docx:
                st.download_button(
                    "Scarica relazione completa (.docx)", dati_docx,
                    file_name=f"{pratica_attiva['id']}_relazione.docx", key="dl_completa_attiva",
                )
            with st.expander("Leggi la relazione completa (33 sezioni)"):
                st.markdown(pratica_attiva["relazione_md"])
        else:
            genera_completa = st.button(
                "Genera relazione completa (sezioni 3-33)", type="secondary", width="stretch",
                key="genera_completa_attiva",
            )
            if genera_completa:
                sintesi_per_prompt = pratica_attiva.get("sintesi_md") or ""
                with st.spinner("Redazione delle sezioni restanti (alcuni minuti)..."):
                    try:
                        risultato_completa = agent.run_completa(dati_attivi, sintesi_per_prompt)
                    except Exception as e:
                        st.error(f"Errore durante la generazione della relazione completa: {e}")
                        st.stop()

                report_finale = sintesi_per_prompt.rstrip() + "\n\n" + risultato_completa["report_md"].strip()
                registry.update_pratica(
                    pratica_attiva["id"], stato="Relazione completa prodotta", relazione_md=report_finale,
                )
                if risultato_completa.get("stop_reason") == "max_tokens":
                    st.warning("La relazione completa è stata troncata per limite di lunghezza: verificane la fine prima di considerarla definitiva.")
                st.rerun()
