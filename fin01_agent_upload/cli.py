"""
Orchestratore — sostituisce Power Automate.
Workflow (equivalente al punto 15 del prompt originale):
  1. Raccolta dati pratica (CLI o file JSON)
  2. Creazione pratica nel registro
  3. Creazione cartella output dedicata
  4. Esecuzione analisi (agent.run_analysis -> Claude API + web_search)
  5. Salvataggio bozza Markdown
  6. Generazione Word
  7. Aggiornamento stato pratica nel registro

Uso:
  python cli.py nuova --file pratica_esempio.json
  python cli.py analizza FIN01-20260709-001
  python cli.py lista
"""
import argparse
import json
import os
import sys

import registry
import agent
import report_docx
import validation

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


def cmd_nuova(args):
    with open(args.file, "r", encoding="utf-8") as f:
        dati = json.load(f)
    mancanti = validation.validate_dati(dati)
    if mancanti:
        print(f"Attenzione: campi mancanti o segnaposto: {', '.join(mancanti)}.")
        print("La relazione lo segnalerà come rischio procedurale. Consigliato completarli prima di procedere.")
    pratica = registry.create_pratica(dati)
    print(f"Creata pratica {pratica['id']} (stato: {pratica['stato']})")
    if pratica["stato"] == "Dati incompleti":
        print("Attenzione: mancano anche dati patrimoniali. La Fase 0 nella relazione sarà provvisoria.")
    return pratica["id"]


def cmd_analizza(args):
    pratica = registry.get_pratica(args.pratica_id)
    registry.update_pratica(pratica["id"], stato="In raccolta fonti")

    print(f"Avvio analisi per {pratica['id']} — chiamata API in corso (può richiedere qualche minuto)...")
    risultato = agent.run_analysis(pratica["dati_iniziali"])
    registry.update_pratica(pratica["id"], stato="In revisione EZ SUPER")

    report_pulito, dashboard = agent.extract_dashboard(risultato["report_md"])

    pratica_dir = os.path.join(OUTPUT_DIR, pratica["id"])
    os.makedirs(pratica_dir, exist_ok=True)
    docx_path = os.path.join(pratica_dir, "relazione.docx")
    report_docx.build_docx(report_pulito, pratica, docx_path)

    registry.update_pratica(
        pratica["id"],
        stato="Relazione completa prodotta",
        relazione_md=report_pulito,
        dashboard=dashboard,
    )
    print(f"Bozza prodotta: {docx_path}")
    print(f"Chiamate di ricerca web effettuate dal modello: {risultato['num_search_calls']}")


def cmd_lista(args):
    for r in registry.list_pratiche(stato=args.stato):
        dati = r["dati_iniziali"]
        print(f"{r['id']}  [{r['stato']}]  {dati.get('strumento', '?')} ({dati.get('isin_o_ticker', '?')})")


def main():
    parser = argparse.ArgumentParser(description="Agente Finanziario EIAOS — FIN-01")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_nuova = sub.add_parser("nuova", help="Crea una nuova pratica da un file JSON")
    p_nuova.add_argument("--file", required=True)
    p_nuova.set_defaults(func=cmd_nuova)

    p_analizza = sub.add_parser("analizza", help="Esegue l'analisi FIN-01 su una pratica esistente")
    p_analizza.add_argument("pratica_id")
    p_analizza.set_defaults(func=cmd_analizza)

    p_lista = sub.add_parser("lista", help="Elenca le pratiche")
    p_lista.add_argument("--stato", default=None)
    p_lista.set_defaults(func=cmd_lista)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
