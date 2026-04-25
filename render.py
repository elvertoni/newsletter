#!/usr/bin/env python3
"""
Hermes Newsletter — Renderizador HTML.

Lê o JSON de síntese (produzido pelo agente após curadoria) e preenche
o template HTML, gerando o index.html final e atualizando historico.json.

Uso:
    python render.py --input synthesis.json --output index.html
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
TEMPLATE_PATH = SCRIPT_DIR / "template.html"
DEFAULT_OUTPUT_DIR = Path.home() / ".hermes/cron/output"
HISTORICO_PATH = DEFAULT_OUTPUT_DIR / "historico.json"

# Category badge class mapping (matches template CSS)
TAG_CLASSES = {
    "modelo": "tag-modelo",
    "ferramenta": "tag-ferramenta",
    "pesquisa": "tag-pesquisa",
    "infra": "tag-infra",
    "agente": "tag-agente",
    "negocio": "tag-negocio",
    "opinião": "tag-opiniao",
    "opiniao": "tag-opiniao",
}

TAG_NAMES = {
    "modelo": "Modelo",
    "ferramenta": "Ferramenta",
    "pesquisa": "Pesquisa",
    "infra": "Infra",
    "agente": "Agente",
    "negocio": "Negócio",
    "opinião": "Opinião",
    "opiniao": "Opinião",
}


def render_card(destaque: dict) -> str:
    tag = destaque.get("tag", "opinião").lower()
    tag_class = TAG_CLASSES.get(tag, "tag-opiniao")
    tag_name = TAG_NAMES.get(tag, tag.capitalize())
    titulo = destaque.get("titulo", "")
    resumo = destaque.get("resumo", "")
    handle = destaque.get("handle", "")
    url = destaque.get("url", "#")

    # Escape HTML entities in user content
    import html
    titulo = html.escape(titulo)
    resumo = html.escape(resumo)
    handle = html.escape(handle)

    return f"""    <article class="card tag-{tag}-border">
      <div class="tags-row">
        <span class="tag {tag_class}">{tag_name}</span>
      </div>
      <h3 class="card-title">{titulo}</h3>
      <p class="card-summary">{resumo}</p>
      <div class="card-footer">
        <span class="card-handle">fonte: <strong>{handle}</strong></span>
        <a class="card-link" href="{url}" target="_blank" rel="noopener">Ver post →</a>
      </div>
    </article>"""


def render_movimento(handles: list) -> str:
    chips = []
    for i, h in enumerate(handles[:5], 1):
        import html as hmod
        h_clean = hmod.escape(h)
        chips.append(
            f'      <div class="movimento-chip">'
            f'<span class="movimento-rank">{i}</span>'
            f'<span class="movimento-handle">{h_clean}</span></div>'
        )
    return "\n".join(chips)


def load_template() -> str:
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def fill_template(synthesis: dict) -> str:
    template = load_template()

    # Format date
    data_br = synthesis.get("data", "")
    # Try to convert DD/MM/AAAA to long format
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                   "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]

    data_longa = data_br
    try:
        parts = data_br.split("/")
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            from datetime import date
            dt = date(y, m, d)
            dia_semana = dias_semana[dt.weekday()]
            data_longa = f"{dia_semana}, {d} de {meses[m-1]} de {y}"
    except (ValueError, IndexError):
        pass

    # Render cards
    cards_html = "\n".join(
        render_card(d) for d in synthesis.get("destaques", [])
    )

    # Render movimento
    movimento_html = render_movimento(synthesis.get("em_movimento", []))

    # Timestamp
    now = datetime.now()
    # BRT = UTC-3
    from datetime import timedelta
    brt = now.astimezone(timezone(timedelta(hours=-3)))
    timestamp = brt.strftime("%d/%m/%Y às %H:%M BRT")

    # Replace placeholders
    template = template.replace("{{HEADLINE}}", synthesis.get("headline", ""))
    template = template.replace("{{DATA_LONGA}}", data_longa)
    template = template.replace("{{DATA_BR}}", data_br)
    template = template.replace("{{TIMESTAMP}}", timestamp)

    # Indent cards and movimento to match template indentation
    template = template.replace("    {{CARDS}}", cards_html)
    template = template.replace("      {{MOVIMENTO}}", movimento_html)

    return template


def update_historico(synthesis: dict):
    """Append current edition to historico.json (keep last 30)."""
    entry = {
        "data": synthesis.get("data", ""),
        "headline": synthesis.get("headline", ""),
        "destaques": synthesis.get("destaques", []),
        "em_movimento": synthesis.get("em_movimento", []),
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }

    historico = []
    if HISTORICO_PATH.exists():
        try:
            with open(HISTORICO_PATH, "r", encoding="utf-8") as f:
                historico = json.load(f)
        except (json.JSONDecodeError, IOError):
            historico = []

    # Avoid duplicate entries for same date
    historico = [h for h in historico if h.get("data") != entry["data"]]

    historico.insert(0, entry)
    historico = historico[:30]  # keep last 30

    HISTORICO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORICO_PATH, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


def main():
    input_path = None
    output_path = DEFAULT_OUTPUT_DIR / "index.html"

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--input" and i + 1 < len(args):
            input_path = Path(args[i + 1])
        elif arg == "--output" and i + 1 < len(args):
            output_path = Path(args[i + 1])

    if not input_path:
        print("Uso: python render.py --input synthesis.json [--output index.html]",
              file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        synthesis = json.load(f)

    html = fill_template(synthesis)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    update_historico(synthesis)

    print(f"✅ HTML gerado: {output_path} ({len(html)} bytes)")
    print(f"   Destaques: {len(synthesis.get('destaques', []))}")
    print(f"   Em movimento: {len(synthesis.get('em_movimento', []))} perfis")
    print(f"   Histórico atualizado: {HISTORICO_PATH}")


if __name__ == "__main__":
    main()
