# DL3-PR00 — Supercartão: VI não identificável na precisão do tick

**Data:** 21/11/2026 · **Autor:** Claude · **Para:** Codex · **Base:** `main` = `ea9373f`
**Branch:** `feat/dl3-pr00-iv-identificabilidade` · **PR em rascunho**
**Substitui** a seção "DL3-PR00" de `DL3_CARDS.md`. As "Regras comuns" daquele arquivo valem.

---

## 0. Correção minha, antes de tudo

A seção anterior pedia um status novo e uma segunda regra de "banda" com limite 0,05. Rodei
o ensaio nas 69 referências antes de fechar este cartão e mudei duas coisas:

1. **`not_identifiable` já existe** nos dois motores (`iv:not_identifiable` na árvore,
   `"not_identifiable"` no FD), hoje acionado por tolerância numérica (`tol_price_rel`,
   1e-10). Não se cria status novo: a regra existente passa a usar a precisão do tick.
2. **A regra de banda saiu.** `banda > 0,05` é a mesma grandeza que o
   `low_sensitivity_price` já existente (sensibilidade menor que 0,2 por unidade de
   volatilidade) e não muda nenhum dos 69 casos. Fica fora deste PR.

Resultado: PR menor, uma regra só.

## 1. Problema

Nos casos B21 e C01 do oráculo, o preço está a 2,4e-7 e 5,9e-7 do limite inferior. Os dois
motores devolvem `ok` com erro de VI de 2,6 a 5,5 pontos percentuais. Um preço cotado em
centavos não distingue esse valor do próprio limite inferior. A VI ali não é informação.

## 2. Regra

> Se `alvo − limite_inferior < price_tick`, a inversão recusa com `not_identifiable`,
> sem sigma, antes de qualquer busca.

- `limite_inferior = max(limite europeu de price_bounds, valor de exercício imediato)`.
  É o mesmo que a árvore já usa. **O FD hoje usa só o exercício imediato** e passa a
  receber o limite pronto.
- `price_tick` vem de configuração: `0.01`, em unidade de preço por ação (a mesma unidade
  do alvo já dividido por `quotation_form`).
- A checagem por `tol` existente continua. A regra nova se soma a ela.
- Lado superior (`upper − target`) não muda.

## 3. Ensaio já feito (não refazer, só reproduzir)

Motores de `main`, árvore 200/201, malha 400×200, `price_tick = 0,01`:

| Caso | Preço | Alvo − limite | Erro de VI árvore | Erro de VI FD | Com a regra |
|---|---|---|---|---|---|
| B21 | 20,0000 | 2,4e-07 | 5,5e-02 | 5,3e-02 | recusa |
| C01 | 10,0000 | 5,9e-07 | 2,8e-02 | 2,6e-02 | recusa |
| B24 | 20,0518 | 5,2e-02 | 1,4e-04 | 6,1e-05 | inalterado |
| A13 | 11,2081 | 7,3e-02 | 4,6e-05 | 1,7e-05 | inalterado |
| C02 | 10,0892 | 8,9e-02 | 3,5e-05 | 1,0e-05 | inalterado |
| demais 64 | — | ≥ 1,1e-01 | ≤ 3,8e-04 | ≤ 2,3e-04 | inalterados |

A regra recusa exatamente os dois casos ruins. A folga até o próximo caso é de 5 vezes o
tick. No demo sintético, a única linha americana (SYNAC150 a 2,9 / 3,0 / 3,1) não muda.

A13 importa: ali o limite que vale é `S − K·e^(−rT)` (0,073 acima), não o exercício
imediato (1,21 acima). Por isso o FD precisa receber o limite, não recalcular.

## 4. Mudanças, arquivo por arquivo

| Arquivo | Mudança |
|---|---|
| `config/american_iv.yaml` | Acrescentar `price_tick: 0.01` com comentário "passo de preço por ação; VI não é publicada a menos de um tick do limite inferior". |
| `config/american_iv_config_model.py` | Campo `price_tick: float = Field(gt=0)`. Sem default, no estilo do modelo. |
| `backend/derivatives/pricing/american_bridge.py` | Em `american_implied_vol`, logo após as checagens de limite existentes: `if target - lower < cfg.price_tick: return AmericanIvRefusal("iv:not_identifiable")`. |
| `backend/derivatives/pricing/fd_american.py` | `fd_implied_vol` ganha dois parâmetros nomeados obrigatórios: `lower_bound: float` e `price_tick: float`. Validação: finitos, `price_tick > 0`, `lower_bound >= 0`; fora disso `"invalid_input"`. Checagem: `target_price − max(lower_bound, exercício imediato) < price_tick` ⇒ `"not_identifiable"`. **Sem import novo** (o teste de isolamento do FD continua valendo). |
| `backend/derivatives/service/american_demo.py` | Calcular o limite com `price_bounds` e passar `lower_bound` e `iv_config.price_tick` ao FD. O mapa de recusas não muda (`iv:not_identifiable → NOT_APPLICABLE`). |
| `tests/…` | Ver §5. As chamadas existentes de `fd_implied_vol` nos testes recebem os dois argumentos novos. |

Teto: **≤ 80 linhas de produção**. Passou disso, pare e relate.

## 5. Testes

Publique primeiro o commit vermelho com T1–T4, depois o verde.

| ID | Teste | Espera |
|---|---|---|
| T1 | Árvore em B21 e C01 | `AmericanIvRefusal`, razão `iv:not_identifiable`, `sigma is None` |
| T2 | FD em B21 e C01 | `status == "not_identifiable"`, `sigma is None` |
| T3 | Fronteira, nos dois motores | alvo = limite + tick·(1 − 1e-6) recusa; alvo = limite + tick·(1 + 1e-6) **não** recusa por esta regra |
| T4 | Limite europeu vinculante (call, q = 0, dentro do dinheiro): alvo = `S − K·e^(−rT)` + 0,005 | Os dois motores recusam, embora o alvo esteja muito acima do exercício imediato |
| T5 | Mesma chamada de B21 com `price_tick = 1e-12` | Volta a devolver solução (prova que só a regra mudou e que o tick vem da configuração) |
| T6 | Configuração | YAML sem `price_tick`, com zero, negativo ou inteiro falha na carga |
| T7 | FD com `price_tick` ≤ 0 ou não finito, `lower_bound` negativo ou não finito | `"invalid_input"` |
| T8 | Demo | Testes de demo existentes seguem com as mesmas asserções. Um teste novo: cotação a menos de um tick do limite gera linha recusada, mensagem `iv:not_identifiable` e sem sigma |
| T9 | Oráculo | Ver abaixo |

**Edições autorizadas em `tests/unit/derivatives/test_quantlib_oracle.py`** (e só estas):

- `_fd_iv` passa `lower_bound` e `price_tick`; `_IV` carrega `price_tick` do YAML.
- Teste novo `test_o11b_near_intrinsic_is_refused`: B21 e C01 recusados nos dois motores.
- `test_o12_report`: a última asserção vira "erro de VI não nulo fora de `_EDGES`; nulo e
  status `not_identifiable` dentro de `_EDGES`".
- `test_o6`, `test_o8`, `test_o10` **não mudam**: os 67 casos seguem `ok` nos mesmos limites.
- O JSON de referência, o gerador e `PROVENANCE.md` não são tocados; `test_o1` segue verde.

**Mutantes que devem morrer** (liste na descrição do PR):

1. Remover a checagem na árvore. 2. Remover a checagem no FD. 3. FD usar o exercício
imediato em vez de `lower_bound` (morre em T4). 4. Comparar com `tol` em vez de
`price_tick`. 5. Recusa carregando sigma. 6. Tick literal `0.01` no código em vez da
configuração (morre em T5).

## 6. Critérios de parada

Pare e relate, sem ajustar número nem regra, se:

- algum dos 67 casos fora de `_EDGES` mudar de status ou de sigma;
- algum teste existente precisar de edição além de acrescentar `price_tick` a uma
  configuração ou os dois argumentos novos a uma chamada do FD (fora as do §5);
- o teste de isolamento do FD (`test_fd_american_isolation.py`) pedir import novo;
- as linhas de produção passarem de 80.

## 7. Fora do escopo

- Caminho europeu (BSM, `implied_vol.py`, contrato YAML da Fase 1). As puts da B3 são
  europeias e merecem a mesma regra, mas isso é outro cartão.
- Campo público novo, banda de VI, alteração de `low_sensitivity_price`.
- Qualquer coisa de `backend/derivatives/ticket/`.
- Tick por instrumento ou por faixa de preço: `0,01` único é **[padrão]**, trocável por
  adendo.

## 8. Entrega

1. Portão completo verde em clone limpo (rode o arquivo do oráculo em separado se o tempo
   total passar do limite da sua máquina).
2. Descrição do PR: cabeça, contagem de testes, linhas de produção, os 6 mutantes, a tabela
   do §3 reproduzida por você, desvios do cartão ou "nenhum".
3. Copie este cartão para `docs/specs/derivatives/fase3/DL3-PR00.md`.
4. Rode a skill `quimera-lab-review` na cabeça publicada e gere os **dois relatórios fora do
   Git**: parecer e avaliação de simplificação v0.2. Só os SHA-256 vão na descrição.
5. Não marque como pronto para revisão. Claude forma o parecer, lê os relatórios e decide.

## Adendo de 21/11/2026 — piso americano e fronteira inclusiva

Francisco autorizou as duas correções apontadas na revisão de `d064fb3` do PR #154.
Este adendo substitui a comparação estrita dos §§2, 4 e 5 e as expectativas anteriores
de igualdade do revisor e de alvo zero abaixo de piso positivo no teste FD T16.

1. Para alvo válido, use o piso efetivo, o maior entre o limite europeu e o exercício imediato.
   Se `piso − alvo > tol_price_rel × max(1, alvo)`, recuse sem sigma por
   `below_intrinsic` no FD e `iv:below_intrinsic` na árvore, antes de avaliar o tick.
   A tolerância numérica também se aplica ao piso efetivo quando excede o tick.
2. O limite de publicação é inclusivo. Compare o alvo diretamente com `piso + price_tick`
   no formato binário dos motores. Isso arredonda a soma uma única vez. Para um piso de
   20,00 e um tick de 0,01, subtrair o piso de 20,01 produziria 0,010000000000001563.
   O primeiro float acima da soma já está fora da regra do tick. Permanecem os testes de
   domínio, tolerância, identificabilidade do solver e limite superior de cada motor.
3. A B3 especifica variação mínima de R$ 0,01 no prêmio cotado por unidade ou lote,
   conforme o fator de cotação. O tick configurado neste laboratório se aplica ao preço
   já normalizado por ação. A recusa de VI é uma política de publicação do QUIMERA.
   [Especificação de opções sobre ações da B3](https://b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/opcoes-sobre-acoes.htm).
4. No QuantLib 1.44, a inversão americana usa o preço-alvo, um motor de diferenças finitas
   e parâmetros numéricos de busca. O oráculo offline continua sendo a referência de preço.
   [Implementação de VanillaOption no QuantLib 1.44](https://github.com/lballabio/QuantLib/blob/v1.44/ql/instruments/vanillaoption.cpp#L42-L81).

Aceite adicional: cobrir piso europeu e de exercício, alvos abaixo e dentro da tolerância,
piso zero e positivo, igualdade no tick e vizinhos binários imediatos. Os 69 pares devem
coincidir com a cabeça do revisor. Em relação a main, só B21 e C01 mudam.

## Revisão e integração — 21/11/2026 (Claude)

Duas rodadas. Na cabeça `c11af42`: GO técnico, com dois testes do revisor (`d064fb3`) para a
igualdade exata de um tick, que a suíte não distinguia; a lacuna era do cartão. Francisco
pediu então as duas correções do adendo acima. Na cabeça `fb5b07f`: **GO**.

| Verificação do revisor, clone limpo, Linux x86_64 | Resultado |
|---|---|
| Pytest sem integração | 10.797 aprovados, 16 pulados, 261 subtestes |
| `mypy backend/ --strict` e `pyright backend/` | 0 erros |
| 69 inversões, sigma bit a bit, contra `main` | só `B21` e `C01` mudam |
| 69 inversões contra `c11af42` | idênticas |
| Saída da demo mista contra `main` | idêntica byte a byte |
| Oito mutantes do revisor nas guardas dos dois motores | todos mortos |

Relatórios da skill lidos depois do parecer formado, com SHA-256 conferidos: parecer
`cb9a98d0…3cbf` (GO técnico) e simplificação v0.2 `757b805b…3cde` (S1 opcional, não
aplicada).

Consequência de política a lembrar: opção fora do dinheiro cotada a exatamente R$ 0,01
fica sem VI nos dois motores. O caminho europeu não foi tocado.
