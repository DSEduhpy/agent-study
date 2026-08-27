# SQL Joins

## Conceito
Joins combinam linhas de tabelas relacionadas usando uma condicao de correspondencia.

## Modelo mental
Imagine duas listas com uma chave em comum: o join decide quais pares de linhas podem ser vistos juntos.

## Exemplo
`SELECT users.name, orders.total FROM users JOIN orders ON orders.user_id = users.id;`

## Como funciona
O banco avalia a condicao `ON` e produz linhas combinadas de acordo com o tipo de join.

## Quando usar
Use joins para analisar fatos junto de suas dimensoes, como pedidos e clientes.

## Contexto profissional
Analistas usam joins para construir datasets confiaveis antes de metricas e modelos.

## Erros comuns
Confundir `INNER JOIN` com `LEFT JOIN` e multiplicar linhas por causa de uma relacao um-para-muitos.

## Pratica
Compare a contagem de clientes com e sem pedidos usando `LEFT JOIN`.

## Desafio
Explique em que situacao um `LEFT JOIN` preserva informacao que um `INNER JOIN` descartaria.
