# Bases combinadas — V19

## Regra obrigatória
A distribuição via Excel somente funciona com **BASE LIST LEVANTAMENTO + BASE LIST VU + PROJETISTAS** carregados simultaneamente.

## BASE LIST LEVANTAMENTO
Fonte completa de carteira, produtividade e carga por postes.

## BASE LIST VU
A ferramenta lê somente:
- coluna A: número do projeto;
- coluna C: status.

Somente `Em projeto` entra na fila. Como não existe quantidade de postes nessa fonte, o projeto VU vale **1 projeto** para a meta de projetos e **0 postes conhecidos** para a meta de postes.

## Duplicidade
Se o mesmo projeto existir nas duas bases, prevalece o registro do LEVANTAMENTO para evitar dupla atribuição.

## Liberação dos botões
A tela mostra 0/3, 1/3, 2/3 ou 3/3 arquivos carregados. Os botões de análise e distribuição só são liberados em 3/3.
