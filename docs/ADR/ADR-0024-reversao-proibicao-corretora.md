# ADR-0024 — Boleta ao vivo, gate humano e roteamento OpLab

- **Status:** APPROVED por Francisco quanto ao desenho. Sem vigência operacional;
  não autoriza implementação, acesso real ou ordens. Ver seção 8.
- **Dono da decisão:** Francisco.
- **Escopo:** desenho futuro do Lab de Derivativos. Vigência só nos termos da seção 8.

## 1. Decisão

O QUIMERA **preenche e atualiza a boleta e aguarda**. No piloto, Executar e
Cancelar só atuam no simulador local. Em eventual modo real, só a confirmação
humana reforçada em **Executar** autoriza a ponte a pedir à OpLab o roteamento
da ordem aprovada. **Cancelar** uma ordem real é uma decisão humana separada.
Sem segunda confirmação no chat e sem conexão direta à corretora.

A documentação pública descreve roteamento em certos fluxos, mas a capacidade
para a conta, corretora e modalidade de Francisco **não está demonstrada**.
Até homologar, a ponte de escrita é apenas um desenho futuro e permanece
desabilitada. Se a OpLab não oferecer o caminho exigido, a boleta segue útil:
Francisco pode conferir e, por sua conta, operar na interface do provedor;
o Lab não tenta outra rota.

### Degraus

| Modo | O que permite | Como entra |
|---|---|---|
| **D0 — Papel** | Motor da boleta em simulador local, com replay e sem tela, conta, credencial ou rota real. Candidato à Fase 3. | Cartão próprio aprovado, com protocolo e duração do piloto. |
| **D1 — Leitura real** | Só ler o que estiver expressamente liberado, incluindo ordens e posições reais quando aprovadas. Não envia, altera, arma nem cancela ordens. | Primeira liberação assinada, separada, com escopo, credencial e rotas somente de leitura demonstráveis. |
| **D2 — Envio e cancelamento pela ponte** | Encaminhar à OpLab ações humanas específicas, nas capacidades homologadas. | Segunda liberação assinada, independente de D1. Cada ação real ainda exige o gate humano da seção 2. |

As duas liberações de acesso real têm decisões e registros separados. Nem o
piloto, nem a aprovação deste desenho, nem acesso de leitura equivalem a
autorização para enviar uma ordem. Engatilhar é uma função, não um degrau.

A regra de arquitetura não é «a rota nunca pode ser chamada». É: **só a ponte
pode chamar rotas com efeito real, e só para cumprir a decisão humana específica
já validada**. A ponte não escolhe o que operar nem decide por conta própria.
Agentes, chat, MCP, atualização de mercado e gatilhos não têm acesso à ponte de
escrita, credenciais de ordens ou permissão de aprovar, enviar ou cancelar.

O desenho de interface fica para a Fase 4 e está fora do escopo deste ADR.

## 2. Boleta ao vivo e versão submetida ao gate

- **A tela acompanha o livro:** bid/ask e quantidade visível por perna, spread
  executável estimado no sentido da operação, débito/crédito estimado, custos
  conhecidos, horário, fonte e qualidade dos dados. Identificar o que é preço
  do livro, marcação teórica e limite da ordem; nenhum é garantia de execução.
- **A boleta é editável:** Francisco pode alterar série, lado, quantidade,
  limites por perna, limite do spread e validade, dentro do escopo da modalidade.
  Cada alteração cria uma nova versão e revalida a proposta. O campo alterado
  fica travado contra atualização automática até que ele o destrave. O livro
  segue atualizando em área separada.
- **O clique vale para o que estava na tela:** vincular a identidade humana, a
  versão da boleta, a conta mascarada, o ambiente (simulado/real), a finalidade,
  o ativo, série/vencimento, lado, lote, fator, quantidade, preço-limite de cada
  perna, débito máximo/crédito mínimo, teto bruto, exposição parcial, validade
  e dados de referência. O limite aprovado não acompanha o book.
- **Sem alteração silenciosa:** separar atualização informativa de mudança na
  proposta. Se a cotação mudar materialmente entre a exibição, o clique e o
  envio, ou se a proposta mudar, mostrar a nova versão e pedir outro clique.
  Mudanças apenas informativas, que passem na revalidação e permaneçam nas
  tolerâncias e nos limites da versão, não reescrevem a ordem. Tolerâncias,
  frescor e validade devem ser definidos no cartão de homologação, não por IA.
- **Gate em dois passos no D2:** (1) Francisco entra com login e senha locais
  do Lab na interface humana confiável. A senha da OpLab ou da corretora nunca
  é digitada no QUIMERA; (2) revisa a ação e escolhe **Confirmar** ou
  **Voltar sem enviar**. Confirmar exige verificação presencial a cada ação
  (por exemplo, Touch ID com passkey configurada para verificação do usuário),
  não apenas uma sessão autenticada ou clique local. Para cancelar, exibir
  ordem e saldo pretendido e colher uma confirmação específica. Senhas ficam
  no fluxo humano de autenticação, nunca no chat, agentes, LiteLLM ou logs.
- **Validação na ponte, não só na tela:** o desafio de uso único vincula a
  confirmação a um resumo criptográfico da versão exibida, à ação, conta,
  ambiente, rota, identificador da ordem no cancelamento e prazo. A ponte
  rejeita desafio repetido, vencido ou incompatível. O dispositivo e a
  interface confiável devem demonstrar que controle de navegador/computador
  ou sessão reaproveitada não concluem a aprovação sem presença humana.
  Sem aprovação em lote, por chat, por parâmetro de ferramenta ou por silêncio.
  A ponte revalida dados, limites, cobertura e estado antes de cada envio.
  O botão desabilitado é só a indicação visual.

## 3. Executar, Cancelar e Engatilhar

| Ação de Francisco | Efeito |
|---|---|
| **Executar** | Aprova a versão exibida. A ponte revalida e envia à operação de roteamento homologada da OpLab apenas ordens limitadas dentro do plano. A venda só pode ser enviada na proporção efetivamente coberta pela compra protetora confirmada. |
| **Cancelar / Negar** | **Descartar proposta** ou **Desarmar alerta** é ação local, sem ordem. **Cancelar saldo na OpLab** exige seleção e confirmação humanas sobre a ordem real. **Preparar desmontagem** cria outra boleta: desfazer posição executada exige nova aprovação. |
| **Engatilhar** | Arma somente uma vigilância no Lab, não uma ordem pendente no fornecedor. Na condição válida, o Lab avisa, preenche ou atualiza a boleta e aguarda outro clique humano em **Executar**. Se a oportunidade passar, a boleta continua sem envio e mostra a condição vencida ou não mais satisfeita. |

O gatilho define o ativo ou série e a fonte, evento (negócio simples, bid/ask
ou cotação do spread), lado, limiar e direção, quantidade, frescor, janela,
validade e tratamento de condição já verdadeira na ativação. Para spread,
usar os lados apropriados do livro e quantidades coerentes, não o mid ou o
último negócio como substituto de preço executável. Deduplicar alertas, não
rearmar sozinho e revalidar o gatilho no clique e antes do primeiro envio.
Com dados incompatíveis, leilão, livro incompleto, perda de sequência ou
reconexão sem estado confiável, não marcar condição atingida.

**Gatilho nativo que envia uma ordem sem novo clique fica fora desta proposta.**
A B3 distingue negócios de estratégia dos negócios das pernas: aqueles não
disparam stops da bolsa nem atualizam o último negócio dos componentes. O
cartão deve testar uma negociação de estratégia que cruza o limiar sem que o
último negócio simples o cruze; a fonte usada tem de estar explícita.

## 4. Travas do gate e da execução

**G1. Aviso de não executar.** O aviso de mercado adverso, incluindo
**Alta volatilidade** quando aplicável, permanece visível na revisão final,
com o motivo em texto, não só por cor. Alertar sobre abertura ou reabertura,
leilão, volatilidade elevada, spread aberto, pouca profundidade, movimento
rápido ou deterioração do payoff. Separar
volatilidade de mercado de incerteza do cálculo de volatilidade implícita;
uma VI não identificável nunca aparece como zero nem como sinal de segurança.
A apresentação distingue **Cuidado: não recomendado** de **Bloqueado**. No
primeiro recorte, leilão, suspensão, abertura/reabertura enquanto o mercado
não cumprir os critérios de normalização, cotação vencida, livro inválido
ou risco não verificável desabilitam Executar, inclusive no servidor. Se
volatilidade ou payoff violarem limites homologados, bloquear igualmente.
Os critérios e números vêm de cartão aprovado; sem política validada, não
habilitar execução real. Não usar a volatilidade ou uma janela de abertura
para bloquear um pedido humano de cancelamento de saldo.

**G2. Não vender sem proteção confirmada.** Em montagens elegíveis, compra
primeiro, por execução e não por envio. Em compra parcial, só a fração já
executada, conciliada e não alocada pode cobrir a venda dentro dos lotes
válidos. Conferir séries, vencimentos, quantidades e multiplicadores. A soma
de venda executada e reservada em ordens vivas não pode superar a cobertura.
Reservas são exclusivas, inclusive entre boletas concorrentes. Divergência
com a posição confirmada ou proteção não verificável bloqueia
envios afetados. Alteração de posição feita fora do QUIMERA não se confunde
com editar a boleta antes de confirmá-la. Se a proteção deixar de existir
com ordem viva, avisar e indicar o fluxo humano de cancelamento; não cancelar nem recomprar sozinho.
Na desmontagem, quando aplicável, recomprar a ponta vendida antes de liberar
a proteção. Estruturas incompatíveis com a sequência ficam indisponíveis.

**G3. Limites por perna e pelo conjunto.** Respeitar débito máximo/crédito
mínimo incluindo custos conhecidos, limites por perna, teto bruto e risco
caso só a compra execute. A compra inicial pode ficar sozinha; mostrar essa
exposição em reais antes do clique e depois de cada execução. Sem condições
para completar dentro da aprovação, não enviar novas pernas, mostrar a
posição e o saldo. Sem contraordem a mercado, troca automática de série,
fallback direto à corretora, ajuste automático de limites ou desmontagem
autônoma. A mesma confirmação cobre apenas o plano assinado e a quantidade
proporcional; o limite da venda não muda após a compra. Se sair dos limites,
parar e mostrar a posição aberta. Retomar requer nova boleta e confirmação.

**G3a. Prazo para enviar não é validade da ordem.** A boleta mostra dois
prazos antes da confirmação: até quando a ponte pode enviar as pernas e até
quando cada ordem já enviada pode ficar no livro. Vencido o primeiro prazo,
nenhuma perna nova. O segundo deve ser imposto nativamente pelo provedor:
não simular expiração com cancelamento automático e não ampliar o prazo em
silêncio. Se só existir validade até o fim do pregão, Francisco só pode
confirmar esse prazo quando ele estiver explícito e for permitido pela
política homologada. Se ele quiser um prazo menor que o provedor não garante,
a boleta não pode ser enviada. Nunca cancelar automaticamente em nome dele.

**G4. Pausar novas boletas.** Pausa humana, ou bloqueio por condição de falha
predefinida, impede novas liberações e envios ainda não feitos. A tela
continua mostrando ordens vivas, parciais, saldo e cancelamentos pendentes.
Pausar não cancela ordem na bolsa. Retomar só por decisão humana após
reconciliação e revalidação; não ressuscita aprovações vencidas.

**G5. Recibo e recuperação.** Registrar sem sobrescrever a decisão, versão
vista e aprovada, motivo e limites, IDs de roteamento e confirmações por perna,
horários, divergências e transições, sem segredos. Clique não comprova envio;
envio não comprova execução. Timeout vira **Estado incerto**, exige consultar
e conciliar no OpLab e não permite reenvio cego. **Cancelamento solicitado**
não equivale a **Cancelado**; pode haver execução no intervalo, e a confirmação
de cancelamento só vale para o saldo. Em leilão, o usuário pode pedir
cancelamento, mas a bolsa pode recusá-lo: mostrar o resultado sem esconder
a ordem viva ou uma execução posterior. Expiração da autorização de envio não
cancela uma ordem ainda dentro da validade nativa que Francisco aceitou.
Se ela aparecer viva após a própria validade nativa, sinalizar **Estado
incerto**, bloquear novos envios afetados e reconciliar. Francisco pode
solicitar o cancelamento do saldo pelo fluxo humano; não marcar como
cancelada ou expirada sem confirmação do provedor.

## 5. Fronteiras e qualificação de capacidade

- **A ponte pertence ao Lab, mas roda em processo próprio:** a integração
  determinística comunica-se diretamente com a API OpLab. Sem cliente de
  LLM, sem LiteLLM no caminho de ordens e sem plugin de navegador. LiteLLM
  pode servir à análise, não é o roteador nem recebe credenciais de ordens.
  Serviço local em `127.0.0.1` com autenticação própria; loopback sozinho
  não é barreira contra outros processos locais. A ponte recebe apenas as
  decisões verificáveis do gate e não aceita chamadas de agentes.
- **Permissões separadas:** listas de rotas em código por processo.
  Credenciais de ordens ficam fora do repositório e de qualquer processo
  com LLM/MCP. Dados de conta são **Nível 0**: não entram em prompts,
  telemetria, logs de conteúdo ou arquivos de evidência do piloto.
  A via de leitura não ganha permissão de escrita; rota capaz de enviar
  não serve para estacionar rascunhos antes da confirmação.
- **Homologar por conta, corretora, modalidade e versão:** leitura, envio
  limitado, sequência proporcional, consulta, expiração nativa e
  cancelamento são capacidades distintas. Mudança material suspende a
  capacidade afetada até reconferência. Sem prova, manter desabilitada.
  Preferir confirmação escrita do provedor e ambiente de testes isolado.
  Sem ambiente adequado nem evidência suficiente, não migrar para real
  nem usar ordem mínima como substituto de homologação.
- **Dependências de uso real:** a identificação de VI perto do intrínseco
  e a validação da convenção de dias úteis continuam pendências de outra
  fase. São pré-condições antes de usar essas métricas na boleta com dados
  reais; não bloqueiam o piloto sintético. A especificação de VI não
  integra este ADR.
- **MCP é só analítico:** sem rota, credencial ou permissão para aprovar,
  enviar, armar ordem ou cancelar.

## 6. Evidências e o que falta demonstrar

- [OpLab REST API 3.0](https://apidocs.oplab.com.br/): a rota literal
  `/orders/{id}/execute` é descrita para ordem de **portfólio, manual e pendente**.
  Isso não comprova envio à bolsa. A inclusão de ordem com conta de trade é
  descrita separadamente como capaz de rotear. O botão **Executar** descreve
  a ação da pessoa, não escolhe o nome do endpoint: antes de habilitá-lo é
  preciso provar qual operação roteia de fato, quando isso ocorre e qual
  retorno confirma envio, cancelamento ou execução. Não experimentar em conta real.
- [Manual do Robô OpLab, pp. 14–16](https://oplab.com.br/wp-content/uploads/2022/09/Manual_Robo_OpLab_20220701.pdf):
  o modo histórico de compra primeiro descreve contraordem a mercado e risco
  de desvio do spread. Não demonstra conformidade com G2/G3.
- [Manual da B3, Título II, §6.1.1, itens III–V](https://sistemasweb.b3.com.br/normativos/MPODENEGOCIACAO20260525.pdf#page=56):
  passada a janela livre, a bolsa restringe o cancelamento de ofertas que
  participam do preço teórico; um pedido não impede execução no leilão.
- [Manual de Negociação da B3, Título III, §4 VI](https://www.b3.com.br/data/files/8F/65/01/0A/6FECD910579CDBD9AC094EA8/MPO%20de%20Negociacao%20da%20B3.pdf#page=160)
  e [Circular B3 sobre UDS](https://www.b3.com.br/data/files/4D/F6/55/1F/649998109EBF7498DC0D8AA8/OC%20135-2023%20PRE%20UDS%20Mercado%20Cont%C3%ADnuo%20-%20T%C3%BAneis%20de%20Negocia%C3%A7%C3%A3o%20%28PT%29.pdf):
  o pacote nativo de negociação da B3 não é a sequência de compra primeiro.
  Avaliá-lo exigiria decisão própria e prova de suporte na OpLab. Está fora
  deste ADR; não presumir execução conjunta ou elegibilidade.

## 7. Provas exigidas para o próximo cartão

1. **Gate:** teste de arquitetura limita rotas mutantes à ponte; em simulador
   e teste integrado do gate, agente, MCP, atualização, alerta, rascunho e
   clique inválido nunca chegam à rota. Clique humano válido aciona só o
   plano autorizado. Além do teste de arquitetura, exercitar sessão
   reaproveitada, automação de clique, desafio repetido e versão trocada.
   Confirmação repetida não duplica envio; só comando humano específico
   autoriza cancelamento real.
2. **Mercado e revisão:** replay atualiza bid/ask, quantidade, spread e risco sem
   alterar campos travados nem a parte autorizável silenciosamente. Provar que
   a versão entregue à revisão final conserva o aviso de mercado adverso com
   o motivo em texto; na Fase 4, verificar que ambos permanecem visíveis.
   Testar concorrência entre confirmação e atualização, estabilidade da versão
   válida e alerta/bloqueio de mercado adverso. Testar G1 também no servidor;
   permitir cancelamento manual sob alerta mesmo quando Executar está bloqueado.
3. **Engatilhar:** cruzamento válido avisa uma vez e preenche a boleta, com zero
   chamadas de ordens até o clique; testar condição já verdadeira, ordem
   dos eventos, diferença entre negócios simples e de estratégia, cotações
   velhas, expiração e reinício sem reaproveitar alertas nem aprovação.
4. **Pernas e recuperação:** zero/parcial/total, duas boletas com a mesma
   proteção, posição alterada fora do Lab, teto bruto, rejeição, timeout e
   execução entre pedido e confirmação de cancelamento. Testar prazo de envio
   menor que a validade nativa explícita, provedor só com validade dia,
   vencimento inesperado e perna restante fora do preço assinado.
   Na simulação: compra 3 de 10, entra em leilão, pedido de cancelamento
   pendente ou recusado e mais 1 unidade executada; mostrar 4 executadas e
   6 de saldo até conciliar, sem enviar nova perna. Provar que
   pausar não envia nem cancela e que o recibo preserva os eventos conflitantes.
5. **Homologação posterior:** somente com autorização própria e ambiente
   apropriado, demonstrar as operações do provedor por modalidade e o estado
   observado na corretora. Sem prova adequada, modo real indisponível.
   O D0 é candidato à Fase 3: somente o motor da boleta em simulador local,
   sem tela. A duração e os critérios do piloto pertencem ao cartão próprio.
   Este ADR não aprova implementação nem ativação.

## 8. Governança

O gate humano tem prioridade sobre velocidade, liquidez e oportunidade. Mudar
roteamento ou desenho do gate exige **aprovação expressa de Francisco**,
revisão e registro; configuração e agente não podem contornar a regra.
Francisco pode revisar este ADR por adendos explícitos, datados e aprovados
por ele, com indicação do que substituem. Adendos não eliminam os aceites
separados de D1 e D2 nem substituem a confirmação individual da boleta.

A aprovação do desenho não altera a vedação atual de `CLAUDE.md` e do ADR-007.
Qualquer vigência operacional que conflite com essa vedação requer decisão
expressa e commit **assinado por Francisco**, que altere `CLAUDE.md` e resolva
explicitamente a vedação do ADR-007, registrada como não revisável. Enquanto
isso não for conciliado, a proibição segue vigente.

Revisar ou aceitar este texto não cria ponte, implementação, credencial,
assinatura comercial, acesso real, permissão de negociar ou autorização para
instalar dependências. Implementação e eventual ativação real têm portões
próprios. Nenhum agente executa ou cancela ordens em nome de Francisco.
