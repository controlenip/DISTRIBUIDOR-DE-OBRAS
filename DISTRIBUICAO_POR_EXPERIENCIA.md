# Distribuição por experiência — V13

A V13 pode usar a coluna **F — PI (Tipo Projeto)** para diferenciar a dificuldade das obras.

## 1. Nível do projetista

Cada projetista pode ser marcado como:

- Menos experiente
- Intermediário
- Experiente

A configuração pode ser feita diretamente no Streamlit. Opcionalmente, `PROJETISTAS.xlsx` pode conter uma coluna `Experiência`, `Nível` ou `Senioridade`.

## 2. Dificuldade do PI

Cada valor encontrado em `PI (Tipo Projeto)` pode ser classificado como:

- Fácil
- Médio
- Difícil

A ferramenta não presume que um código específico é fácil ou difícil. Essa classificação é definida pelo usuário da ferramenta.

## 3. Modos

### Preferencial

Prioriza o encaixe exato entre experiência e dificuldade. Se não houver combinação ideal, permite fallback para manter a distribuição funcionando.

### Estrito

Não permite projeto acima do nível do projetista:

- Menos experiente: somente Fácil
- Intermediário: Fácil ou Médio
- Experiente: Fácil, Médio ou Difícil

Mesmo no modo Estrito, o algoritmo tende a reservar os projetos mais difíceis para os projetistas mais experientes porque o encaixe exato recebe prioridade.

## 4. Demais regras continuam valendo

O critério de experiência não substitui:

- equilíbrio de carteira;
- meta de 30 postes / 5 projetos;
- teto de carteira;
- prioridade e prazo;
- bloqueio de obra sem Nota SGO;
- bloqueio de obra sem Postes Alterados/Novos;
- proteção contra redistribuição de obra já atribuída.
