# Registro de decisões de produto — Laboratório de Derivativos (DP-01 a DP-19)

**Decisões de:** Francisco · **Data:** 22/11/2026 · **Registro e revisão adversarial:** Claude
**Base:** `main` = `51fd6d2` · DL3-PR06 no PR #162, revisado na cabeça `742b852` (NO-GO; correção no DL3-PR06B)
**Atualização de 22/11/2026:** Francisco aceitou a contraproposta do revisor para o DP-18 e autorizou o DP-19 sem modificação.

## Como usar este arquivo

- Todo cartão novo cita os `DP` que implementa e não contradiz nenhum outro.
- A Parte D é o texto original de Francisco e é a fonte de verdade. As Partes A a C são
  índice, ressalvas e conferência de fatos do revisor.
- Ressalva do revisor **não altera** a decisão. Só Francisco altera, por escrito.
- `DP` que muda garantia da ADR-0024 só vira código depois de adendo datado e aprovado por
  Francisco. Este arquivo é insumo do adendo, não o substitui.
- Substitui a lista de `PENDENCIAS_DECISOES_PR07_2026-11-22.md` (D1–D11 e M1–M6 viraram
  DP-01 a DP-17, na mesma ordem).

## Parte A — Índice, destino sugerido e parecer do revisor

| DP | Tema | Destino sugerido | Parecer |
|---|---|---|---|
| 01 | Limite de margem adicional; `gross_cap` histórico preservado; "margem indisponível" | cartão próprio, depois de adendo a G3 | aceito com ressalvas |
| 02 | Zerar comprada e vendida; custódia e histórico | PR07B (plano de pernas); histórico em cartão próprio | aceito com ressalva |
| 03 | Borboleta 1:−2:1 como primeiro teste; venda protegida por mais de uma compra | PR07B | aceito com ressalva técnica |
| 04 | 1 a 4 pernas, depois 8; famílias de estruturas por etapa | um cartão por família | aceito |
| 05 | Custos estimados na prévia e conciliados depois | cartão próprio, depois de confirmar a tabela da conta | aceito com correções de fato |
| 06 | Reconciliação no login e a cada 30 min | desenho em D0; código em D1 | aceito com ressalva |
| 07 | Perda de sequência: recuperar já, repetir a cada 15 min | desenho em D0; código em D1 | **contestado em parte** |
| 08 | Cancelar para a boleta; duplicar em boleta nova | PR07A (regra já vale); duplicar em cartão próprio | aceito |
| 09 | Rejeição definitiva; timeout consulta antes | já vale no motor | aceito |
| 10 | VI atual contra mediana de 5 pregões, aviso visual | cartão próprio, com histórico de VI | **contestado no método** |
| 11 | Manifesto de hashes em repositório de auditoria separado | cartão próprio | aceito com ressalva |
| 12 | Liberar reserva de compra nunca enviada | PR07A | aceito |
| 13 | Relatório impossível: preservar, registrar, suspender, sem exceção | PR07A | aceito |
| 14 | Instante do fechamento fora da janela de envio | PR07A (mexe em módulos existentes) | aceito |
| 15 | Rótulos em português | PR07A | aceito |
| 16 | Edição no roteiro, em roteiro futuro | depois do PR07 | aceito |
| 17 | Rodada de simplificações; avaliar instalar o Ponytail | rodada própria | simplificações aceitas; **Ponytail contestado** |
| 18 | Boletas `T1` e `t1` | PR06B | **decidido: vale a contraproposta** (a sessão recusa ids que só diferem por maiúsculas) |
| 19 | `after_seq=0` = antes do primeiro evento; fita com sequência positiva | PR06B | **autorizado sem modificação** |

**Recorte sugerido:** PR06B = DP-18 e DP-19. PR07A = visibilidade já adotada (origem da
cobertura e bruto assinado, executado e projetado na prévia e no recibo) mais DP-12, 13, 14
e 15. PR07B = DP-02 (zeragem) e DP-03 (borboleta). O resto não cabe em PR07: cada um pede
cartão próprio, e DP-01, 06, 07 e 11 dependem de adendo ou do degrau D1.

## Parte B — Ressalvas do revisor

**DP-01, margem.**
1. O número de margem do QUIMERA será sempre estimativa datada. O Manual de Risco da XP
   (v66, 14/10/2026) diz que, para opções, a garantia exigida só aparece na boleta de
   negociação da XP, que o percentual de deságio pode mudar a qualquer momento sem aviso e
   que a garantia da XP pode ser maior ou menor que a chamada de margem da B3.
2. Regra que falta na decisão: enquanto a prévia disser "margem indisponível", a nova
   modalidade **não envia**. Senão o limite assinado em reais não limita nada. Até lá o
   `gross_cap` segue sendo o limite que o motor consegue fazer cumprir.
3. O pico não acontece só nas execuções parciais. O mesmo manual recalcula a garantia de
   day trade como posição 15 minutos antes do fechamento do pregão regular.
4. Replicar o CORE da B3 e o estresse da XP é projeto grande. Primeiro passo defensável:
   tabela de cenários declarados, comparada à mão com o simulador da B3, sem motor de
   margem.

**DP-02, zeragem e histórico.** O histórico por estrutura exige persistência, que a Fase 3
excluiu. Além disso a posição pode mudar por ato da corretora: enquadramento, antecipação
de exercício e exercício contrário sem aviso prévio (manual da XP, seções 6 e 8). Essas
execuções não nascem de boleta e precisam entrar no histórico como origem externa.

**DP-03, borboleta.** "Protegida" tem dois graus. Numa borboleta de calls K1 < K2 < K3, a
venda em K2 pareada com a compra em K1 fica coberta. A venda em K2 pareada com a compra em
K3 é uma trava de crédito, com perda máxima igual à diferença de strikes menos o crédito.
Hoje o par (proteção, vendida) é declarado na foto de posição; o motor não confere strike,
tipo nem vencimento. Para o teste "só uma asa executou" fazer sentido, a qualidade da
proteção tem de ser calculada, não declarada.

**DP-05, custos.** Ver Parte C. A decisão não menciona quatro regras da página de custos da
XP que mudam a conta: impostos sobre a corretagem; alteração de ordem conta como ordem
nova; ordem parcialmente executada é cobrada inteira; exercício tem mínimo por série. A
prévia não sabe se a boleta será day trade ou swing, então mostra as duas contas.

**DP-06, reconciliação.** Trinta minutos servem como teto, não como único gatilho. Ordem
viva continua executando durante a divergência; a tentativa deve disparar também a cada
relatório de execução e a cada reconexão. O agendador fica fora do pacote `ticket`, que não
pode ler relógio.

**DP-07, perda de sequência (contestado em parte).**
1. Número de sequência é coisa de feed sequenciado. Não foi verificado se a fonte de dados
   prevista (OpLab) entrega sequência ou só fotos com horário (não verificado; sem
   assinatura). Se for só foto, a regra real vira "foto íntegra com horário conhecido".
2. Quinze minutos é lento para um livro: todo envio que depende dele fica parado nesse
   intervalo. Proponho tentativas curtas e crescentes (segundos, depois minutos) e 15
   minutos como teto. (baixo nível de evidência: não há dado real de D1)

**DP-08, cancelar e duplicar.** De acordo. Fato a mostrar na boleta duplicada: na XP,
alteração de ordem conta como ordem nova para corretagem.

**DP-10, volatilidade (contestado no método).** Comparar a VI de hoje de uma série com a
mediana dos últimos cinco pregões da mesma série mistura três efeitos: o ativo andou sobre
o sorriso, o prazo encurtou e a volatilidade mudou. "Observações equivalentes" precisa ser
definido como mesma distância do dinheiro (ou delta) e mesmo prazo; senão o aviso de "8
pontos acima" pode ser só movimento do ativo. Cinco pontos é amostra fraca (baixo nível de
evidência). Referência: Derman, "Regimes of Volatility", 1999 (citada de memória, não
reconferida). Depende de guardar histórico de VI, que hoje não existe.

**DP-11, manifesto.** Repositório separado na mesma máquina e no mesmo usuário continua
regravável: o histórico pode ser reescrito. "Separado" precisa significar outro domínio de
confiança. Se o manifesto sair da máquina, a ADR precisa dizer que hash, contagem e id não
são dado de Nível 0. A `main` do próprio repositório segue sem proteção de branch.

**DP-13, relatório impossível.** De acordo. Acrescentar a quarta situação: execução de
origem externa (enquadramento ou exercício feitos pela corretora).

**DP-14, fechamento.** De acordo para o simulador. Na integração futura a janela útil
termina antes do fechamento: a XP recalcula garantia 15 minutos antes e tem zeragem
automática antes do leilão de encerramento.

**DP-17, Ponytail (contestado).** Instalar um repositório novo de ferramentas contraria a
regra do próprio Francisco de 20/11/2026 (não inventar bibliotecas; só quando necessárias)
e abre risco de cadeia de suprimentos num repositório que caminha para ordens. A rodada de
simplificação não depende disso.

**DP-18, `T1` e `t1` (contestado, com contraproposta).** A proposta faz o mesmo comando,
com as mesmas entradas, sair com código 0 no Linux e 2 no Mac. Isso quebra o critério de
aceite do DL3-PR06 (resultado idêntico nas duas plataformas). Contraproposta: a **sessão**
recusa abrir boleta cujo id só difere de outro por maiúsculas e minúsculas. O motor
continua aceitando os dois; a sessão não. O resultado fica igual em qualquer sistema de
arquivos. O APFS do macOS é insensível a maiúsculas por padrão.
**Decisão de Francisco, 22/11/2026: aceita a contraproposta.** Para o DP-18 vale esta regra, e
não a do texto original na Parte D.

**Sobre o volume.** Dezenove decisões não cabem em PR06B, PR07A e PR07B. Juntar tudo é
aumento de escopo. O recorte da Parte A fecha a Fase 3 e entrega o que não depende de
adendo nem de dado real.

## Parte C — Fatos conferidos em 22/11/2026

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

## Parte D — Texto original das decisões (Francisco, 22/11/2026)


## Margem, custos e estruturas

**1. O que quero limitar em cada estrutura**

Quero saber, antes de confirmar uma boleta, **quanto de garantia adicional essa operação pode exigir da minha conta**, inclusive se apenas parte da estrutura executar. Quero ver separadamente o dinheiro que preciso para pagar os prêmios, o débito ou crédito líquido, os custos e o volume bruto negociado. São valores diferentes e eu os uso para decisões diferentes.

A B3 calcula a margem pelo risco de encerramento da carteira, considerando posições, garantias, liquidez e fluxos de caixa. A XP também considera as outras posições no mesmo ativo e aplica cenários de estresse. O manual da XP dá um exemplo concreto: vender calls em quantidade até a posição comprada no ativo pode resultar em **deságio adicional zero** quando a operação reduz o risco. Esse zero se refere à operação nas condições do exemplo. A conta ainda pode ter margem exigida por outras posições. Portanto, não adotaria um percentual fixo por borboleta, trava ou venda descoberta. [Metodologia CORE da B3](https://www.b3.com.br/pt_br/produtos-e-servicos/compensacao-e-liquidacao/clearing/administracao-de-riscos/modelo-de-risco/core/) · [Manual de Risco da XP, pp. 19–20](https://www.xpi.com.br/documentos/manual-de-risco/) · [Simulador de margem da B3](https://simulador.b3.com.br/)

**Minha proposta para o adendo à G3** é criar um limite explícito de margem adicional em reais e preservar o significado histórico de `gross_cap` nas boletas já assinadas. Na nova prévia, quero ver a garantia estimada da conta antes da operação, depois da montagem e no ponto de maior exigência durante as execuções parciais. Por exemplo, se a conta começar exigindo R$ 10 mil, puder chegar a R$ 13 mil durante a montagem e terminar em R$ 11 mil, quero assinar sabendo que o pico adicional estimado é **R$ 3 mil**. Uma venda executada a preço melhor deve ser registrada pelo preço real. O aumento do volume bruto, por si só, não deve interromper a nova modalidade se os limites que assinei continuarem atendidos.

Para calibrar o simulador, quero comparar a mesma carteira e o mesmo cenário com as referências da B3 e da XP, registrando fonte, data e premissas. A OpLab pode ajudar na análise. A B3 informa que o resultado de seu simulador é hipotético e que a exigência efetiva depende da corretora. Enquanto a margem for desconhecida, a prévia deve dizer **“margem indisponível”**. Quero poder estudar a estrutura, mas o sistema não pode apresentar zero como se tivesse calculado a garantia. [Simulador da B3](https://simulador.b3.com.br/) · [OpLab](https://oplab.com.br/)

**2. Zerar posições compradas e vendidas**

Quero poder vender para zerar uma posição comprada e comprar para zerar uma posição vendida, inclusive quando há uma única perna. Se tenho 100 opções compradas e 30 já estão comprometidas com outra ordem ou proteção, o motor deve me mostrar as 70 livres. Uma ordem de zeragem deve parar no saldo disponível, sem inverter a posição.

Para desmontar uma estrutura, quero recomprar primeiro as pernas vendidas. As proteções compradas só ficam disponíveis para venda **na proporção da recompra efetivamente executada**. Assim, se pedi a recompra de 100 e só 40 executaram, a estrutura continua protegida no saldo que permanece vendido.

Quero distinguir **custódia** e **histórico**. A posição conciliada informa quanto posso movimentar agora. O histórico mostra quais execuções pertencem àquela borboleta e quanto ela rendeu, incluindo parciais, custos, exercício e encerramento. Precisamos guardar também as execuções de boletas que terminaram interrompidas. A OpLab divulga importação de movimentações da B3, mas isso, sozinho, não comprova acesso por API à custódia conciliada em tempo real da XP. [OpLab](https://oplab.com.br/)

**3. Borboleta e motor multileg**

Quero que o PR07 comece pela limitação que já conhecemos: uma venda pode ser protegida por mais de uma compra. O primeiro teste de aceitação deve ser uma **borboleta 1:−2:1**, com montagem, execução parcial e desmontagem. Quero ver o que acontece se apenas uma asa executar. O nome “borboleta” na tela não garante que a posição esteja protegida.

Na sequência, quero incluir Iron Condor, Jade e THL de call e de put. Antes de homologar Jade e THL, quero registrar exemplos com ativo, vencimento, strikes, lados e proporções. Assim, o teste representa a estrutura que eu efetivamente opero.

**4. Quantas pernas e quais estruturas entram**

O protótipo deve permitir **uma a quatro pernas**, com um botão **“+ Adicionar perna”**. O objetivo posterior é chegar a oito. Quero poder montar, inverter e zerar as estratégias homologadas. A possibilidade de preencher quatro linhas na tela é diferente da capacidade de executar qualquer combinação de quatro linhas com segurança.

| Etapa proposta | O que quero validar |
|---|---|
| Primeiro conjunto | Compra simples, zeragem de posição comprada ou vendida, travas verticais, borboleta e condor de quatro pernas. |
| Estruturas com o ativo | Venda coberta e collar com custódia conciliada, quantidade disponível e proteção reservada uma única vez. |
| Homologação específica | Calendário e diagonal com risco entre vencimentos. Ratio, Jade, THL e venda descoberta com identificação explícita da parcela descoberta, margem e risco de execução parcial. |

Quero manter a visão de cobertura por conta, mas saber **de qual posição saiu a proteção e qual estrutura a está usando**. Sem essa atribuição, duas boletas podem parecer protegidas para quem olha a tela, e o resultado individual das estratégias perde confiabilidade.

**5. Quando entram corretagem e taxas**

Quero os **custos estimados já na prévia**, antes da confirmação. Depois da execução, quero conciliar a estimativa com a nota de corretagem e guardar o custo efetivo no histórico. A prévia deve separar tarifas B3, corretagem XP e eventual custo de exercício. O spread de compra e venda também deve aparecer, separado das tarifas.

A tabela da B3 consultada informa **0,1340% sobre o prêmio** para pessoa física na categoria regular de opções sobre ações, aplicado a comprador e vendedor nas respectivas operações. Para day trade há faixas próprias. Ações à vista e exercício seguem outra tabela. Na XP, o atendimento publica, para opções, referências de **R$ 8, R$ 10 ou R$ 12 por ordem de day trade**, conforme a faixa financeira, e **R$ 18,90 por ordem executada de swing trade**. Quero conferir canal, plano e tabela vigente antes de aplicar esses valores à minha conta. [B3 — opções sobre ações](https://b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/opcoes-de-acoes/) · [B3 — ações à vista e exercício](https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/) · [XP — custos para operar renda variável](https://atendimento.xpi.com.br/artigo/1932-quais-os-custos-para-operar-rv-na-xp)

Isso muda a comparação entre estratégias. Se a regra aplicável for R$ 18,90 e uma borboleta gerar **três ordens cobradas**, serão **R$ 56,70 de corretagem na entrada**, antes das tarifas B3. Só usaria esse cálculo depois de confirmar como o canal cobra uma ordem estruturada e suas execuções parciais. Quero calcular pelo que a corretora efetivamente cobra, sem presumir uma corretagem por perna ou por parcial.

## Operação, interrupções e reconciliação

**6. Conta bloqueada por divergência**

Quero tentar a reconciliação **no login e a cada 30 minutos** enquanto houver divergência. Reconectar restabelece a comunicação. Para liberar a conta, quero evidência de que ordens abertas, execuções, posições e reservas voltaram a concordar. Se ainda faltar uma execução ou sobrar uma reserva sem explicação, o bloqueio continua e a tela deve mostrar a diferença específica. Na fase atual, essa política pode ser desenhada e ensaiada com dados simulados.

**7. Perda de sequência de mercado**

Se o sistema recebeu o evento 105 depois do 103, quero que ele sinalize imediatamente a lacuna e suspenda os novos envios que dependem daquele livro. Proponho tentar a recuperação assim que a falha for detectada. Durante o pregão, enquanto um agente ou uma pessoa estiver consultando o serviço, quero uma nova tentativa **a cada 15 minutos** se a primeira falhar.

Para liberar, o sistema precisa recuperar o evento faltante ou obter uma foto íntegra do livro com sequência conhecida e aplicar os eventos posteriores em ordem. A passagem de 15 minutos não torna a cotação válida. Recuperar o livro também não resolve, por si só, uma divergência na custódia.

**8. Cancelar a boleta e estudar outro preço**

Enquanto estou estudando uma borboleta, quero trocar strikes, séries, quantidades e preços e recalcular spread, custo, margem e resultado. Cada alteração relevante gera uma nova versão da prévia e exige nova confirmação para envio.

Depois que eu pedir cancelamento, aquela boleta deve parar de enviar novas pernas. O sistema acompanha as ordens já enviadas até saber quanto executou e quanto foi cancelado. Para tentar outro preço, quero poder **duplicar a estratégia em uma nova boleta**, já considerando a posição remanescente. Uma execução recebida durante o pedido de cancelamento continua fazendo parte do histórico. [FIX — relatórios de execução e cancelamento pendente](https://archive.fixtrading.org/online-specification/business-area-trade/)

**9. Rejeição definitiva**

Se a corretora rejeitar definitivamente uma perna, não quero reenvio automático pela mesma boleta. Quero ver o motivo, as pernas já executadas e a exposição que ficou aberta. Se eu decidir prosseguir, abro outra boleta para o saldo conciliado. Se houve apenas timeout, primeiro consultamos o destino da ordem. Repetir uma ordem cujo resultado ainda é desconhecido pode duplicar a posição.

**10. Volatilidade e avisos visuais**

Quero ver a **volatilidade implícita atual**, uma referência recente e a diferença em pontos percentuais. Para o protótipo, proponho a mediana dos últimos cinco pregões válidos, comparando observações equivalentes. Uma VI atual de 34% diante de uma mediana de 26% apareceria como **“8 pontos percentuais acima da referência”**. Com histórico insuficiente ou VI não identificável, quero que a tela diga isso.

Quero destacar a volatilidade elevada com cor **e texto**. O limiar de destaque precisa ser calibrado. Por enquanto, trato isso como aviso visual. Os atuais 5 segundos de idade da cotação e 10 ticks de spread continuam parâmetros sintéticos. Um bloqueio automático por volatilidade exige estudo e homologação próprios.

## Auditoria e correções do motor

**11. Onde guardar o hash final do recibo**

Minha preferência para o QUIMERA local é guardar, ao fechar cada sessão, **um manifesto em um repositório de auditoria separado**, cujo histórico já gravado o processo de replay não possa sobrescrever nem apagar. Cada registro identifica sessão, boleta, quantidade de eventos e SHA-256 final. Quero uma segunda cópia sob meu controle, em armazenamento com retenção imutável ou mídia offline. Um segundo arquivo na mesma pasta, gravável pelo mesmo processo, continua vulnerável à mesma substituição.

O teste de aceitação é simples: retirar o último evento do recibo e recalcular todos os hashes locais. A verificação deve falhar contra o manifesto preservado. Também quero conseguir detectar a remoção de um recibo inteiro pela lista de boletas da sessão. Se futuramente eu precisar provar **quando** o manifesto já existia, podemos acrescentar um carimbo de tempo independente conforme a RFC 3161. Para o simulador, o manifesto separado já resolve a principal dúvida. [RFC 3161 — carimbo de tempo](https://www.rfc-editor.org/rfc/rfc3161) · [Exemplo documentado de retenção imutável](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html)

**12. Reserva de compra que nunca foi enviada**

Entendi a reserva com este exemplo: tenho 100 opções vendidas e duas boletas tentam recomprar as mesmas 100. A primeira reserva o saldo para impedir que ambas comprem e eu termine com uma posição comprada indevida. O problema aparece quando a primeira boleta encerra antes mesmo de enviar a recompra e a segunda continua bloqueada.

Aceito a regra conservadora no simulador atual. Para a evolução, proponho liberar a reserva quando houver prova de que a ordem **nunca foi enviada** e a boleta já não puder enviá-la. Se houve envio ou timeout, mantenho a reserva até a reconciliação. Se houve execução parcial, libero apenas o saldo comprovadamente livre.

**13. Relatório impossível da corretora ou da venue simulada**

Quero corrigir esse caso sem perder a mensagem que explica o problema. Se uma ordem de 10 aparecer com execução acumulada de 12, o motor deve preservar o relatório recebido, registrar a divergência, manter o último saldo conciliado e suspender novos envios da conta afetada. Na tela, quero ler algo como **“ordem de 10, corretora informou 12, aguardando conciliação”**. O restante do sistema deve continuar disponível para consulta e recebimento de fatos.

O desenho deve diferenciar três situações: uma mensagem duplicada idêntica é reconhecida uma vez, uma correção oficial é vinculada à execução original, e uma contradição sem explicação fica pendente. Quero testes para as três, além da execução válida que chega durante o cancelamento. O desbloqueio exige evidência e fica registrado no recibo. [FIX — identificação de execuções, correções e estornos](https://archive.fixtrading.org/online-specification/business-area-trade/)

**14. Instante exato do fechamento**

Proponho uma convenção única: **o instante de fechamento já está fora da janela para novos envios**. Se a sessão termina às 17h no replay, o último instante anterior ainda pode passar pelas demais verificações. Às 17h exatas, tanto a checagem prévia quanto a venue recusam. A recusa deve ocorrer antes de consumir a decisão humana ou reservar saldo. Relatórios de ordens anteriores continuam sendo recebidos e conciliados.

Quero testes um microssegundo antes, no instante exato e um microssegundo depois. O prazo pessoal de envio continua sendo um campo separado. No simulador, o fechamento vem da fita. Em uma integração futura, deve vir do calendário e da fase aplicáveis à série, inclusive no vencimento. [B3 — horários de negociação e regras para séries vincendas](https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/horario-de-negociacao/acoes/)

## Interface, roteiro e simplificação

**15. Rótulos em português.** Quero português claro na interface. Quando o termo em inglês for o que uso no mercado, como *spread*, podemos mantê-lo. Os códigos internos permanecem estáveis. Enquanto o mesmo rótulo servir para a ordem e para a boleta, podemos compartilhá-lo. Se o sentido divergir, cada uma passa a ter seu próprio texto.

**16. Ações disponíveis no roteiro do PR06.** Entendi que o roteiro é o arquivo que faz o papel do humano no teste. O motor já sabe editar uma boleta, atualizar sua prévia, desarmar um gatilho e descartar um rascunho. O PR06 apenas não oferece essas quatro instruções no arquivo. Aceito esse recorte. Quero o comando de edição em um roteiro futuro para testar a comparação de duas borboletas e demonstrar que a decisão da versão antiga perde a validade.

**17. Simplificações e Ponytail.** Quero revisar as três sugestões em uma rodada própria, identificando cada uma pelo relatório de origem. Quero aplicar as que reduzirem a complexidade e preservarem resultados, recusas, recibos e limites de segurança. Uma candidata é evitar decodificar a mesma prévia duas vezes sem perder a validação do conteúdo. A instalação do repositório Ponytail fica como avaliação para o próximo round.

## As duas decisões específicas para concluir a revisão do PR06

**18. Boletas `T1` e `t1`.** Proponho preservar os IDs distintos no motor. Antes de publicar a saída, o comando deve verificar se o destino consegue representar todos os nomes de recibos. Se houver colisão, deve retornar código 2, explicar quais nomes colidiram e preservar os arquivos anteriores. Assim, o Linux pode gravar os dois recibos e o Mac dá uma resposta compreensível quando o volume trata os nomes como iguais.

**19. Significado de `after_seq=0`.** Proponho reservar zero para **“agir antes do primeiro evento da fita”**. Para manter essa promessa, o comando PR06 deve exigir sequências positivas nas fitas que recebe e explicar a recusa quando a primeira sequência for zero ou negativa. O leitor genérico da fase anterior pode preservar seu contrato. Quero um teste que demonstre que uma ação com `after_seq=0` acontece antes da primeira cotação.
