# Relatório — SimES: simulador de E/S e de sistema de arquivos

**Integrantes:** [nome completo do integrante 1], [nome completo do integrante 2], [nome completo do integrante 3], [nome completo do integrante 4]

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

