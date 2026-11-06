# config/calendars — Calendários do Laboratório de Derivativos

Artefatos declarativos produzidos pelo Colaborador 1 (ChatGPT) em 06/11/2026 e **verificados por Claude em 06/11/2026**:

| Arquivo | schema_version | Identidades | Status B3 |
|---|---|---|---|
| b3_calendar_2026.yaml | 3.0.0 (JSON estrito dentro de .yaml) | 6 | 247 sessões confirmadas (Quadro A do OC 041/2026) |
| b3_calendar_2027.yaml | 3.0.0 (JSON estrito dentro de .yaml) | 6 | `unknown` (365) + projeção separada (365) |
| b3_calendar_2028.yaml | 3.0.0 (JSON estrito dentro de .yaml) | 6 | `unknown` (366); 29/02 presente |

Verificações independentes (Claude, 06/11/2026):
- SHA-256 do PDF `evidence_b3_oc_041_2026_errata.pdf` = `82d42d34…c34958` — confere com `evidence_catalog.B3_OC041_2026` e com o YAML mínimo.
- Quadro A (pp. 3–4) conferido **visualmente**: 14 fechamentos de seg–sex em 2026, idênticos aos de `calendar_day[B3_LISTED_TRADING, closed, !weekend]`.
- B3 2026 open=247; ANBIMA 2026=249, 2027=251, 2028=248; NYSE 251/251/251; 24/12 e 31/12 fechados em B3 e abertos em ANBIMA.
- Candidato de vencimento nov/2026: nominal 2026-11-20 → `preceding` → **2026-11-19**, `is_listed_contract=false`.
- Custo de carga: os arquivos 3.0.0 usam JSON estrito (subconjunto de YAML 1.2) — `json.loads` lê cada um em ~15–40 ms; `yaml.safe_load` puro levaria ~1,5–2,5 s. Regra para o loader (DL-PR02): usar `json` da stdlib (fallback YAML só se o `json` falhar, com log), carregar **uma vez por processo**, ler só `calendar`, `calendar_version`, `calendar_day` das identidades `B3_LISTED_TRADING` e `BR_ANBIMA_BUSINESS`; demais ignoradas com log. O `calendar_loader.py` do Colaborador 1 é referência, não é importado: o repo escreve o seu, com testes.

Regras de uso (ADR-0023 / registro de decisões §5.1):
- `day_status=unknown` → ano fora de `coverage` → `CalendarCoverageError`; projeção nunca promovida.
- 247/249/251 **não** substituem o denominador 252.
- Calendário oficial não altera a procedência de preços fixture.
- Calendários dos EUA: eventos do Mapeador (Fase 2), não calendário do pricer.

Estes arquivos entram no git no **DL-PR02**, junto com `backend/derivatives/pricing/calendar.py` e seus testes.

Versionado no DL-PR02 em 2026-11-06; alterações exigem novo `SHA256SUMS` e revisão.
