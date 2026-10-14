# Study Agent Core 1.0 — Linha de base do tutor

## Objetivo
Registrar a qualidade inicial das respostas do tutor e comparar mudanças no prompt usando o mesmo caso de avaliação.

## Caso de avaliação
**Tema:** SQL — INNER JOIN  
**Modelo:** qwen3:1.7b (Ollama, CPU)

**Solicitação:** explicar INNER JOIN para um iniciante, usando duas tabelas pequenas, consulta SQL, explicação das linhas do resultado e uma pergunta final de compreensão sem revelar a resposta.

## Linha de base inicial

**Latência observada:** 100,24 segundos.

### Resultado observado
- A resposta apresentou um exemplo de INNER JOIN.
- A tabela de pedidos não deixou explícita a chave de relacionamento.
- A pergunta final de compreensão foi acompanhada da resposta esperada.

### Avaliação inicial
| Critério | Nota | Observação |
|---|---:|---|
| Correção técnica | 1/2 | Exemplo insuficientemente explícito sobre a chave de relacionamento. |
| Didática | 1/2 | Explicação básica, mas com oportunidade de melhoria. |
| Cumprimento das instruções | 0/2 | A resposta revelou a resposta esperada após a pergunta. |
| Aplicação prática | 1/2 | Exemplo SQL apresentado, mas incompleto em clareza. |
| **Total** | **3/8** | **Avaliação qualitativa de um único caso.** |

## Reavaliação após o primeiro ajuste de prompt

**Modelo:** qwen3:1.7b (Ollama, CPU)

**Latência observada:** 95,60 segundos.

### Resultado observado
- As tabelas explicitam as chaves de relacionamento.
- A consulta SQL apresentada é válida.
- A pergunta de compreensão termina sem revelar a resposta esperada.
- A explicação afirma incorretamente que Pedro não tem pedidos, embora a tabela contenha um pedido para `cliente_id = 3`.
- A tabela de resultado omite esse pedido, portanto não corresponde aos dados apresentados.

### Avaliação após o primeiro ajuste
| Critério | Nota | Observação |
|---|---:|---|
| Correção técnica | 1/2 | Inconsistência entre os dados, a explicação e o resultado. |
| Didática | 2/2 | Exemplo estruturado, com chaves explícitas e consulta legível. |
| Cumprimento das instruções | 2/2 | Pergunta final sem resposta revelada. |
| Aplicação prática | 2/2 | Consulta e resultado demonstrados, apesar da inconsistência. |
| **Total** | **7/8** | **Avaliação qualitativa de um único caso.** |

**Comparação:** 3/8 antes do ajuste e 7/8 depois. A latência passou de 100,24 s para 95,60 s; a diferença não comprova uma melhoria de desempenho.

**Próxima prioridade:** exigir consistência entre os dados de exemplo, a consulta SQL, a explicação e o resultado apresentado.

## Reavaliação após o segundo ajuste de prompt

**Modelo:** qwen3:1.7b (Ollama, CPU)

**Latência observada:** 82,87 segundos.

### Resultado observado
- A consulta SQL utiliza corretamente a chave de relacionamento `id_cliente`.
- Os dados das tabelas são consistentes com a consulta e com o resultado apresentado.
- A explicação descreve corretamente quais registros são mantidos pelo INNER JOIN.
- A pergunta de compreensão termina sem revelar a resposta esperada.

### Avaliação após o segundo ajuste
| Critério | Nota | Observação |
|---|---:|---|
| Correção técnica | 2/2 | Dados, consulta e resultado são coerentes. |
| Didática | 2/2 | Explicação organizada, com exemplo concreto. |
| Cumprimento das instruções | 2/2 | Pergunta final sem resposta revelada. |
| Aplicação prática | 2/2 | DDL, consulta e resultado demonstrados. |
| **Total** | **8/8** | **Avaliação qualitativa de um único caso.** |

**Comparação:** 3/8 na linha de base, 7/8 após o primeiro ajuste e 8/8 após o segundo. A latência observada caiu de 100,24 s para 95,60 s e, depois, para 82,87 s. Três observações não comprovam uma melhoria consistente de desempenho.

**Limitação:** o resultado valida apenas este caso de SQL; não comprova a mesma qualidade em outros temas.
