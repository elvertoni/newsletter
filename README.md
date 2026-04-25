# Hermes Newsletter

Newsletter diária de IA gerada automaticamente por agente. Coleta posts do X (Twitter) de 38 perfis curados, sintetiza os destaques com LLM e publica em HTML estático.

**Domínio:** [newsletter.tonicoimbra.com](https://newsletter.tonicoimbra.com)

## Arquitetura

```
06:00 BRT → collect.py (X GraphQL) → LLM synthesis → render.py (HTML) → Cloudflare Tunnel
```

| Arquivo | Função |
|---|---|
| `collect.py` | Coleta tweets via GraphQL guest token (38 perfis, sem credenciais) |
| `template.html` | Template HTML — dark theme, Geist, paleta ProfessorDash |
| `render.py` | Preenche template com JSON de síntese + atualiza `historico.json` |
| `hermes-newsletter.service` | Servidor HTTP estático (systemd) |

## Stack

- **Coleta:** `httpx` + X GraphQL API (guest access)
- **Síntese:** Hermes Agent (LLM)
- **Frontend:** HTML estático autocontido (CSS inline, zero JS de tracking)
- **Deploy:** Cloudflare Tunnel → Python http.server
- **Orquestração:** Cron job do Hermes Agent
