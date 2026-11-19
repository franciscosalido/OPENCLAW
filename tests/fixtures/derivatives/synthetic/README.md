# Fixture sintetica — chain BOVA11 com 100 europeias

- **Natureza:** dados **sinteticos**, gerados por script. **Nao sao observacoes
  de mercado** e nunca podem ser apresentados como tal.
- **Procedencia:** `provenance=synthetic`, `purpose=test` (ver
  `backend/derivatives/provenance.py` e ADR-0023).
- **Gerador:** `scripts/derivatives_make_synthetic_fixture.py`
  (`--seed 20261105 --underlying BOVA11 --expiry 2026-11-19 --n 100 --style EUROPEAN`).
- **Conteudo:** uma captura coerente — chain, ativo, taxas e status — no
  instante `2026-11-05T17:00:00-03:00`: spot 150,00, Selic 14,9 % a.a., 50
  strikes de 137,50 a 162,00, precos BSM com smile suave e spread
  arredondado ao centavo (bid para baixo, ask para cima).
- **Integridade:** `manifest.json` registra semente, parametros, versao do
  gerador e SHA-256 de cada arquivo.

Uso: testes do `ChainService` e protocolo de latencia
(`scripts/derivatives_latency_protocol.py`).
