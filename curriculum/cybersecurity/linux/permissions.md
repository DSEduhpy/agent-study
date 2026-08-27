# Linux File Permissions

## Conceito
Permissoes controlam quem pode ler, escrever ou executar um arquivo.

## Modelo mental
Pense em tres grupos: proprietario, grupo e outros. Cada grupo recebe as capacidades read, write e execute.

## Exemplo
`chmod 640 relatorio.txt` permite leitura e escrita ao proprietario, leitura ao grupo e nenhum acesso aos demais.

## Como funciona
O sistema verifica as permissoes do arquivo e a identidade efetiva do processo antes de autorizar uma operacao.

## Quando usar
Use permissoes para limitar acesso a configuracoes, logs e dados sensiveis.

## Contexto profissional
Em servidores, permissoes incorretas podem expor segredos ou permitir alteracoes indevidas em scripts.

## Erros comuns
Conceder `777` por conveniencia e esquecer que permissoes de diretorios tambem controlam navegacao.

## Pratica
Crie um arquivo temporario e compare `ls -l` antes e depois de usar `chmod`.

## Desafio
Explique por que um arquivo pode ser legivel, mas ainda assim inacessivel quando o diretorio pai nao permite travessia.
