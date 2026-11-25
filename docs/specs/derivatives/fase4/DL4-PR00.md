# DL4-PR00 — Supercartão: piso e lock do pydantic em 2.14.4

**Data:** 24/11/2026 · **Autor:** Claude (planejador) · **Implementa:** Codex
**Base:** `main` = `1361724` (Fase 3 estendida encerrada)
**PR novo**, em rascunho. Cartão pequeno, de dependência. **Não toca em código de produção.**

**Origem:**

- Plano de PRs do colaborador (24/11/2026), §3, cartão «DL4-PR00 · Fundação».
- Decisão de Francisco, 24/11/2026, neste chat de planejamento: **o pydantic entra
  primeiro, como DL4-PR00**, e a fila da Fase 4 é renumerada (§9). O planejador recomendou
  deixá-lo para antes do M4; Francisco decidiu diferente, e vale a decisão dele.
- Pendência L7 da blueprint e linha do `current_state.md` («o `pyproject.toml` ainda declara
  piso 2.10 para o pydantic; subir o piso é decisão e commit de Francisco»).

## 0. Escopo

**O que acontece hoje.** Fatos conferidos em `1361724`:

- `pyproject.toml` declara `pydantic>=2.10.0`. O `uv.lock` trava 2.13.3. A boleta recusa
  versão anterior a 2.12 na importação (`require_pydantic`, DL3-PR07F1).
- Os avisos GHSA-qpmf-fgh3-ff25 e GHSA-3r8g-cqwr-jr29 (29/10/2026) foram corrigidos na
  **2.14.2**. O primeiro atinge 2.13.0 até 2.14.1, e portanto o lock atual.
- **O QUIMERA não usa a configuração atingida.** O primeiro aviso exige `extra="allow"` com
  tipo de chave anotado em `__pydantic_extra__` e validação JSON. O segundo exige
  `TypedDict` ou dataclass com alias e extra permitido; `BaseModel` não é atingido. O único
  `extra="allow"` do repositório está em `backend/derivatives/oplab/vendor_models.py`, sem
  chave tipada. A atualização é higiene preventiva antes da primeira entrada JSON externa
  (OpLab, M4), não correção de falha demonstrada.

**O que este cartão entrega.**

1. Piso declarado `pydantic>=2.14.4,<3`.
2. Lock com pydantic 2.14.4 e só as transitivas que ele exige.
3. Um teste de política que impede o piso de voltar abaixo da correção e o portão de rodar
   sobre ambiente que não é o do lock.

**O que este cartão não faz.**

- Não muda código em `backend/`, `config/` nem `scripts/`. Não toca a guarda
  `require_pydantic` (ela protege `exclude_if`, não os avisos).
- Não fixa `pydantic-core` como dependência direta.
- Não atualiza outros pacotes, não reduz a matriz de Python, não muda `requires-python`.
- Não mexe em `requirements-rag.txt`, `requirements-vibe.txt` nem
  `infra/litellm/requirements.txt`: são outros ambientes ou avisos de obsolescência.
- Não instala Pydantic AI, não ativa agentes, não adiciona MCP/A2A.

Nenhuma dependência nova.

**Arquivos protegidos.** `pyproject.toml` e `uv.lock` só mudam por esta decisão de
Francisco. Cole na descrição do PR, com data, a autorização dele:
«DL4-PR00: autorizo subir o piso do pydantic para >=2.14.4,<3 e o lock para 2.14.4 —
Francisco, 24/11/2026». Sem a frase colada, o revisor dá NO-GO.

## 1. Referência externa

Conferida pelo planejador em 24/11/2026:

- PyPI: pydantic 2.14.4, publicada em 19/11/2026. Python 3.10 ou mais novo.
- Avisos do mantenedor, publicados em 29/10/2026: as duas faixas atingidas, as condições e
  a versão corrigida (2.14.2) estão no §0.
- O comportamento que importa ao QUIMERA **foi observado por execução** (§5), não lido em
  nota de versão.

Se a página do PyPI ou dos avisos disser outra coisa quando você implementar, pare e relate.

## 2. Arquivos e tetos

| Arquivo | O que muda |
|---|---|
| `pyproject.toml` | uma linha: `"pydantic>=2.10.0",` → `"pydantic>=2.14.4,<3",` |
| `uv.lock` | gerado por `uv lock`, nunca editado à mão |
| `tests/architecture/test_pydantic_floor.py` | novo, P1 a P5 (§4) |
| `docs/specs/derivatives/fase4/DL4-PR00.md` | cópia deste cartão |

**Não muda:** nenhum teste existente, nenhum snapshot, nenhum esquema publicado, nenhuma
âncora, `current_state.md`, `CLAUDE.md`. Linhas novas com até 100 colunas.

## 3. Regra

**Comando de resolução**, numa worktree da base:

```bash
uv lock --upgrade-package 'pydantic==2.14.4'
uv lock --check
uv sync --locked
uv pip check
```

**Delta esperado no lock: exatamente quatro pacotes.**

| Pacote | Base | Candidato |
|---|---|---|
| pydantic | 2.13.3 | 2.14.4 |
| pydantic-core | 2.46.3 | 2.50.5 |
| typing-extensions | 4.15.0 | 4.16.0 |
| typing-inspection | 0.4.2 | 0.4.5 |

Além dos quatro, só muda o `specifier` do pydantic na seção de metadados do projeto. O
`uv.lock` do planejador saiu com SHA-256 `6db65870c3ba…` com uv 0.11.32. **Hash diferente
não é parada** se a versão do uv for outra e o delta de pacotes for o da tabela. **Pacote
diferente é parada.**

**Teste de política** (`tests/architecture/test_pydantic_floor.py`): lê `pyproject.toml` e
`uv.lock` com `tomllib`, só da biblioteca padrão. O leitor do requisito aceita só as formas
`>=X` e `<Y`, cada uma no máximo uma vez; qualquer outra forma é recusa do teste, não
aceitação silenciosa. A versão corrigida fica numa constante com os dois avisos em
comentário: `_PATCHED = (2, 14, 2)`.

## 4. Cenários

| Teste | Afirma | Na base `1361724` | No candidato |
|---|---|---|---|
| P1 | o piso declarado é ≥ 2.14.2 e o teto é exatamente `<3` | **falha**: falta `<` | passa |
| P2 | a versão do lock está dentro do intervalo declarado (sem teto, o intervalo é aberto) | passa | passa |
| P3 | a versão do lock é ≥ 2.14.2 | **falha**: `(2, 13, 3) >= (2, 14, 2)` | passa |
| P4 | `importlib.metadata.version("pydantic")` é igual à do lock | passa | passa |
| P5 | o leitor recusa `~=2.14`, `>=2.14.4,>=2.15`, `==2.14.4` e o nome sem versão | passa | passa |

**RED pelo motivo certo:** na base, falham **P1 e P3, e só eles**, com as mensagens da
tabela. Se P2 falhar com `KeyError` na base, o leitor está errado; o protótipo do
planejador caiu nisso.

O nome do pacote casa com `^pydantic(?![A-Za-z0-9_.-])`: `pydantic-settings` não pode
contar como pydantic.

**Equivalência de comportamento, base × candidato** (o planejador já mediu; você repete na
sua cabeça e anexa):

1. As três sessões oficiais (`calmo`, `leilao`, `rapido`) pelo
   `scripts/derivatives_ticket_replay.py`: os 7 arquivos de saída **idênticos byte a byte**.

   | Sessão | Arquivo | Eventos | Âncora (12 primeiros) |
   |---|---|---|---|
   | calmo | `recibo_T1.jsonl` | 12 | `1d50bba66aa2` |
   | leilao | `recibo_T1.jsonl` | 12 | `8592cd742d26` |
   | rapido | `recibo_T1.jsonl` | 15 | `9ebc9cd5b584` |
   | rapido | `recibo_T2.jsonl` | 1 | `fbcaafa8eb79` |

   Total: 40 eventos, 4 âncoras. Os três `resumo.json` também idênticos.
2. Esquema de saída da prévia: `Preview.model_json_schema(mode="serialization")` serializado
   como no teste existente dá SHA-256 `a1c0bed2054e…` nas duas versões, e os bytes batem
   com `docs/specs/derivatives/fase3/schemas/previa.schema.json`. O teste
   `test_v1_preview_serialization_schema_matches_published_bytes` cobre isso: ele **não
   pode** ser editado.
3. A prova de borda pedida no plano (cobertura omitida, Decimal com expoente, opcionais,
   datetime com fuso, extra proibido, estrito JSON × Python) **já existe** em
   `tests/unit/derivatives/ticket/test_models.py` e passa sem mudança nas duas versões. Não
   escreva teste duplicado.

## 5. Evidência do planejador

Clone de `1361724` em Linux x86_64, Python 3.12.3, uv 0.11.32.

- **Resolução:** o delta é exatamente o da tabela do §3. `uv lock --check` e `uv pip check`
  limpos. Há rodas de `pydantic-core` 2.50.5 para cp312 em macOS arm64, Linux x86_64 e
  Linux aarch64: nada é compilado.
- **Portão sem o teste novo** (`pytest tests/ -q --ignore=tests/integration
  --timeout=120`): base **11.652 aprovados, 16 pulados**; candidato **11.652 aprovados, 16
  pulados**. Os motivos dos pulos não foram comparados um a um.
- **Portão com o teste novo, no candidato:** **11.657 aprovados, 16 pulados**, código 0.
- `mypy backend/ --strict`: limpo em 182 arquivos. `pyright backend/`: 0 erros. Ambos no
  candidato.
- **Sessões e esquema:** idênticos, com os valores do §4.
- **RED e GREEN do teste novo:** na base falham P1 e P3; no candidato passam os cinco.
- **Mutantes:** 6 de 6 detectados (§6).
- **Hashes:** base `pyproject.toml` `8a71e29146f0…`, `uv.lock` `4414a2e753fa…`; candidato
  `pyproject.toml` `96bbf92889cc…`, `uv.lock` `6db65870c3ba…`.

**Não conferido pelo planejador:** o Mac arm64 nativo; o contêiner `openclaw-sandbox`;
`tests/integration`; FastMCP, MCP e pydantic-settings fora do que a suíte já exercita.

## 6. Mutantes obrigatórios

Um por vez, cada um derrubando ao menos um teste. Entre parênteses, quem derrubou no
protótipo.

1. Piso volta para `>=2.14.1,<3` (P1).
2. Teto `<3` removido (P1).
3. Lock volta a 2.13.3 com o piso novo (P2, P3, P4).
4. Ambiente antigo (pydantic 2.13.3) sobre o lock novo, ou seja, imagem ou venv velhos
   (P4).
5. Leitor passa a aceitar `==` (P5).
6. Nome casa por prefixo e conta `pydantic-settings` (P1, P2).

## 7. Critérios de parada

Pare, preserve a base e relate se:

- o lock mudar qualquer pacote fora dos quatro do §3;
- a resolução exigir mudar `requires-python` ou reduzir a matriz de Python;
- qualquer teste existente mudar de resultado, ou a contagem de pulos mudar;
- qualquer um dos 7 arquivos das sessões, alguma das 4 âncoras ou o esquema da prévia
  mudar;
- `mypy --strict` ou `pyright` deixar de sair limpo;
- o portão falhar no Mac ou no Linux;
- for preciso tocar em arquivo fora do §2.

Diferença semântica, de compatibilidade ou de resolução incerta é NO-GO. **Não atualize
snapshot, esquema ou âncora para fazer passar.** Se algo de alias ou Decimal exigir ajuste,
primeiro um caso RED novo e autorização de Francisco para escopo extra.

**Reversão após a integração:** reverter `pyproject.toml` e `uv.lock` juntos, num commit
só. O teste P1 a P5 vai junto. Qualquer fronteira de dado externo continua desligada até
uma versão corrigida ser homologada.

## 8. Entrega

1. Commit vermelho só com `tests/architecture/test_pydantic_floor.py` (P1 e P3 falhando).
   Envie o vermelho ao GitHub antes do verde.
2. Commit verde com `pyproject.toml` e `uv.lock`, sem nada mais.
3. **Portão no Mac arm64**, em clone limpo da cabeça candidata: `uv sync --locked`, depois
   `pytest tests/ -q --ignore=tests/integration --timeout=120`, `mypy backend/ --strict` e
   `pyright backend/`. Esperado: **11.657 aprovados, 16 pulados** (os 11.652 de hoje mais os
   5 novos).
4. **Portão Linux** no contêiner isolado (`openclaw-sandbox`, via MCP/Docker), com **imagem
   construída a partir do lock da cabeça candidata**, nunca reaproveitada. O P4 derruba uma
   imagem velha. Se o Dockerfile usar `uv sync --frozen`, rode antes `uv lock --check`
   sobre o mesmo lock. Registre a arquitetura; o planejador já cobriu x86_64.
   `tests/integration` só no contêiner, nunca no Mac com banco vivo. O workflow
   `pr09-python312.yml` não dispara para estes arquivos; não conte com ele.
5. Para o revisor: cabeça, arquitetura, imagem, versões de Python, uv, pydantic e
   pydantic-core, comandos, logs, contagens, o delta do lock, os 7 SHA-256 das sessões base
   e candidato, o hash do esquema e os 6 mutantes.
6. Descrição do PR: o acima, mais a frase de autorização de Francisco (§0), com data.
7. Copie este cartão para o caminho do §2. Não edite `docs/04_MEM/current_state.md`: o
   planejador atualiza na integração.
8. Skill `quimera-lab-review` e simplificação v0.2 na cabeça publicada, relatórios fora do
   Git, SHA-256 na descrição.
9. **Adendo a este cartão só entra na cópia versionada com a autorização de Francisco
   colada na descrição do PR**, com data.

O revisor analisa as evidências da mesma cabeça e não repete o portão. Roda os mutantes 3 e
4 e a comparação das sessões por conta própria.

## 9. Depois deste cartão — fila da Fase 4 renumerada

Decisão de Francisco em 24/11/2026: vale a numeração do plano do colaborador. A blueprint
(`FASE4_BLUEPRINT.md`, §6 e §10) chamava de DL4-PR00 o contrato de visão; esse nome passa
para DL4-PR01.

| PR | Entrega | Marco |
|---|---|---|
| **00** | piso e lock do pydantic (este) | fundação |
| 01 | contrato de visão: sessão → modelo de tela, puro e versionado | M1 |
| 02 | roteiros sintéticos de trava de BOVA11: calmo, cotação vencida, mercado adverso | M1 |
| 03 | tela HTML estática; prova de uso M1 (18 de 18) | M1 |
| 04 | confirmação de uma versão exata, no simulador | M2 |
| 05 | acompanhamento por perna: executado, vivo, cancelado | M2 |
| 06 | visor de recibo com âncora independente; prova de uso M2 | M2 |
| 07 | alvo de spread que só avisa; prova de uso M3 | M3 |
| 08 | D1: leitura OpLab, só com autorização assinada | M4 (condicional) |
| 09 | relatório de confiabilidade da VI | M4 (condicional) |

**Já decidido para o DL4-PR01** (Francisco, 24/11/2026):

- **L3, mercado adverso:** só as guardas que o simulador já emite (`guards.assess`).
  Bloqueiam leilão, suspensão, cotação vencida, livro inválido, livro incompleto, perda de
  sequência e tempo inválido; spread aberto e pouca profundidade são cautela. Condição nova
  é cartão de motor.
- **L4, risco:** os dois números, com rótulos distintos: o desembolso se só a compra
  executar (`partial_exposure`) e o pior resultado no vencimento ao preço-limite
  (`expiry_profile`, com sinal).

## Anexo — protótipo do teste (referência do planejador)

Usado para medir o §5. Pode ser reescrito, desde que P1 a P5 e os 6 mutantes se comportem
como no §4 e no §6.

```python
"""Mantém o piso declarado do pydantic acima da correção dos avisos e coerente com o lock."""
import re
import tomllib
from importlib.metadata import version
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_PATCHED = (2, 14, 2)  # GHSA-qpmf-fgh3-ff25 e GHSA-3r8g-cqwr-jr29
_NAME = re.compile(r"^pydantic(?![A-Za-z0-9_.-])")
_BOUND = re.compile(r"^(>=|<)([0-9]+(?:\.[0-9]+)*)$")


def _release(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _bounds(requirement: str) -> dict[str, tuple[int, ...]]:
    """Lê somente as formas `>=X` e `<Y`; qualquer outra recusa o manifesto."""
    clauses = requirement.removeprefix("pydantic").replace(" ", "").split(",")
    bounds: dict[str, tuple[int, ...]] = {}
    for clause in clauses:
        match = _BOUND.fullmatch(clause)
        assert match is not None and match[1] not in bounds, requirement
        bounds[match[1]] = _release(match[2])
    return bounds


def _declared() -> str:
    project = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    rows = [dep for dep in project["dependencies"] if _NAME.match(dep)]
    assert len(rows) == 1, rows
    return str(rows[0])


def _locked() -> str:
    lock = tomllib.loads((_ROOT / "uv.lock").read_text(encoding="utf-8"))
    rows = [pkg["version"] for pkg in lock["package"] if pkg["name"] == "pydantic"]
    assert len(rows) == 1, rows
    return str(rows[0])


def _pad(value: tuple[int, ...]) -> tuple[int, ...]:
    return value + (0,) * (3 - len(value))


def test_p1_declared_floor_covers_patched_release() -> None:
    """O manifesto exige a versão corrigida e recusa a próxima maior."""
    bounds = _bounds(_declared())
    assert set(bounds) == {">=", "<"}
    assert _pad(bounds[">="]) >= _PATCHED
    assert bounds["<"] == (3,)


def test_p2_lock_satisfies_manifest() -> None:
    """A versão travada está dentro do intervalo declarado; sem teto, o intervalo é aberto."""
    bounds = _bounds(_declared())
    locked = _pad(_release(_locked()))
    assert _pad(bounds[">="]) <= locked
    assert "<" not in bounds or locked < _pad(bounds["<"])


def test_p3_lock_covers_patched_release() -> None:
    """O lock instala a versão corrigida dos avisos."""
    assert _pad(_release(_locked())) >= _PATCHED


def test_p4_environment_matches_lock() -> None:
    """O portão roda sobre o ambiente do lock, nunca sobre imagem ou venv antigos."""
    assert version("pydantic") == _locked()


def test_p5_bounds_parser_refuses_unknown_forms() -> None:
    """O leitor não aceita formas que ele não sabe comparar."""
    for text in ("pydantic~=2.14", "pydantic>=2.14.4,>=2.15", "pydantic==2.14.4", "pydantic"):
        try:
            _bounds(text)
        except AssertionError:
            continue
        raise AssertionError(text)
```
