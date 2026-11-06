# Fixtures documentais — OpLab REST API v3

- **Fonte:** <https://apidocs.oplab.com.br/>
- **Data de captura:** 2026-11-05
- **Natureza:** exemplos de documentacao — **nao sao observacoes de mercado**.
- **Procedencia:** `provenance=documental`, `purpose=test` (ver
  `backend/derivatives/provenance.py` e ADR-0023).

Cada arquivo e uma copia byte a byte do exemplo oficial da documentacao,
registrado com hash SHA-256 em `manifest.json`. Qualquer divergencia entre
estes exemplos e a API real sera tratada na homologacao (estado B), com
retrabalho aceito (Decisao 7 do ADR-0023).

| Arquivo | Endpoint |
|---|---|
| `market_options_PETR3.json` | `GET /market/options/{symbol}` |
| `market_options_details_PETRE100.json` | `GET /market/options/details/{symbol}` |
| `market_stocks_PETR4.json` | `GET /market/stocks/{symbol}` |
| `market_instruments_XBOV11.json` | `GET /market/instruments/{symbol}` |
| `market_interest_rates.json` | `GET /market/interest_rates` |
| `market_status.json` | `GET /market/status` |
| `market_options_bs_example.json` | `GET /market/options/bs` |

**Atencao:** `market_options_bs_example.json` tem `volatility: 0` no exemplo
oficial, o que o torna **inutil como referencia numerica** — nao usar como
teste de BSM (as referencias numericas obrigatorias estao no ADR-0023: Hull,
paridade put-call, round-trip de IV).
