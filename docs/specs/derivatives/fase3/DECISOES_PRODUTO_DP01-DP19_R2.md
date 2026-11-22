# Registro de decisões de produto — Laboratório de Derivativos (DP-01 a DP-19) — Revisão 2

**Decisões de:** Francisco · **Data:** 22/11/2026 · **Registro:** Claude
**Base:** `main` = `51fd6d2` · PR #162 (DL3-PR06) em rascunho, correção DL3-PR06B em execução no Codex
**Substitui:** a Revisão 1 (`DECISOES_PRODUTO_DP01-DP19_2026-11-22.md`, SHA-256 `0d3d1b4d…233f`)

> **A Revisão 1 não foi editada.** O DL3-PR06B manda copiar aquele arquivo para o repositório
> conferindo o SHA-256. Mexer nele quebraria o cartão que está rodando. Esta Revisão 2 é um
> arquivo novo e passa a ser a referência para os próximos cartões. Um cartão futuro traz a
> Revisão 2 para dentro do repositório.

## Como usar este arquivo

- Todo cartão novo cita os `DP` que implementa e não contradiz nenhum outro.
- **A Parte D é o texto de Francisco e é a fonte de verdade.** As Partes A, B, C e E são
  índice, resumo e conferência do revisor. Se o resumo divergir da Parte D, vale a Parte D.
- Cada decisão é lida em três camadas, como Francisco pediu: **o que vale hoje no simulador**,
  **o que ele quer como produto** e **o que ainda depende de dado, adendo ou homologação**.
- `DP` que muda garantia da ADR-0024 só vira código depois de adendo datado e assinado por
  Francisco. Este arquivo é insumo do adendo, não o substitui.
- Só Francisco altera uma decisão, por escrito.

## Parte A — Índice

| DP | Tema | Situação | Destino |
|---|---|---|---|
| 01 | Limite em reais para o pico de garantia adicional | decidido; código só depois de adendo à G3 | cartão próprio |
| 02 | Zeragem, custódia e histórico | decidido | zeragem no PR07B; histórico em cartão próprio |
| 03 | Borboleta e qualidade da proteção | decidido | PR07B |
| 04 | Uma a quatro pernas; matriz de homologação por estratégia | decidido; faltam exemplos de Jade e THL | PR07B prova zeragem e borboleta; o resto por estratégia |
| 05 | Custos na prévia e no histórico | decidido; falta confirmar plano, canal e vigência | cartão próprio |
| 06 | Bloqueio por divergência; 30 min como teto | decidido | política em D0, cartão próprio; integração depende da fonte real |
| 07 | Perda de sequência ou foto desatualizada; 15 min como teto | decidido (aceita a contraproposta) | cartão próprio; OpLab pendente |
| 08 | Cancelar, editar e duplicar | decidido | cancelamento já vale; duplicar em cartão próprio |
| 09 | Rejeição definitiva | decidido | regra já vale no motor |
| 10 | Volatilidade implícita e aviso visual | decidido (aceita a objeção ao método) | cartão próprio; depende de histórico e calibração |
| 11 | Âncora do recibo em outro domínio de confiança | decidido | cartão próprio |
| 12 | Reserva de compra nunca enviada | decidido | **PR07A** |
| 13 | Relatório contraditório e evento externo | decidido | **PR07A** |
| 14 | Instante do fechamento | decidido | **PR07A** |
| 15 | Rótulos em português | decidido | **PR07A** |
| 16 | Ações no roteiro de replay | decidido | evolução posterior ao PR07 |
| 17 | Rodada de simplificação; Ponytail retirado | decidido | rodada própria |
| 18 | Boletas `T1` e `t1` | decidido | **PR06B** (em execução) |
| 19 | `after_seq=0` e fita com sequência positiva | decidido | **PR06B** (em execução) |

**Não há contestação aberta do revisor.** As três que existiam na Revisão 1 (DP-07, DP-10 e
DP-17) foram resolvidas por Francisco nesta revisão.

## Parte B — Cada decisão em três camadas

"Hoje" descreve o `main` em `51fd6d2`, conferido no código e por sonda (Parte E). "Produto" é
resumo do revisor; o texto que vale está na Parte D.

**DP-01 — Margem e limites assinados**
- **Hoje:** o motor fiscaliza preço por perna, limite líquido (débito máximo ou crédito
  mínimo, `net_limit`) e teto bruto (`gross_cap`), sempre com o executado. `gross_cap` é
  volume bruto. Venda executada a preço melhor entra pelo preço real e pode interromper os
  próximos envios. Não existe estimativa de margem. O motor confere limites com custo zero.
- **Produto:** limite explícito em reais para o pico estimado de garantia adicional. A prévia
  mostra a garantia antes, ao final e no pior estágio intermediário, com fonte, horário e
  premissas, contando ordens abertas e a mudança de regime perto do fechamento. Margem
  ausente, vencida ou sem base: a nova modalidade deixa estudar e **bloqueia o envio**.
  Começa por cenários declarados, comparáveis à mão.
- **Depende de:** adendo à G3 da ADR-0024 assinado por Francisco, antes de qualquer código
  e antes de mudar o que `gross_cap` limita; fonte de margem da corretora.

**DP-02 — Zeragem, custódia e histórico**
- **Hoje:** recomprar para zerar uma vendida, em perna única, o plano aceita até o saldo
  vendido. Vender para zerar uma comprada, em perna única, o plano **recusa**. Na
  desmontagem em par, a venda da proteção só libera na quantidade recomprada e executada.
  Não há persistência nem histórico.
- **Produto:** zerar comprada e vendida até o saldo livre conciliado. Recompra executada
  libera a proteção na mesma quantidade (pediu 100, executou 40, 60 seguem comprometidas).
  Histórico com parciais, custos, boletas interrompidas e eventos externos. Movimento sem
  evidência de origem aparece como **"sem atribuição"**.
- **Depende de:** PR07B demonstra a zeragem com posição sintética, sem persistência. O
  histórico pede cartão próprio e persistência, que a Fase 3 excluiu.

**DP-03 — Borboleta e qualidade da proteção**
- **Hoje:** a borboleta é recusada: uma vendida só pode ter um par. O par declarado na foto
  é conferido em ativo-objeto, tipo, vencimento e multiplicador. **Strike não existe na foto
  de posição**, então o motor não distingue a asa de baixo da asa de cima.
- **Produto:** testes da estrutura completa, de cada asa isolada e de execuções parciais. O
  motor confere ativo-objeto, call ou put, strikes, vencimento, multiplicador e quantidades
  executadas antes de reconhecer a proteção. Uma unidade comprada protege uma unidade
  vendida por vez.
- **Depende de:** PR07B. Exige strike na foto de posição e pareamento de uma vendida com
  mais de uma compra.

**DP-04 — Estruturas e número de pernas**
- **Hoje:** o rascunho aceita de uma a quatro pernas. Trava e condor funcionam. Zeragem de
  comprada e borboleta são recusadas. O par exige mesmo tipo e mesmo vencimento, e a foto
  só conhece opções: calendário, diagonal e estruturas com o ativo não passam.
- **Produto:** uma a quatro pernas agora, oito depois. Matriz de homologação por estratégia
  dizendo se o motor consegue **montar, acompanhar parcial e desmontar**. Estratégia pode
  estar disponível para estudo antes de homologada para envio.
- **Depende de:** exemplos concretos de pernas e proporções de Jade e THL, que Francisco
  fornecerá; um cartão por família depois do PR07B.

**DP-05 — Custos na prévia e no histórico**
- **Hoje:** não há modelo de custos. O motor usa custo conhecido igual a zero.
- **Produto:** custos estimados na prévia, separando B3, corretagem e exercício. Ordem
  parcial cobrada **uma vez por ordem cobrável**. Alteração pode ser ordem nova. Tributos
  com a base de cálculo. Mínimo de exercício só no cenário de exercício. Se day trade ou
  swing ainda não estiver definido, mostrar os dois cenários e dizer qual custo entrou no
  limite assinado. Depois, conciliar com a nota.
- **Depende de:** plano, canal e vigência da tabela aplicável à conta de Francisco; nota de
  corretagem para conciliar; persistência para o histórico.

**DP-06 — Bloqueio por divergência**
- **Hoje:** o bloqueio por divergência não tem liberação. Vale até o fim da sessão; a saída
  é sessão nova com posição conciliada.
- **Produto:** conciliar ao detectar a divergência, no login, na reconexão e a cada execução
  relevante, agrupando tentativas simultâneas; **30 minutos é o teto entre tentativas**.
  Liberar só quando ordens, execuções, posições e reservas concordarem, com evidência
  registrada. Login bem-sucedido não basta. Agendador fora do motor.
- **Depende de:** a política é testável em D0 com eventos simulados. A integração depende
  de conhecer a fonte real.

**DP-07 — Perda de sequência ou foto desatualizada**
- **Hoje:** a fita do replay exige sequência crescente. A lacuna fica marcada, bloqueia novos
  envios e a marca dura até o fim da sessão. Cotação vencida também bloqueia, com parâmetro
  sintético.
- **Produto:** com eventos sequenciados, a lacuna bloqueia os envios daquele livro até
  recuperar a continuidade ou uma foto íntegra com sequência conhecida. Com fotos por
  horário, validar origem, completude e atualidade. Recuperação imediata, com intervalos
  curtos e crescentes; **15 minutos é o teto entre tentativas**. Prazo de validade da
  cotação tem critério próprio.
- **Depende de:** documentação ou amostra autorizada do comportamento da OpLab; limites do
  provedor.

**DP-08 — Cancelar, editar e duplicar**
- **Hoje:** o motor edita e atualiza a prévia, e a decisão vale só para a versão assinada.
  Depois do pedido de cancelamento a boleta não envia novas pernas e segue recebendo fatos.
  Duplicar não existe.
- **Produto:** duplicar para preparar outra hipótese. Enviar a nova boleta exige nova
  confirmação e saldo conciliado, descontando ordens e reservas vivas. Mostrar nova
  corretagem quando houver nova ordem cobrável. Copiar um rascunho não gera cobrança.
- **Depende de:** cartão próprio para duplicar; modelo de custos (DP-05).

**DP-09 — Rejeição definitiva**
- **Hoje:** já vale. Perna rejeitada não é reenviada pela mesma boleta. Timeout fica
  incerto e só sai por reconciliação.
- **Produto:** mostrar o motivo, quanto executou e a exposição que restou. Continuar é
  abrir boleta nova.
- **Depende de:** a exibição entra com a prévia e a tela, em cartão próprio.

**DP-10 — Volatilidade implícita e aviso visual**
- **Hoje:** o motor da boleta não mostra nem trava por volatilidade. Os parâmetros do
  simulador são sintéticos e não homologados.
- **Produto:** manter a visão semanal. "VI elevada" compara o mesmo ativo em prazo e
  distância do dinheiro equivalentes, por convenção documentada de moneyness ou delta. O
  cartão define qualidade mínima das cotações, tamanho da amostra e o que fazer sem séries
  comparáveis. Até calibrar: mostrar a VI e a referência disponível, ou dizer que o
  histórico é insuficiente. Destaque visual com texto e cor.
- **Depende de:** histórico de VI, que não existe hoje; calibração do limiar.

**DP-11 — Âncora do recibo**
- **Hoje:** recibo encadeado por SHA-256. Sem ponta externa ele não prova que não foi
  truncado. O PR #162 grava hash e contagem de eventos por boleta no resumo da sessão, na
  mesma pasta e sob o mesmo usuário.
- **Produto:** manifesto por sessão (boletas esperadas, contagem de eventos, hashes finais)
  sob **controle independente**. O teste detecta recibo truncado e recibo removido. Outra
  pasta ou outro repositório gravável pelo mesmo usuário não serve.
- **Depende de:** escolha do domínio independente; decisão explícita de Francisco sobre a
  classificação de IDs e metadados **antes de qualquer saída da máquina**. Carimbo de tempo
  fica como evolução.

**DP-12 — Reserva de compra nunca enviada**
- **Hoje:** a ocupação de uma compra nunca enviada só sai no fim da sessão.
- **Produto:** liberar quando ficar demonstrado que a tentativa nunca saiu **e** que a
  boleta já não pode enviá-la. Liberação atômica. Envio incerto preserva a reserva. Parcial
  preserva o executado e o comprometido. Teste: duas boletas disputam a mesma recompra, a
  primeira termina antes de enviar, a segunda usa exatamente o saldo liberado.
- **Depende de:** nada externo. PR07A.

**DP-13 — Relatório contraditório e evento externo**
- **Hoje:** relatório impossível da venue (transição inválida) levanta exceção no motor; a
  venue simulada não emite isso. Quando o livro recusa um fato, o motor grava a divergência
  e bloqueia a conta. Execução que chega durante o pedido de cancelamento fica registrada.
- **Produto:** duplicata idêntica reconhecida uma vez; correção oficial referencia o fato
  original; ordem de 10 com acumulado de 12 gera divergência, preservando mensagem, último
  saldo conciliado e bloqueio de envios da conta. Exercício ou enquadramento confirmado
  pela corretora é **fato externo legítimo** e compõe a posição. Durante o bloqueio o
  sistema segue recebendo fatos.
- **Depende de:** nada externo para o simulador. PR07A. O formato real das mensagens da
  corretora fica para D1.

**DP-14 — Instante do fechamento**
- **Hoje:** no instante exato, a checagem de prazos aceita e a venue rejeita. A decisão
  humana é gasta antes da rejeição.
- **Produto:** em D0, regra única: no instante exato a checagem prévia e a venue recusam,
  **antes** de gastar a decisão ou reservar saldo. Testes um microssegundo antes, no
  instante e um microssegundo depois. Relatórios de ordens anteriores seguem entrando.
- **Depende de:** nada externo em D0. PR07A. Em D1 a janela útil depende da série, da fase
  do mercado, da política da corretora e do prazo assinado, cada restrição com motivo próprio.

**DP-15 — Rótulos em português**
- **Hoje:** o resumo do PR #162 tem chaves em português e valores de estado em código
  interno, em inglês.
- **Produto:** português claro, termos de mercado em inglês quando mais reconhecíveis.
  Códigos internos estáveis. Textos específicos quando ordem e boleta pedirem leituras
  diferentes ("cancelamento solicitado" e "ordem cancelada").
- **Depende de:** nada externo. PR07A.

**DP-16 — Ações no roteiro de replay**
- **Hoje:** o motor sabe editar, atualizar a prévia, desarmar e descartar. O roteiro do
  PR06 não expõe essas quatro ações.
- **Produto:** caso em que Francisco altera uma asa da borboleta, vê a nova prévia e
  comprova que a decisão da versão anterior perdeu a validade.
- **Depende de:** borboleta funcionando (PR07B). Evolução posterior.

**DP-17 — Simplificação e Ponytail**
- **Hoje:** três sugestões registradas nos relatórios da skill; nenhuma aplicada.
- **Produto:** rodada com as ferramentas que já existem. Cada sugestão identificada pelo
  relatório de origem e aplicada só com redução concreta de complexidade e equivalência
  demonstrada em resultados, recusas, recibos e testes. **Instalação do Ponytail retirada.**
- **Depende de:** nada externo. Rodada própria, fora dos cartões de produto.

**DP-18 — Boletas `T1` e `t1`**
- **Hoje:** o motor aceita os dois ids; no PR #162, cabeça `742b852`, a sessão também.
- **Produto:** a **sessão** recusa abrir boleta cujo id só difere de outro por maiúsculas e
  minúsculas. O motor continua aceitando os dois.
- **Depende de:** nada. Em execução no DL3-PR06B.

**DP-19 — `after_seq=0`**
- **Hoje:** no PR #162, cabeça `742b852`, uma fita que começa em sequência zero é aceita.
- **Produto:** zero fica reservado para "agir antes do primeiro evento da fita". O comando
  exige fita com sequências positivas e explica a recusa. O leitor da fase anterior não
  muda. Teste demonstra que a ação com `after_seq=0` acontece antes da primeira cotação.
- **Depende de:** nada. Em execução no DL3-PR06B.

## Parte C — Recorte dos cartões e pendências

**Recorte autorizado por Francisco**

| Cartão | Conteúdo |
|---|---|
| **PR06B** | DP-18 e DP-19. Em execução no PR #162. |
| **PR07A** | Origem da cobertura; **bruto assinado, bruto executado e bruto projetado**, com nomes distintos na prévia e no recibo ("o que autorizei, o que aconteceu e o que ainda pode acontecer"); DP-12, DP-13, DP-14 e DP-15. |
| **PR07B** | Zeragem (DP-02) e borboleta (DP-03), em simulação, com posição sintética e sem persistência. Trava e condor seguem na regressão. |
| **Cartões próprios** | Histórico persistente, margem (DP-01), custos (DP-05), integrações (DP-06, DP-07), duplicar (DP-08), volatilidade (DP-10), âncora do recibo (DP-11), roteiro com edição (DP-16), simplificação (DP-17). Cada um com critério de aceitação próprio. |

Valem também as duas resoluções anteriores de Francisco: a cobertura é controlada por conta,
com reaproveitamento entre boletas autorizado na prévia e origem registrada no recibo; e o
`gross_cap` continua limitando volume bruto nas boletas atuais.

**Pendências, com dono**

| Pendência | Dono | Trava o quê |
|---|---|---|
| Adendo à G3 da ADR-0024, datado e assinado | Francisco | todo código do DP-01 e qualquer mudança no `gross_cap` |
| Exemplos de pernas e proporções de Jade e THL | Francisco | homologação dessas estruturas (DP-04) |
| Plano, canal e vigência da tabela de custos da conta | Francisco | DP-05 |
| OpLab entrega sequência ou só fotos com horário | documentação ou amostra autorizada | DP-07 |
| Fonte real de ordens, execuções e posições | degrau D1 | integração do DP-06 |
| Convenção de moneyness ou delta, amostra mínima e histórico de VI | cartão do DP-10 | DP-10 |
| Domínio independente da âncora e classificação de IDs e metadados | Francisco | DP-11 |
| Identificar as três sugestões pelos relatórios de origem | revisor | DP-17 |

## Parte D — Texto de Francisco (Revisão 2, 22/11/2026)

Claude, concordo com a divisão em cartões. Para documentar as decisões, quero preservar a distinção entre o que vale hoje no simulador, o que quero como produto e o que ainda depende de dados ou homologação.

1. **DP-01 — Margem e limites assinados.** Quero um limite explícito, em reais, para o **pico estimado de garantia adicional** que a estrutura pode exigir da conta. A prévia deve mostrar a garantia antes da montagem, ao final e no pior estágio intermediário considerado, com fonte, horário e premissas. A estimativa precisa considerar as ordens já abertas e, quando aplicável, a mudança de regime perto do fechamento. Se a margem estiver ausente, vencida ou sem base para estimar um estágio relevante, a nova modalidade permite estudar a estrutura e **bloqueia o envio**. Concordo em começar com cenários declarados, comparáveis à mão. Faço uma correção na redação: hoje o motor já fiscaliza limites por perna, débito máximo ou crédito mínimo e teto bruto. O `gross_cap` continua limitando volume bruto nas boletas atuais. Mudar essa regra exige adendo à G3 assinado por mim. Uma execução a preço melhor fica registrada pelo preço real, mesmo que o motor precise interromper os próximos envios. [CORE da B3](https://www.b3.com.br/pt_br/produtos-e-servicos/compensacao-e-liquidacao/clearing/administracao-de-riscos/modelo-de-risco/core/) · [Manual de Risco da XP, seção 5.2](https://www.xpi.com.br/documentos/manual-de-risco/)

2. **DP-02 — Zeragem, custódia e histórico.** Quero vender para zerar uma posição comprada e recomprar para zerar uma vendida, até o saldo livre conciliado. Na desmontagem de estruturas, a recompra **executada** libera a quantidade correspondente de proteção. Se solicitei 100 e só 40 executaram, as outras 60 continuam comprometidas. O PR07B pode demonstrar isso com uma posição sintética, sem persistência. O histórico fica em cartão próprio e precisa incluir parciais, custos, boletas interrompidas e eventos externos, como exercício, atribuição e enquadramento pela corretora. Se não houver evidência de qual estratégia originou um movimento, quero vê-lo como **“sem atribuição”** até conciliá-lo. Não quero que o sistema invente o resultado de uma borboleta para fechar a conta.

3. **DP-03 — Borboleta e qualidade da proteção.** Aceito a objeção e ajustaria a expressão “dois graus de proteção”. Na borboleta de calls `+1 K1, −2 K2, +1 K3`, com strikes crescentes, a compra em K1 e a compra em K3 têm efeitos econômicos diferentes. O par vendido em K2 e comprado em K3 tem, no vencimento, perda máxima por unidade igual à largura dessa asa menos o crédito líquido do par, antes dos custos. Essa conta vale para **aquele par**. Para a borboleta clássica de asas iguais, completamente montada a débito, a perda máxima no vencimento é o débito líquido pago, antes dos custos. Quero testes para a estrutura completa, cada asa isolada e execuções parciais. O motor deve conferir ativo-objeto, call ou put, strikes, vencimento, multiplicador e quantidades executadas antes de reconhecer a proteção. A mesma unidade comprada só pode proteger uma unidade vendida por vez. [OIC — long call butterfly](https://www.optionseducation.org/strategies/all-strategies/long-call-butterfly) · [OIC — bear call spread](https://www.optionseducation.org/strategies/all-strategies/bear-call-spread-credit-call-spread)

4. **DP-04 — Estruturas e número de pernas.** Mantenho o protótipo com **uma a quatro pernas**, adicionadas pelo botão “+”, e o objetivo posterior de chegar a oito. O PR07B deve provar zeragem simples e borboleta. Travas e condor já atendidos continuam na regressão. Para Iron Condor, Jade, THL de call e put, collar com o ativo, calendário, diagonal, ratio e vendas coberta ou descoberta, quero uma matriz de homologação por estratégia. Ela deve dizer se o motor consegue **montar, acompanhar uma execução parcial e desmontar**. Para Jade e THL, fornecerei exemplos concretos de pernas e proporções. Uma estratégia pode estar disponível para estudo antes de estar homologada para envio.

5. **DP-05 — Custos na prévia e no histórico.** Aceito as quatro ressalvas da XP, aplicadas ao **plano, canal e período de vigência correspondentes**. A tabela citada para autoatendimento de clientes de escritório credenciado traz R$ 8, R$ 10 ou R$ 12 por ordem de day trade, conforme a faixa financeira, e R$ 18,90 por ordem executada de swing trade. Quero modelar a cobrança integral de uma ordem parcialmente executada **uma vez por ordem cobrável**. Três execuções parciais da mesma ordem não viram automaticamente três corretagens. Uma alteração pode constituir nova ordem para cobrança. Tributos sobre corretagem devem aparecer com sua base de cálculo. O mínimo de R$ 100 por série registrado para exercício entra no cenário de **exercício** correspondente. Na B3, a referência regular consultada para pessoa física é **0,1340% sobre o prêmio**, com tabela própria para day trade. Se a classificação ainda estiver aberta, quero ver os dois cenários e saber qual custo foi usado no limite assinado. Depois, vale a conciliação com a nota. [XP — custos operacionais](https://www.xpi.com.br/custos-operacionais/) · [B3 — tarifas de opções sobre ações](https://b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/opcoes-de-acoes/)

6. **DP-06 — Bloqueio por divergência.** Aceito os **30 minutos como teto entre tentativas**. Quero iniciar a conciliação ao detectar a divergência, no login, na reconexão e quando chegar uma execução relevante, agrupando tentativas simultâneas. Só libero a conta quando ordens, execuções, posições e reservas concordarem, com a evidência registrada. Um login bem-sucedido comprova comunicação, mas ainda pode haver uma ordem viva executando. O agendador fica fora do motor. A política pode ser testada em D0 com eventos simulados. A integração depende de conhecer a fonte real.

7. **DP-07 — Perda de sequência ou foto de mercado desatualizada.** Aceito a contraproposta. Se a fonte fornecer eventos sequenciados, uma lacuna bloqueia os novos envios dependentes daquele livro até recuperarmos a continuidade ou uma foto íntegra com sequência conhecida. Se fornecer apenas fotos com horário, quero validar origem, completude e atualidade. Uma foto nova pode restabelecer a visão atual, mas não prova o que aconteceu entre duas fotos. A recuperação começa imediatamente, com intervalos curtos e crescentes, respeitando os limites do provedor. **Quinze minutos é o teto de espera entre tentativas.** O prazo aceitável de uma cotação tem critério próprio. O comportamento da OpLab fica pendente de documentação ou amostra autorizada.

8. **DP-08 — Cancelar, editar e duplicar.** Enquanto estudo uma estratégia, quero editar pernas e preços e recalcular spread, custos e margem. Depois do pedido de cancelamento, a boleta para de enviar novas pernas e continua recebendo fatos das ordens existentes. Posso duplicá-la para preparar outra hipótese. Para enviar a nova boleta, preciso de nova confirmação e do saldo conciliado, descontando ordens e reservas ainda vivas. Quero ver eventual nova corretagem quando a operação gerar uma nova ordem cobrável. Copiar um rascunho na tela, por si só, não gera cobrança.

9. **DP-09 — Rejeição definitiva.** Mantenho a regra. Uma perna definitivamente rejeitada não é reenviada pela mesma boleta. Quero ver o motivo, quanto já executou e qual exposição restou. Se eu decidir continuar, abro uma nova boleta. Um timeout permanece incerto até a consulta ou reconciliação esclarecer se a ordem foi registrada.

10. **DP-10 — Volatilidade implícita e aviso visual.** Aceito a objeção ao método. Quero manter a **visão semanal** porque ela me ajuda a ler a tela. A classificação de “VI elevada” precisa comparar o mesmo ativo em condições equivalentes de prazo e distância do dinheiro, usando uma convenção documentada de moneyness ou delta. O cartão deve definir também a qualidade mínima das cotações, o tamanho da amostra e como tratar a falta de séries comparáveis. Cinco observações podem descrever a semana. Sozinhas, são base fraca para classificar um valor como excepcional. Até a calibração, mostrem a VI e a referência disponível. Com histórico insuficiente ou VI não identificável, mostrem essa condição. O destaque será visual, com texto e cor. [Emanuel Derman — *Regimes of Volatility*](https://emanuelderman.com/regimes-of-volatility-risk-april-1999/)

11. **DP-11 — Âncora do recibo.** Aceito a exigência de **outro domínio de confiança**. Quem consegue reescrever o recibo não pode também substituir ou apagar a âncora usada para verificá-lo. Quero um manifesto por sessão com as boletas esperadas, quantidade de eventos e hashes finais, preservado sob controle independente. O teste deve detectar tanto o truncamento de um recibo quanto a remoção de um recibo inteiro. Outra pasta ou outro repositório gravável pelo mesmo usuário não satisfaz o requisito. Antes de qualquer saída da máquina, quero decisão explícita sobre a classificação dos IDs e metadados. Carimbo de tempo independente fica como evolução caso seja preciso provar quando o manifesto já existia. [RFC 3161 — carimbo de tempo](https://www.rfc-editor.org/rfc/rfc3161)

12. **DP-12 — Reserva de compra nunca enviada.** Quero liberar a reserva quando ficar demonstrado que a tentativa nunca saiu **e** que a boleta já não pode enviá-la. A liberação deve ser atômica para que duas boletas concorrentes não usem o mesmo saldo. Envio incerto preserva a reserva. Execução parcial preserva o que foi executado e o que ainda estiver comprometido. O teste que quero ver é simples: duas boletas disputam a mesma recompra, a primeira termina antes de enviar, e a segunda passa a usar exatamente o saldo liberado.

13. **DP-13 — Relatório contraditório e evento externo.** Concordo em tratar ambos, com resultados distintos. Duplicata idêntica é reconhecida uma vez. Correção oficial referencia o fato original. Uma ordem de 10 com execução acumulada de 12 gera divergência: preservamos a mensagem, o último saldo conciliado e o bloqueio de novos envios da conta afetada. Já um exercício ou enquadramento confirmado pela corretora é **fato externo legítimo**. Deve compor a posição conciliada mesmo que nenhuma boleta o tenha originado. Durante o bloqueio, o sistema continua recebendo fatos. Quero incluir no teste uma execução válida que chega enquanto o cancelamento está pendente.

14. **DP-14 — Instante do fechamento.** Aceito a regra única em D0. No instante exato do fechamento da fita, a checagem prévia e a venue recusam novos envios. A recusa ocorre antes de gastar a decisão humana ou reservar saldo. Quero testes um microssegundo antes, no instante exato e um microssegundo depois. Em D1, a janela útil dependerá da série, da fase do mercado, da política da corretora e do prazo que assinei. **Recalcular a garantia antes do fechamento não significa que todo instrumento fechou naquele minuto.** Cada restrição precisa ter motivo próprio. Relatórios e correções de ordens anteriores continuam sendo recebidos. [B3 — horários e regras no vencimento](https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/horario-de-negociacao/acoes/) · [XP — Manual de Risco](https://www.xpi.com.br/documentos/manual-de-risco/)

15. **DP-15 — Rótulos em português.** Quero português claro na interface e termos de mercado em inglês quando forem mais reconhecíveis, como *spread*. Os códigos internos permanecem estáveis. Podemos compartilhar a tradução quando o significado coincidir. Quando a leitura depender de ser ordem ou boleta, quero textos específicos. “Cancelamento solicitado” e “ordem cancelada”, por exemplo, precisam ser facilmente distinguíveis.

16. **DP-16 — Ações no roteiro de replay.** Aceito o escopo do PR06. O motor já sabe editar, atualizar a prévia, desarmar e descartar. O roteiro do PR06 expõe apenas as ações previstas naquele cartão. Em evolução posterior, quero um caso em que eu altero uma asa da borboleta, vejo a nova prévia e comprovo que a decisão da versão anterior perdeu a validade.

17. **DP-17 — Simplificação e Ponytail.** Aceito fazer a rodada com as ferramentas que já temos. Quero que cada uma das três sugestões seja identificada pelo relatório de origem e aplicada quando houver redução concreta de complexidade, com equivalência demonstrada nos resultados, recusas, recibos e testes relevantes. **Retiro a proposta de instalar Ponytail nesta rodada.** Podemos reconsiderar ferramenta externa se surgir uma necessidade específica que o projeto ainda não atende.

**Quanto aos próximos cartões**, autorizo a continuação da **redação do PR06B** com DP-18 e DP-19 já decididas. Para o **PR07A**, concordo com origem da cobertura, bruto assinado, bruto executado e bruto projetado, mais DP-12 a DP-15. Quero que os três valores apareçam com nomes distintos na prévia e no recibo, para eu saber o que autorizei, o que aconteceu e o que ainda pode acontecer. Para o **PR07B**, concordo com zeragem e borboleta em simulação. Histórico persistente, margem, custos e integrações terão cartões e critérios de aceitação próprios.

**DP-18 e DP-19 — decisão de Francisco em 22/11/2026, na mensagem que pediu o DL3-PR06B**

ACEITO: DP-18 (`T1` e `t1`). […] Contraproposta: a sessão recusa abrir boleta cujo id só difere de outro por maiúsculas. O motor continua aceitando os dois.

AUTORIZADO SEM MODIFICAÇÃO: 19. Significado de `after_seq=0`. Proponho reservar zero para **“agir antes do primeiro evento da fita”**. Para manter essa promessa, o comando PR06 deve exigir sequências positivas nas fitas que recebe e explicar a recusa quando a primeira sequência for zero ou negativa. O leitor genérico da fase anterior pode preservar seu contrato. Quero um teste que demonstre que uma ação com `after_seq=0` acontece antes da primeira cotação.

## Parte E — Conferência do revisor

**Correção de um erro meu na Revisão 1.** Escrevi que o motor "não confere strike, tipo nem
vencimento" do par de proteção. Está errado em parte. O plano de pernas confere ativo-objeto,
tipo, vencimento e multiplicador. O que falta é o strike, que nem existe na foto de posição.
A camada "Hoje" do DP-03 já traz a versão correta.

**Sondas e leitura de código no `main` `51fd6d2`, em 22/11/2026**

| Situação | Resultado | Como conferi |
|---|---|---|
| Recompra de uma vendida, perna única, até o saldo vendido | plano aceito | sonda em `plan_legs` |
| Recompra acima do saldo vendido | recusado: "recompra atravessa saldo conciliado" | sonda |
| Venda para zerar uma comprada, perna única | recusado: "pareamento ausente ou ambíguo" | sonda |
| Borboleta 1:−2:1, dois pares na mesma vendida | recusado: "atribuição de proteção ambígua" | sonda |
| Trava (compra uma série, vende outra pareada) | plano aceito | sonda |
| Par de proteção confere ativo-objeto, tipo, vencimento e multiplicador; foto sem strike | confirmado | leitura de `sequencing.py` |
| No instante exato do fechamento a decisão é gasta e a venue rejeita depois | confirmado | leitura de `engine.confirm`, `check_deadlines` e `paper_venue.py`; sem cenário executado nesta rodada |
| O motor confere limites com custo conhecido zero | confirmado | leitura de `engine.py` |

As sondas testam o plano de pernas, não a sessão inteira.

**Fatos externos conferidos na Revisão 1 (22/11/2026), mantidos**

| Fato citado nas decisões | Resultado | Fonte |
|---|---|---|
| B3 cobra 0,1340% sobre o prêmio, pessoa física, opções sobre ações, operação regular | **confirmado**: negociação 0,0370% + liquidação 0,0275% + registro 0,0695% | [B3, tarifas de opções de ações](https://b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/opcoes-de-acoes/) |
| Day trade tem faixas próprias na B3 | **confirmado**: de 0,0450% a 0,0260%, regressivo por volume | mesma página |
| XP: R$ 8, R$ 10 ou R$ 12 por ordem de day trade; R$ 18,90 por ordem de swing | **confirmado, com escopo**: valores de autoatendimento para clientes de escritório credenciado; faixas até R$ 10 mil, até R$ 25 mil e acima | [XP, custos operacionais](https://www.xpi.com.br/custos-operacionais/) |
| Os mesmos valores no artigo 1932 da central de atendimento | **não confirmado nessa URL**: na minha leitura a página não trouxe valores | [artigo citado](https://atendimento.xpi.com.br/artigo/1932-quais-os-custos-para-operar-rv-na-xp) |
| Como a XP cobra ordem parcial e alteração | corretagem por ordem executada; parcial cobrada inteira; não executada não é cobrada; **alteração conta como ordem nova** | XP, custos operacionais |
| Impostos e taxas sobre a corretagem | ISS 5%, PIS 0,65% e COFINS 4% acrescidos; taxa operacional de 5,9% em "Outros Bovespa" | XP, custos operacionais |
| Custo de exercício | tabela Bovespa, **mínimo de R$ 100,00 por série** | XP, custos operacionais |
| Posição zerada pela área de Risco | cobrada com corretagem de mesa | XP, custos operacionais |
| XP, manual de risco, pp. 19–20: venda de calls até a posição comprada tem deságio zero | **confirmado** (seção 5.2.3, item iii); a XP pode aplicar deságio adicional em strikes fora dos cenários | [XP, Manual de Risco v66, 14/10/2026](https://web.xpi.com.br/xp/documentos/manual-de-risco/) |
| A XP considera outras posições no mesmo ativo e cenários de estresse | **confirmado** | mesmo manual |
| macOS trata `T1` e `t1` como o mesmo nome | **confirmado como padrão** do APFS | [Apple, APFS Guide, FAQ](https://developer.apple.com/library/prerelease/content/documentation/FileManagement/Conceptual/APFS_Guide/FAQ/FAQ.html) |
| Metodologia CORE da B3; simulador da B3 é hipotético; horários da B3 | **não reconferidos** (a página de horários não abriu) | — |
| FIX, RFC 3161, S3 Object Lock | **não reconferidos**; uso coerente com o que conheço | — |

**Fontes citadas por Francisco na Revisão 2 e não abertas por mim nesta rodada:** OIC (long
call butterfly e bear call spread), Derman, "Regimes of Volatility" (1999), página de
horários da B3, RFC 3161 e página do CORE da B3. As duas contas do DP-03 (perda máxima da
trava de crédito igual à largura menos o crédito; perda máxima da borboleta de asas iguais
montada a débito igual ao débito pago, ambas no vencimento e antes dos custos) conferem com
o resultado padrão dessas estruturas, por dedução minha, sem reabrir a fonte.

## Parte F — Histórico deste registro

| Revisão | Data | O que mudou |
|---|---|---|
| 1 | 22/11/2026 | Dezenove decisões registradas, com revisão adversarial. Depois, DP-18 decidido pela contraproposta e DP-19 autorizado sem modificação. SHA-256 `0d3d1b4d053dc9bce0899e70ec0ebdfc4985a06967c6813372b397bb3b85233f`. Fixada pelo DL3-PR06B. |
| 2 | 22/11/2026 | Francisco reescreveu DP-01 a DP-17 separando o que vale hoje, o que quer como produto e o que depende de dado ou homologação. Aceitou as contrapropostas do DP-07 e do DP-10, retirou o Ponytail (DP-17) e autorizou o recorte PR06B, PR07A e PR07B. O texto original da Revisão 1 fica como histórico naquele arquivo. |
