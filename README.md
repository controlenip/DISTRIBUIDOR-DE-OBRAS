# NIP Smart Distribuição — V17


## Regra de produtividade V16

A produtividade do projetista somente é contabilizada quando **Status do projeto = Concluído** e a **coluna V - Data de entrega do projeto** contém uma data válida. Projetos em **Em projeto** permanecem apenas como carteira/carga e não contam como produção. Projetos Concluídos sem data de entrega são sinalizados e ficam fora dos indicadores diário, semanal e mensal até a correção.

# NIP Smart Distribuição — V16

Aplicação em **Python + Streamlit** para distribuição equilibrada de obras entre projetistas e acompanhamento de produtividade diária, semanal e mensal.

## O que mudou na V16

Além dos recursos da V12, a V16 acrescenta dois pontos principais:

- o nome **PLN** deixa de aparecer para o usuário e passa a ser exibido como **Postes Alterados/Novos**;
- a coluna **F — PI (Tipo Projeto)** pode ser usada para distribuir projetos conforme a experiência do projetista.

### Distribuição por experiência

A ferramenta permite classificar cada projetista como:

- **Menos experiente**;
- **Intermediário**;
- **Experiente**.

E cada valor de `PI (Tipo Projeto)` pode ser classificado como:

- **Fácil**;
- **Médio**;
- **Difícil**.

Há dois modos:

- **Preferencial**: prioriza o melhor encaixe, mas pode usar outra combinação como fallback se necessário;
- **Estrito**: impede que um projetista receba um projeto classificado acima do seu nível de experiência.

Exemplo de comportamento:

- projetista menos experiente → preferência por projeto Fácil;
- projetista intermediário → preferência por projeto Médio;
- projetista experiente → preferência por projeto Difícil.

A distribuição continua considerando também equilíbrio de carteira, meta diária, teto de carga, prioridade e prazo.

## Regra principal

Meta padrão por projetista:

- 30 postes/dia;
- 5 projetos/dia;
- faixa mínima de 25 postes / 4 projetos;
- meta diária e **não cumulativa**.

A carteira ativa considera obras com:

- `Status do projeto = Em projeto`;
- campo `Projetistas` preenchido;
- peso da obra = **Postes Alterados/Novos**, lido da coluna R (`P L N`) da BASE LIST.

Uma obra pode entrar na distribuição automática quando:

- Status = `Em projeto`;
- Projetistas está vazio;
- Nota SGO está preenchida;
- Postes Alterados/Novos é maior que zero.

## Fluxo recomendado

1. Carregue `BASE_LIST.xlsx` e `PROJETISTAS.xlsx`.
2. Acesse **Distribuir obras**.
3. Se quiser, ative **Usar experiência do projetista na distribuição**.
4. Defina o nível dos projetistas e a dificuldade de cada `PI (Tipo Projeto)`.
5. Clique em **GERAR / ATUALIZAR SIMULAÇÃO**.
6. Confira/ajuste a simulação.
7. Gere e baixe a nova BASE LIST distribuída.
8. Use **LIMPAR DADOS** antes de iniciar outro ciclo.

## PROJETISTAS.xlsx

A planilha continua funcionando apenas com `Nome` e `E-mail`.

Opcionalmente, pode conter uma coluna como `Experiência`, `Nível` ou `Senioridade`. Quando existir, a ferramenta usa esse valor como ponto inicial. Se não existir, todos começam como **Intermediário** e podem ser ajustados na tela.

## Arquivo principal no Streamlit

Use:

```text
app.py
```

Todo o conteúdo deste repositório deve permanecer no GitHub. O usuário final recebe apenas o link do Streamlit.

## Segurança

Nunca coloque credenciais reais no GitHub. Use **Streamlit Secrets**.

## Testes

Execute:

```bash
pytest -q
```

A V16 inclui testes de distribuição por experiência, modo Estrito, Postes Alterados/Novos, teto de carteira, prioridade, Excel e regras de jornada.


## Novidades V17

- Página **Regras e parâmetros** reorganizada com as regras de carteira e produtividade.
- Produtividade só conta com **Status = Concluído + Data de entrega válida na coluna V**.
- Nova trava para projetos individuais acima da meta diária de postes.
- Projetista bloqueado por obra acima da meta aparece explicitamente no painel e não recebe novas atribuições.
- Projeto acima da meta só é distribuído automaticamente para carteira Em projeto zerada.
