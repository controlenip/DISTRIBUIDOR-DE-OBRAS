# Regras e parâmetros — V17

## Carteira x produtividade

- **Em projeto + Projetista preenchido**: conta somente como carteira/carga.
- **Concluído + Data de entrega do projeto (coluna V) válida**: conta como produtividade.
- **Concluído sem data válida na coluna V**: não entra na produtividade e fica sinalizado para correção.
- A coluna V define o dia, a semana e o mês da produção.
- A meta diária não é cumulativa.

## Projeto acima da meta diária

Com a trava ativa, qualquer obra individual com **Postes Alterados/Novos maior que a meta diária de postes** é considerada uma obra de carga especial.

Para novas distribuições automáticas:

1. Essa obra só pode ser atribuída a um projetista que esteja sem outras obras com Status = Em projeto.
2. Assim que recebe essa obra, o projetista fica bloqueado para novas atribuições.
3. O bloqueio permanece enquanto a obra acima da meta continuar com Status = Em projeto.
4. Quando a carteira volta a zero porque a obra foi concluída, o projetista volta a ficar elegível para distribuição.

Essa regra existe para evitar acúmulo de demanda em carteiras com baixa vazão.
