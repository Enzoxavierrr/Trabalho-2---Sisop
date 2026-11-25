# Relatório — SimES: simulador de E/S e de sistema de arquivos

**Integrantes:** [Rafael Menchik Birmann], [Enzo Pecantet Xavier], [Diego Schaeffer dos Santos], [Artur Bäuerle Schultz]

**Repositório:** [https://github.com/usuario/repositorio — link do repositório público do grupo]

## 0. Resumo

O grupo implementou o núcleo (SSTF, SCAN, polling, interrupção e o sistema de arquivos com tabelas de arquivos abertos), os módulos M1 (cache de blocos LRU e FIFO), M2 (C-SCAN, LOOK, C-LOOK e DEADLINE) e M6 (alocação encadeada, FAT e indexada) e a integração ponta a ponta. Os testes automáticos passam e os experimentos X1 a X7, X11 e X12 foram executados com as cargas padronizadas. Os três resultados mais importantes:

1. Sob carga alta, o escalonamento muda a ordem de grandeza da resposta: na carga sequencial (dois fluxos distantes), o FCFS leva a resposta média a 10.241 ms contra 17,4 ms do SSTF, porque o FCFS alterna entre as duas regiões e satura o disco (X1).
2. A alocação contígua falhou em 113 operações (ENOSPC) com 2.052 blocos livres, porque o maior trecho livre tinha só 154 blocos; a FAT foi a mais barata em acessos (1,9 por operação) e a encadeada a mais cara (77,5), por causa do acesso direto (X11).
3. A cache LRU de 1.024 blocos derrubou a resposta média do compilador sobre alocação contígua de 4.971 ms para 0,2 ms (90,4% de acertos), e fez a alocação indexada vencer a contígua na carga de banco de dados (764 ms contra 2.151 ms), pois os blocos de índice ficam na cache (X12).

## 1. Escopo realizado

| Parte | Situação | Observação |
|---|---|---|
| N1 · Dispositivo (fornecido) | usado | — |
| N2 · Subsistema de E/S (SSTF, SCAN, polling, interrupção) | completo | testes do livro conferem (236, 236 e 331 cilindros) |
| N3 · Sistema de arquivos | completo | custos de leitura e escrita conferem com as regras do enunciado; links simbólicos pertencem ao M4, não feito |
| N4 · Experimentos X1–X5 e relatório | completo | — |
| M1 · Cache de blocos | completo | LRU e FIFO, write-through e write-back, queda de energia (X6) |
| M2 · Escalonamento avançado | completo | C-SCAN, LOOK, C-LOOK e DEADLINE (X7) |
| M6 · Alocação em disco | completo | encadeada, FAT e indexada com índice de 2 níveis (X11) |
| Integração (grupos de 4) | completo | histórico de acessos → cache → escalonador (X12) |
| Bônus flash | não feito | — |

Resultado dos testes automáticos (`python3 executar.py testes`): Ran 26 tests ... OK (skipped=4). Os 4 testes pulados são dos módulos M3, M4 e M5, que o grupo não escolheu.

## 2. Implementação

### N2 — Subsistema de E/S

**Onde:** `simes/es/escalonadores.py` (classes `SSTF` e `SCAN`) e `simes/es/cpu.py` (função `custo_cpu`, modos `polling` e `interrupcao`).

**Decisões:** o SSTF escolhe a requisição de menor distância até a cabeça, com desempate pela ordem de chegada, e devolve como direção a do movimento feito. O SCAN considera "à frente" toda requisição na direção atual, inclusive no mesmo cilindro. Se não há nenhuma, vai até a borda do disco (`passar_por = [borda]`), inverte a direção e atende a mais próxima da borda. O polling custa o tempo inteiro de atendimento (espera ocupada); a interrupção custa `n_blocos * (CUSTO_INTERRUPCAO_MS + CUSTO_COPIA_MS_POR_BLOCO)`, como definido em `parametros.py`.

**Dificuldades:** o ponto delicado foi o SCAN sem requisições à frente: depois de ir à borda, todas as pendentes ficam à frente na nova direção, então basta escolher a mais próxima da borda. Os totais do exemplo do livro (fila 98, 183, 37, 122, 14, 124, 65, 67, cabeça em 53) serviram para validar.

### N3 — Sistema de arquivos

**Onde:** `simes/arquivos/sistema.py` (`resolver`, `mkdir`, `create`, `open`, `read`, `write`, `seek`, `close`, `unlink`, mais os auxiliares `_caminhar` e `_resolver_pai`).

**Decisões:** a resolução desce pela árvore lendo, a cada componente, o diretório que o contém (1 leitura), então `resolver("/a/b/c")` custa 3 leituras e as operações que alteram diretório leem também o pai. O `read` limita-se ao tamanho do arquivo; o `write` estende o arquivo pelo alocador antes de gravar, marca o FCB como sujo e, no modo `a`, começa no fim. O `close` grava o diretório pai se o FCB está sujo e só libera os blocos de um arquivo sem links quando o contador global zera, o que faz o `unlink` de arquivo aberto funcionar como no Unix. A tabela global tem uma entrada por arquivo aberto e a tabela do processo, uma por abertura.

**Dificuldades:** garantir que um erro de alocação não deixe um FCB órfão (o FCB é removido se `alocar` lança `ENOSPC`). Um handle já em uso pelo mesmo processo é rejeitado com `EINVAL`, decisão nossa, já que o enunciado não especifica esse caso.

### M1 — Cache de blocos

**Onde:** `simes/es/cache.py` (`CacheLRU`, `CacheFIFO`, base `_CacheOrdenada`).

**Decisões:** as duas políticas compartilham um `OrderedDict` bloco → sujo, com a vítima sempre no início; a LRU reposiciona o bloco no fim a cada acerto ou escrita, a FIFO não. No write-through a escrita devolve o próprio bloco para ir ao disco; no write-back o bloco fica sujo e só os sujos expulsos (ou os do `sincronizar`) vão ao disco.

**Dificuldades:** definir o comportamento de capacidade zero (a escrita em write-back vai direto ao disco), que o enunciado não cobre.

### M2 — Escalonamento avançado

**Onde:** `simes/es/escalonadores.py` (`CSCAN`, `LOOK`, `CLOOK`, `Deadline`).

**Decisões:** o C-SCAN só sobe; sem requisições acima, vai à borda, volta ao cilindro 0 (`passar_por = [max_cilindro, 0]`) e atende a de menor cilindro. O LOOK inverte na última requisição, sem ir à borda. O C-LOOK salta direto para a requisição de menor cilindro. O DEADLINE atende a de prazo mais antigo se alguma venceu e, caso contrário, delega ao SSTF. Os totais do livro (382, 299 e 322 cilindros) conferem.

**Dificuldades:** nenhuma relevante além de respeitar as regras de desempate.

### M6 — Alocação em disco

**Onde:** `simes/arquivos/alocacao.py` (`AlocadorEncadeado`, `AlocadorFAT`, `AlocadorIndexado`, base `_AlocadorDeLivres`).

**Decisões:** os três usam os primeiros blocos livres do disco. A encadeada guarda um cursor em `fcb.extra` e, no acesso ao bloco i, lê os blocos anteriores da corrente (nenhum extra na leitura sequencial). A FAT tem os mesmos blocos, com os ponteiros em memória e sem acessos extras. A indexada usa blocos de índice de 1.024 ponteiros, com 2 níveis acima disso; na passagem de 1 para 2 níveis, o índice único vira bloco de 2º nível e um novo bloco de 1º nível é colocado na frente.

**Dificuldades:** a transição de índice de 1 para 2 níveis ao estender o arquivo, e manter `fcb.extra['indices']` com o 1º nível primeiro.

### Integração

**Onde:** `simes/integracao.py` (`historico_para_requisicoes`).

**Decisões:** converte o histórico `(instante, processo, tipo, bloco, n_blocos)` em requisições ordenadas por instante (ordenação estável, então acessos da mesma operação ficam na ordem em que foram feitos) com ids 0, 1, 2...

## 3. Experimentos

> Os experimentos oficiais são os gerados por `experimentos.py`; os números abaixo vêm de `resultados/`. Tempos em ms, deslocamento em cilindros.

### X1 — Escalonadores sob quatro padrões de carga

**Hipótese:** o SSTF terá a menor resposta média e o menor deslocamento na maioria das cargas, mas a maior espera máxima (risco de inanição). O SCAN ficará entre o FCFS e o SSTF em resposta média, com espera máxima menor que a do SSTF. Em carga sequencial com dois fluxos distantes, o FCFS será o pior por alternar entre as regiões.

**Fundamentação:** Silberschatz 9ª ed., seção 10.4: o SSTF reduz o tempo de busca mas pode causar inanição; o SCAN limita a espera por varrer o disco em um sentido e inverter; o FCFS é justo, porém ignora a posição do braço.

**Configuração:** FCFS, SSTF e SCAN em HDD com interrupção, sobre as cargas `es_sequencial`, `es_aleatoria`, `es_concentrada` e `es_rajadas` (2.000 requisições cada). Mede deslocamento do braço, resposta média e p95, espera máxima e vazão.

**Resultados:**

| Carga | Esc. | Deslocamento | Resp. média | Resp. p95 | Espera máx. |
|---|---|---|---|---|---|
| sequencial | FCFS | 7.184.093 | 10.241,0 | 19.565,4 | 20.598,1 |
| sequencial | SSTF | 2.336.365 | 17,4 | 32,8 | 37,4 |
| sequencial | SCAN | 2.469.069 | 23,2 | 43,6 | 48,6 |
| aleatória | FCFS | 3.316.472 | 50,1 | 145,1 | 193,5 |
| aleatória | SSTF | 2.631.714 | 21,0 | 48,6 | 116,7 |
| aleatória | SCAN | 3.372.680 | 31,5 | 65,1 | 116,7 |
| concentrada | FCFS | 1.864.164 | 19,8 | 48,6 | 96,0 |
| concentrada | SSTF | 1.613.030 | 15,0 | 37,2 | 130,5 |
| concentrada | SCAN | 3.338.708 | 33,2 | 68,3 | 118,8 |
| rajadas | FCFS | 3.341.490 | 267,0 | 505,3 | 597,3 |
| rajadas | SSTF | 209.811 | 147,5 | 277,7 | 297,0 |
| rajadas | SCAN | 199.955 | 148,6 | 278,7 | 285,4 |

**Evidências:** `resultados/es.csv` (experimento=X1); `graficos/X1_resposta_media_ms.png`, `graficos/X1_deslocamento_total.png`, `graficos/X1_espera_max_ms.png`.

**Análise:** o SSTF teve a menor resposta média em todas as cargas, e o FCFS foi catastrófico na sequencial: as duas fontes (blocos 20.000 e 250.000) ficam a cerca de 3.600 cilindros uma da outra, então cada requisição atendida em ordem de chegada paga uma busca longa (cerca de 12 ms) mais a rotação, mais do que o intervalo entre chegadas, e a fila cresce até 10 s de espera. O SSTF e o SCAN ficam num fluxo por vez e mantêm a transferência em sequência, sem pagar a rotação. Na carga concentrada (80% dos acessos nos primeiros 20% do disco) o SCAN foi pior que o FCFS: 3,3 milhões de cilindros contra 1,9 milhão, pois cada varredura vai até a borda (cilindro 4.999) mesmo sem requisições lá. Na carga em rajadas, SSTF e SCAN praticamente empatam, porque a fila longa dá sempre uma requisição próxima. A espera máxima do SSTF só foi a maior na concentrada (130,5 contra 96,0 do FCFS); nas demais, não houve inanição visível, pois as cargas são curtas e as chegadas continuam a cada poucos ms. O deslocamento total sozinho prediz mal a resposta: na aleatória o SCAN percorreu um pouco mais que o FCFS (3,37 contra 3,32 milhões) e ainda assim respondeu mais rápido (31,5 contra 50,1 ms); nossa explicação, não testada, é que o ganho vem de atender várias requisições por varredura quando a fila está longa.

**Veredito:** PARCIALMENTE CONFIRMADA

### X2 — Polling × interrupção conforme o dispositivo

**Hipótese:** num HDD, o polling consumirá quase toda a CPU (espera ocupada durante milissegundos de busca e rotação) e a interrupção, pouco. Num dispositivo rápido, a relação se inverte: o polling custará menos que a interrupção, porque o tempo de espera passa a ser menor que o custo de tratar a interrupção.

**Fundamentação:** Silberschatz 9ª ed., seções 13.2.1 e 13.2.2: o polling é eficiente quando o dispositivo responde rápido e a espera ocupada é curta; a interrupção evita gastar CPU esperando um dispositivo lento, mas tem o custo fixo de tratar cada interrupção.

**Configuração:** FCFS sobre `es_aleatoria` e `es_sequencial`, em HDD e em dispositivo rápido (sem busca e sem rotação, 0,008 ms por bloco), nos dois modos. Mede a porcentagem de CPU gasta com E/S.

**Resultados:**

| Carga | Dispositivo | CPU polling | CPU interrupção |
|---|---|---|---|
| aleatória | HDD | 86,28% | 1,12% |
| sequencial | HDD | 100,00% | 0,84% |
| aleatória | rápido | 0,53% | 1,12% |
| sequencial | rápido | 1,07% | 2,28% |

**Evidências:** `resultados/es.csv` (experimento=X2); `graficos/X2_cpu.png`.

**Análise:** no HDD o polling ocupa a CPU durante todo o atendimento, então a porcentagem acompanha a utilização do disco: 86% na aleatória e 100% na sequencial (disco saturado, ver X1). A interrupção custa cerca de 1% porque paga só 0,017 ms por bloco. No dispositivo rápido, o atendimento de 8 blocos dura cerca de 0,064 ms, enquanto a interrupção custa 8 × 0,017 = 0,136 ms: o polling gasta cerca de metade da CPU da interrupção (0,53% contra 1,12%). O ponto de equilíbrio do modelo é o atendimento durar o mesmo que o custo por bloco da interrupção (0,017 ms por bloco). A resposta média foi idêntica entre os modos, pois o custo de CPU não entra no tempo de atendimento do disco no simulador.

**Veredito:** CONFIRMADA

### X3 — Acesso sequencial × direto

**Hipótese:** o compilador (leitura sequencial) e o banco de dados (acesso direto) farão quantidades parecidas de acessos por operação de leitura e escrita (1 bloco), mas o tempo por operação do banco de dados será várias vezes maior, porque cada acesso direto paga busca e latência rotacional enquanto a leitura sequencial só paga a transferência.

**Fundamentação:** Silberschatz 9ª ed., seções 11.2 (métodos de acesso) e 12.4: no acesso sequencial o próximo bloco está logo depois do anterior; no direto, a posição é arbitrária. O modelo de custo do disco (`parametros.py`) zera a rotação quando o bloco é o seguinte ao último transferido.

**Configuração:** cargas `fs_compilador` (leitura sequencial de fontes, 3 compilações) e `fs_banco_dados` (tabela de 64 MiB com leituras e gravações em posições aleatórias, mais um log), com alocação contígua. Mede acessos e tempo por operação.

**Resultados:**

| Operação | Compilador: acessos / tempo (ms) | Banco de dados: acessos / tempo (ms) |
|---|---|---|
| read | 1,0 / 1,48 | 1,0 / 5,49 |
| write | 1,0 / 0,91 | 1,0 / 5,54 |
| open | 3,0 / 8,20 | 2,0 / 4,25 |

**Evidências:** `resultados/arquivos_por_operacao.csv` (experimento=X3); `resultados/arquivos.csv` (experimento=X3); `graficos/X3_tempo_por_operacao.png`.

**Análise:** os acessos por leitura e escrita são iguais (1 bloco), mas o tempo de leitura do banco é 3,7 vezes o do compilador (5,49 contra 1,48 ms) e o da escrita, 6 vezes (5,54 contra 0,91 ms), pela busca e pela rotação a cada acesso aleatório. No compilador, os blocos consecutivos de um arquivo evitam a rotação e deixam o `read` próximo do custo de transferência. O `open` do compilador custa mais (3 acessos contra 2) porque os arquivos estão em `/src/...`, mais fundo na árvore que o arquivo do banco de dados.

**Veredito:** CONFIRMADA

### X4 — Custo de resolver caminhos conforme a profundidade

**Hipótese:** o número de acessos do `open` crescerá linearmente com a profundidade do caminho (um por diretório mais o da raiz), e o tempo do `open` crescerá proporcionalmente. A leitura depois do `open` não dependerá da profundidade.

**Fundamentação:** Silberschatz 9ª ed., seção 11.3 (estrutura de diretórios) e 11.5.1 (operações): resolver um caminho exige localizar cada componente no diretório que o contém.

**Configuração:** um arquivo no fim de uma cadeia de 1 a 10 diretórios, aberto 20 vezes, em cada profundidade. Mede acessos e tempo por `open`.

**Resultados:**

| Profundidade | Acessos por open | Tempo por open (ms) | Acessos por read |
|---|---|---|---|
| 1 | 2 | 4,25 | 1 |
| 2 | 3 | 4,29 | 1 |
| 5 | 6 | 4,41 | 1 |
| 10 | 11 | 4,61 | 1 |

**Evidências:** `resultados/arquivos_por_operacao.csv` (experimento=X4); `graficos/X4_open_por_profundidade.png`.

**Análise:** os acessos crescem linearmente, de 2 a 11, exatamente profundidade + 1. O tempo, porém, cresce só 0,04 ms por nível (4,25 para 4,61 ms, cerca de 8% em 10 níveis), muito menos que proporcional: os diretórios foram alocados em blocos consecutivos, então a leitura de cada um é sequencial em relação ao anterior, sem busca nem rotação, e só paga a transferência de 0,04 ms. A primeira leitura (a raiz) paga o custo cheio. O `read` não depende da profundidade (1 acesso). O resultado depende do layout: diretórios espalhados pelo disco custariam uma busca por nível. Isso justifica a existência da dentry cache nos sistemas reais, que evita reler diretórios.

**Veredito:** PARCIALMENTE CONFIRMADA

### X5 — Tabelas de arquivos abertos com vários processos

**Hipótese:** com vários processos abrindo os mesmos arquivos, a tabela global terá menos entradas que a soma das entradas das tabelas por processo (uma entrada global por arquivo, uma por processo por abertura), e o contador de aberturas de um arquivo popular ficará acima de 1 e nunca passará do número de processos.

**Fundamentação:** Silberschatz 9ª ed., seção 11.1.3 (arquivos abertos): tabela global com uma entrada por arquivo aberto e contador, tabela por processo com posição e modo.

**Configuração:** carga `fs_servidor_web`: 12 páginas e 8 trabalhadores; em cada uma das 40 rodadas, cada trabalhador sorteia 3 páginas, abre, lê e fecha. Mede o tamanho máximo da tabela global, o máximo por processo, a soma máxima das tabelas por processo e o contador máximo de aberturas.

**Resultados:**

| Indicador | Máximo |
|---|---|
| Tabela global (arquivos distintos abertos) | 12 |
| Tabela por processo (maior) | 3 |
| Soma das tabelas por processo | 24 |
| Contador de aberturas de um arquivo | 6 |

**Evidências:** `resultados/arquivos.csv` (experimento=X5); `graficos/X5_tabelas.png`.

**Análise:** a soma das tabelas por processo (24) é o dobro da global (12), o que mostra o compartilhamento: um mesmo arquivo aparece uma vez na global e uma vez em cada processo que o abriu. Os 12 arquivos distintos são as 12 páginas, e os 24 da soma são 8 trabalhadores × 3 aberturas. O contador chegou a 6 aberturas simultâneas do mesmo arquivo, abaixo dos 8 trabalhadores, o que decorre do sorteio: cada trabalhador escolhe uma dada página com probabilidade 3/12, então a média esperada é 2 aberturas por página, e 6 é um pico. As posições (por processo) são independentes: um `read` em um processo não move a posição de outro, o que o teste automático do núcleo confere.

**Veredito:** CONFIRMADA

### X6 — Cache de blocos (M1)

**Hipótese:** a LRU terá mais acertos que a FIFO com capacidades pequenas e a diferença sumirá com capacidades grandes; os acertos crescerão com a capacidade até um limite. O write-back reduzirá as escritas físicas e o tempo de resposta em relação ao write-through, mas perderá dados numa queda de energia, enquanto o write-through não perde nenhum.

**Fundamentação:** Silberschatz 9ª ed., seções 13.4.3 (caching) e 12.6 (eficiência e desempenho): a cache evita acessos ao disco; o write-back adia a gravação, diminuindo a E/S, ao preço da integridade em falhas.

**Configuração:** carga `es_reuso` (3.000 requisições de 1 bloco, Zipf sobre 4.000 blocos, 65% de leituras), FCFS, HDD, sem cache e com LRU e FIFO de 64 a 2.048 blocos, em write-through e write-back. A queda de energia ocorre no instante da requisição do meio (11.733 ms). A sincronização do write-back é a cada 5 s.

**Resultados:**

| Cache | Capacidade | Escrita | Acertos | Escritas físicas | Resp. média | Espera máx. | Perdidos na queda |
|---|---|---|---|---|---|---|---|
| nenhuma | — | — | — | 1.045 | 3.500,0 | 6.936,3 | 0 |
| LRU | 64 | write-through | 39,6% | 1.045 | 74,7 | 257,8 | 0 |
| FIFO | 64 | write-through | 31,3% | 1.045 | 436,1 | 885,5 | 0 |
| LRU | 128 | write-through | 48,8% | 1.045 | 33,4 | 158,0 | 0 |
| FIFO | 128 | write-through | 42,6% | 1.045 | 51,7 | 247,6 | 0 |
| LRU | 256 | write-back | 57,7% | 543 | 47,4 | 1.271,1 | 55 |
| LRU | 256 | write-through | 57,7% | 1.045 | 22,0 | 151,8 | 0 |
| LRU | 1.024 | write-back | 67,0% | 541 | 39,1 | 1.416,8 | 55 |
| LRU | 1.024 | write-through | 67,1% | 1.045 | 16,9 | 151,8 | 0 |
| FIFO | 1.024 | write-back | 67,0% | 541 | 39,7 | 1.425,7 | 55 |
| LRU | 2.048 | write-through | 67,1% | 1.045 | 16,9 | 151,8 | 0 |

**Evidências:** `resultados/es.csv` (experimento=X6); `graficos/X6_acerto.png`, `graficos/X6_escrita.png`.

**Análise:** com 64 e 128 blocos, a LRU acertou mais que a FIFO (39,6% contra 31,3% e 48,8% contra 42,6%), pois a carga é Zipf e os blocos populares têm de ficar na cache, o que a FIFO não garante porque expulsa o mais antigo, mesmo que muito usado. Com 1.024 blocos ou mais, as duas empatam em 67%, provavelmente o limite imposto pelas leituras de blocos ainda não vistos (faltas obrigatórias); a partir daí, mais capacidade não ajuda (1.024 e 2.048 deram resultados idênticos). O write-back reduziu as escritas físicas de 1.045 para cerca de 541 a 715 (queda de 22% a 48%), porque várias escritas ao mesmo bloco viram uma. O custo foi perder 22 a 55 blocos sujos na queda, contra zero no write-through. A parte inesperada: com capacidades de 256 ou mais, o write-back teve resposta média pior que o write-through (47,4 contra 22,0 ms) e espera máxima de mais de 1.200 ms. Nossa explicação, não verificada com outra medição, é que a sincronização a cada 5 s joga uma rajada de gravações no disco de uma vez, e as leituras que chegam durante ela esperam. Sem cache, a resposta média foi de 3.500 ms: o disco satura, pois a carga chega a cada 8 ms em média e o atendimento aleatório leva cerca de 10 ms.

**Veredito:** PARCIALMENTE CONFIRMADA

### X7 — Escalonadores avançados e inanição (M2)

**Hipótese:** com a carga crescendo, o FCFS será o primeiro a degradar. O SSTF terá a melhor resposta média, mas a maior espera máxima. O C-SCAN terá a espera máxima mais uniforme (menor), ao custo da resposta média, por visitar as bordas. O LOOK será melhor que o SCAN (sem viagem à borda), e o DEADLINE ficará perto do SSTF na média, mas com espera máxima menor.

**Fundamentação:** Silberschatz 9ª ed., seção 10.4: o C-SCAN dá tempo de espera mais uniforme que o SCAN; LOOK e C-LOOK evitam ir à borda sem necessidade; a documentação do mq-deadline do Linux descreve prazos por requisição para impedir inanição.

**Configuração:** carga `concentrada` com semente 7 e 2.000 requisições, com intervalo médio entre chegadas de 14, 11, 9 e 8 ms (carga crescente), nos sete escalonadores (FCFS, SSTF, SCAN, C-SCAN, LOOK, C-LOOK, DEADLINE). Mede resposta média, p95 e espera máxima.

**Resultados:** carga mais alta (intervalo de 8 ms):

| Escalonador | Deslocamento | Resp. média | Resp. p95 | Espera máx. |
|---|---|---|---|---|
| FCFS | 1.811.896 | 281,6 | 538,0 | 616,2 |
| SSTF | 1.150.844 | 27,8 | 79,6 | 327,1 |
| SCAN | 1.529.626 | 49,0 | 116,6 | 226,7 |
| C-SCAN | 1.589.526 | 65,8 | 142,1 | 223,1 |
| LOOK | 1.165.152 | 31,4 | 87,5 | 170,3 |
| C-LOOK | 1.258.318 | 38,9 | 100,2 | 163,8 |
| DEADLINE | 1.148.860 | 28,4 | 84,8 | 244,8 |

Resposta média por intervalo (14 / 11 / 9 / 8 ms): FCFS 15,8 / 26,5 / 61,2 / 281,6; SSTF 13,4 / 16,7 / 21,9 / 27,8; DEADLINE 13,4 / 16,7 / 22,0 / 28,4. Espera máxima do SSTF e do DEADLINE a 9 ms: 265,5 e 204,2; a 8 ms: 327,1 e 244,8.

**Evidências:** `resultados/es.csv` (experimento=X7); `graficos/X7_resposta_p95_ms.png`, `graficos/X7_espera_max_ms.png`.

**Análise:** o FCFS degrada de forma explosiva: a resposta média vai de 15,8 para 281,6 ms (18 vezes) quando o intervalo cai de 14 para 8 ms, enquanto o SSTF só dobra (13,4 para 27,8 ms). O SSTF é o melhor em média, mas tem a maior espera máxima entre os algoritmos que olham a posição (327 ms), contra 164 a 245 ms nos demais. Quem tem a menor espera máxima é o C-LOOK (163,8 ms) e o LOOK (170,3 ms), e o LOOK tem média só 13% pior que a do SSTF (31,4 contra 27,8 ms), o melhor compromisso entre média e justiça nesta carga. O C-SCAN, apesar do nome ligado à uniformidade, foi o pior em média entre os não-FCFS (65,8 ms) porque a carga é concentrada nos primeiros 20% do disco e ele faz viagens completas até a borda e de volta. O DEADLINE acompanhou o SSTF na média (28,4 contra 27,8 ms) e reduziu a espera máxima em 25% a 8 ms e 23% a 9 ms. Com 11 e 14 ms, os prazos nunca venceram e o DEADLINE foi idêntico ao SSTF. A espera máxima do DEADLINE (245 ms) ainda passa do prazo de leitura de 200 ms, pois uma vez que várias requisições vencem, elas esperam atrás umas das outras, de modo que o prazo limita a inanição, mas não garante o teto.

**Veredito:** PARCIALMENTE CONFIRMADA

### X11 — Métodos de alocação (M6)

**Hipótese:** a alocação contígua terá o menor número de acessos por operação, mas sofrerá fragmentação externa: com o disco cheio, falhará em criar ou estender arquivos mesmo com blocos livres suficientes, e as realocações custarão cópias de blocos. A encadeada terá o pior custo de acesso direto (percorre a corrente). A FAT eliminará esse custo (ponteiros em memória). A indexada ficará no meio, com 1 a 2 leituras extras por acesso e uma pequena fração do espaço (cerca de 1%) para índices.

**Fundamentação:** Silberschatz 9ª ed., seções 12.4 (métodos de alocação) e 12.5 (gerenciamento de espaço livre): a contígua sofre fragmentação externa; a encadeada é ruim para acesso direto; a FAT melhora a encadeada mantendo a tabela em memória; a indexada suporta acesso direto ao custo de blocos de índice.

**Configuração:** carga `fs_alocacao` (criação e remoção de muitos arquivos até encher a partição, crescimento e acessos) numa partição de 20.000 blocos, com os quatro alocadores. Mede acessos e tempo por operação, falhas, realocações e fragmentação.

**Resultados:**

| Alocador | Erros (ENOSPC) | Acessos totais | Acessos por op. | Tempo por op. (ms) | Tempo total (s) | Realocações | Maior trecho livre | Blocos livres no fim |
|---|---|---|---|---|---|---|---|---|
| contígua | 113 | 18.151 | 7,35 | 34,55 | 85,3 | 59 | 154 | 2.052 |
| encadeada | 0 | 191.309 | 77,52 | 12,73 | 31,4 | 0 | 1.939 | 1.939 |
| FAT | 0 | 4.690 | 1,90 | 4,01 | 9,9 | 0 | 1.939 | 1.939 |
| indexada | 0 | 10.585 | 4,29 | 14,32 | 35,3 | 0 | 1.805 | 1.805 |

**Evidências:** `resultados/arquivos.csv` (experimento=X11); `graficos/X11_alocacao.png`, `graficos/X11_fragmentacao.png`.

**Análise:** a contígua falhou em 113 operações (4,6% das 2.468) com 2.052 blocos livres (10% da partição), porque estavam em 50 trechos e o maior tinha só 154 blocos: é a fragmentação externa. As 59 realocações (cópia do arquivo inteiro) fizeram a contígua ter o maior tempo por operação (34,55 ms), apesar de usar poucos acessos por operação em média. A encadeada, por outro lado, teve 77,5 acessos por operação, pelo acesso direto percorrer a corrente, mas não falhou. A FAT, com os mesmos blocos e ponteiros em memória, teve o menor custo (1,9 acessos, 4,0 ms por operação): é 40 vezes menos acessos que a encadeada. A indexada teve 4,29 acessos por operação, mas um tempo por operação (14,32 ms) maior que o da encadeada (12,73 ms), contra a hipótese: provavelmente porque a corrente da encadeada lê blocos vizinhos em sequência, e o modelo de disco não cobra rotação quando o bloco lido é o seguinte ao anterior, enquanto cada leitura de índice da indexada cai num bloco isolado, que paga busca e rotação (explicação não verificada). O espaço dos índices aparece nos blocos livres no fim (1.805 contra 1.939, cerca de 0,7% da partição).

**Veredito:** PARCIALMENTE CONFIRMADA

### X12 — Integração ponta a ponta

**Hipótese:** a cache terá efeito enorme na carga do compilador (muito reuso de cabeçalhos e fontes) e menor no banco de dados (acessos aleatórios com pouco reuso). A alocação indexada piorará a resposta sem cache (mais requisições, os blocos de índice), mas, com cache, os blocos de índice, muito reusados, serão acertos. O escalonador fará pouca diferença quando os acessos estão num trecho pequeno do disco (compilador) e mais diferença no acesso aleatório (banco de dados).

**Fundamentação:** Silberschatz 9ª ed., seções 12.6 e 13.4.3: o desempenho do sistema de arquivos depende do layout dos blocos e da cache; o escalonamento só ajuda quando há deslocamento do braço a economizar.

**Configuração:** cada carga de arquivos (`compilador`, `banco_dados`) roda no sistema de arquivos com alocação contígua e indexada, guardando o histórico de acessos ao disco; o histórico vira requisições de E/S, que passam por FCFS, SSTF e SCAN, sem cache e com cache LRU de 1.024 blocos em write-back.

**Resultados:** resposta média (ms) e acertos de cache:

| Carga + alocação | Requisições | FCFS sem cache | SSTF sem cache | FCFS com cache | Acertos |
|---|---|---|---|---|---|
| compilador + contígua | 5.400 | 4.970,9 | 5.170,1 | 0,2 | 90,4% |
| compilador + indexada | 11.705 | 14.961,0 | 10.563,6 | 0,2 | 95,7% |
| banco de dados + contígua | 3.610 | 6.158,8 | 4.106,2 | 2.150,6 | 4,9% |
| banco de dados + indexada | 10.314 | 22.146,1 | 17.353,2 | 764,3 | 74,5% |

Com cache, o SCAN percorreu 49.996 cilindros no compilador + contígua, contra 104 do FCFS e 80 do SSTF.

**Evidências:** `resultados/es.csv` (experimento=X12); `graficos/X12_resposta.png`.

**Análise:** o compilador, com muito reuso de arquivos já lidos, passa a 90,4% de acertos com 1.024 blocos, o que derruba a resposta de 4.970,9 para 0,2 ms. O banco de dados sobre alocação contígua só atinge 4,9% de acertos (cada acesso é a um bloco quase novo da tabela de 64 MiB), e a cache melhora a resposta (6.158,8 para 2.150,6 ms), mas muito menos. A alocação indexada duplicou ou triplicou o número de requisições (11.705 contra 5.400; 10.314 contra 3.610) e piorou a resposta sem cache (14.961 contra 4.971 ms no compilador; 22.146 contra 6.159 ms no banco), por causa das leituras do bloco de índice. Com cache, porém, os índices viram acertos: no banco de dados a indexada chegou a 74,5% de acertos e 764,3 ms de resposta, melhor que a contígua (2.150,6 ms), o resultado mais importante da integração, que só aparece quando as camadas são medidas juntas. O efeito do escalonador dependeu da carga: no banco de dados, sem cache, o SSTF reduziu a resposta em 33% na contígua (6.158,8 para 4.106,2 ms) e em 22% na indexada (22.146,1 para 17.353,2 ms), pois os acessos aleatórios à tabela pedem deslocamento do braço; no compilador o deslocamento é de poucos cilindros e a resposta é dominada pela rotação (4,17 ms por acesso fora de sequência), e o SSTF ficou até um pouco pior que o FCFS no compilador + contígua (5.170,1 contra 4.970,9 ms), provavelmente porque reordena requisições consecutivas do mesmo arquivo e quebra a sequência de blocos (explicação não verificada). Com cache, o SCAN foi pior em deslocamento (49.996 cilindros), pois cada falta que sobra o faz ir até a borda, mesmo que quase todas as requisições sejam absorvidas pela cache.

**Veredito:** PARCIALMENTE CONFIRMADA

## 4. Relação com sistemas reais

**Escalonadores de E/S (X1, X7).** O Linux tem o `mq-deadline`, que é o DEADLINE do M2 com prazos de 500 ms para leitura e 5 s para escrita, o BFQ, que prioriza justiça entre processos, e o `none`, comum em NVMe. O `none` é coerente com o X2: num dispositivo sem partes móveis não há braço a otimizar, e o escalonamento só acrescenta custo de CPU. O resultado do X7, em que o DEADLINE acompanha a média do SSTF e limita parte da inanição, ajuda a entender por que prazos por requisição existem no `mq-deadline`. O Windows e o macOS não expõem essa escolha, mas também reordenam as requisições por posição no disco.

**Polling e interrupção (X2).** Drivers de NVMe modernos no Linux oferecem polling para dispositivos de latência muito baixa, o que repete a conclusão do X2: com espera curta, o custo de tratar a interrupção supera o de esperar.

**Cache e gravação periódica (X6, X12).** O Linux mantém um cache de páginas com gravação diferida: o `flusher` grava as páginas sujas periodicamente (por padrão, acorda a cada 5 s, parâmetro `dirty_writeback_centisecs`), e é o análogo do `INTERVALO_SYNC_MS`. A rajada de gravações do X6 reproduz o motivo de o kernel limitar e suavizar a gravação (os limites `dirty_ratio`). O Windows tem o Cache Manager com escrita preguiçosa, e o macOS, o cache de buffers unificado com a memória virtual. O X4 relaciona-se com a cache de diretórios (dentry cache) do Linux, que evita as releituras de diretório medidas no `open`.

**Alocação (X11).** A alocação contígua com fragmentação lembra os extents do ext4 e do NTFS, que usam trechos contíguos grandes, mas permitem vários trechos por arquivo, evitando a falha do alocador contíguo puro. A indexada com blocos de índice é a estrutura do i-node dos sistemas ext2 e ext3 (ponteiros diretos e indiretos); o ext4 a substituiu por extents. A FAT é a estrutura de pendrives e cartões (FAT32 e exFAT), cuja tabela é mantida em memória justamente para evitar o custo da encadeada pura medido no X11. O APFS usa estruturas de árvore com cópia na escrita, que o simulador não modela.

## 5. Limitações do simulador

5. Limitações do simulador
- O disco é único, de tempos fixos e sem fila no dispositivo: não há cache de trilha, reordenação interna da controladora (NCQ) nem variação da rotação por posição. O resultado do X1, em que a rotação domina, pode ser exagerado ou atenuado num disco real.
- As cargas são sintéticas, com semente fixa: os efeitos de X6 e X12 dependem da distribuição escolhida (Zipf no X6). Uma única semente impede dar intervalos de confiança.
- O simulador de E/S conta o custo da CPU, mas ele não retarda o disco, então polling e interrupção têm a mesma resposta (X2). Num sistema real, a CPU ocupada afetaria o resto.
- O sistema de arquivos não tem cache de diretórios nem de metadados, então o open mede o pior caso (X4), e o close grava o diretório pai literalmente como no enunciado.
- Na integração (X12), o histórico do sistema de arquivos vira requisições com os instantes originais da carga, sem retroalimentação: se o disco demora, as operações seguintes não atrasam, como atrasariam num sistema real, o que exagera a fila sem cache.
- No X11, é uma única execução de uma carga com semente fixa: as diferenças pequenas (por exemplo, 12,73 contra 14,32 ms por operação) devem ser lidas como indícios.
- Não foram implementados M3, M4, M5 nem o bônus de flash; as conclusões não cobrem DMA, links nem proteção.

## 6. Conclusões

1. A política de escalonamento importa mais quanto mais o disco está saturado: na carga sequencial o FCFS levou a resposta a cerca de 600 vezes a do SSTF (10.241 contra 17,4 ms), e na carga crescente do X7 o FCFS ficou 18 vezes pior ao subir a carga, contra 2 vezes do SSTF.
2. Não existe escalonador que vença em tudo: o SSTF tem a melhor média, mas a maior espera máxima entre os que olham a posição; o SCAN e o C-SCAN perdem em cargas concentradas por visitarem as bordas; o LOOK e o C-LOOK dão o melhor compromisso entre média e espera máxima; o DEADLINE mantém a média do SSTF e reduz a espera máxima, sem garantir um teto.
3. A cache é a otimização mais eficaz do trabalho (resposta de 4.971 para 0,2 ms no compilador), e a política de escrita troca E/S por risco: o write-back reduziu as escritas físicas em até 48% à custa de perder até 55 blocos numa queda, e a sincronização periódica piorou a espera máxima.
4. A alocação contígua pura é rápida enquanto há espaço contíguo, mas a fragmentação externa a fez falhar com 10% do disco livre; a FAT deu o melhor custo de acesso (1,9 por operação), desde que a tabela caiba em memória, e a encadeada pura só é viável para acesso sequencial (77,5 acessos por operação).
5. Os resultados dependem da interação entre camadas: a alocação indexada é pior que a contígua sem cache e melhor com cache no banco de dados (764 contra 2.151 ms). Medir as camadas isoladas daria a conclusão oposta.
6. O custo de resolver caminhos cresce linearmente em acessos (profundidade + 1), mas o tempo cresce pouco por nível, o que mostra por que os sistemas reais mantêm uma cache de diretórios.

## 7. Referências

- SILBERSCHATZ, A.; GALVIN, P. B.; GAGNE, G. *Operating System Concepts*. 9. ed. Wiley, 2013.
- Documentação do kernel Linux sobre escalonadores de E/S: mq-deadline e BFQ (https://docs.kernel.org/block/index.html).
- Documentação do Python: `collections.OrderedDict` (https://docs.python.org/3/library/collections.html#collections.OrderedDict).
- Documentação do kernel Linux, parâmetros de gravação de páginas sujas (`vm.dirty_*`) (https://docs.kernel.org/admin-guide/sysctl/vm.html).

## 8. Declaração de autoria e uso de IA

**Quem fez o quê:**
| Parte implementada pelo grupo | Onde | Responsável(is) |
|---|---|---|
| N2 — escalonadores SSTF e SCAN | `simes/es/escalonadores.py` | [Enzo Pecantet Xavier] |
| N2 — custo de CPU por polling e interrupção | `simes/es/cpu.py` | [Diego Schaeffer dos Santos] |
| N3 — resolução de caminhos, `mkdir`, `create`, `open`, `read`, `write`, `seek`, `close`, `unlink` e tabelas de arquivos abertos | `simes/arquivos/sistema.py` | [Diego Schaeffer dos Santos] |
| M1 — cache LRU e FIFO, write-through e write-back | `simes/es/cache.py` | [Enzo Pecantet Xavier] |
| M2 — C-SCAN, LOOK, C-LOOK e DEADLINE | `simes/es/escalonadores.py` | [Rafael Menchik Birmann] |
| M6 — alocação encadeada, FAT e indexada | `simes/arquivos/alocacao.py` | [Artur Bäuerle Schultz] |
| Integração ponta a ponta | `simes/integracao.py` | [Enzo Pecantet Xavier] |
| Execução dos experimentos e dos gráficos, hipóteses e análises | `resultados/`, `graficos/`, `RELATORIO.md` seção 3 | [Rafael Menchik Birmann] |
| Relatório | `RELATORIO.md` | [Artur Bäuerle Schultz, Enzo Pecantet Xavier, Diego Schaeffer dos Santos e Rafael Menchik Birmann] |

**Uso de ferramentas de IA:**

| Ferramenta | Finalidade | Onde foi usada (arquivos ou seções) |
|---|---|---|
| Claude Code (Claude Sonnet 5.5) | Rascunho inicial do núcleo (N2 e N3) a partir do que foi compreendido nos materiais de estudos disponibilizados pelo professor, explicar o código inicial do projeto, além de consultas pontuais e esclarecimento de dúvidas técnicas nos demais módulos, com revisão e ajustes manuais. | `simes/es/escalonadores.py`, `simes/es/cpu.py`, `simes/es/cache.py`, `simes/arquivos/sistema.py`, `simes/arquivos/alocacao.py`, `simes/integracao.py` |

