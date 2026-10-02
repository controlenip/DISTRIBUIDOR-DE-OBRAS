# NIP Smart Distribuição — V9

Aplicação **Python + Streamlit** focada exclusivamente em **produtividade dos projetistas** e **distribuição igualitária de projetos de rede de distribuição**.

## Objetivo

A ferramenta lê a `BASE LIST.xlsx` e a `PROJETISTAS.xlsx`, identifica a carteira já atribuída a cada projetista, calcula quanto falta para a meta diária e distribui automaticamente as obras disponíveis de forma balanceada.

A ferramenta **não acompanha produtividade de levantadores**. As colunas O, P e Q da BASE LIST não participam dos indicadores nem da distribuição.

## Metas operacionais

- 25 a 30 postes por dia;
- 4 a 5 projetos por dia;
- jornada: 08:00–12:00 e 13:12–18:00;
- 528 minutos produtivos por dia;
- meta diária não cumulativa.

O excedente de um dia é registrado apenas como desempenho e não reduz a meta do dia seguinte.

## Colunas principais da BASE LIST

| Coluna | Campo | Uso |
|---|---|---|
| A | Nº da nota | solicitação do cliente |
| C | Nota SGO | número utilizado pelo projetista para iniciar o projeto |
| E | Status do projeto | somente `Em projeto` entra na carteira de distribuição |
| R | P L N | quantidade de postes da obra e peso usado na distribuição |
| U | Projetistas | projetista responsável pela obra |
| V | Data de entrega do projeto | referência da produção diária |
| W | Qtd. de poste | quantidade final concluída; PLN é usado como fallback quando W estiver vazio |

## Regra de carteira

Uma obra já conta na carteira quando:

- `Status do projeto = Em projeto`;
- `Projetistas` está preenchido.

Para cada projetista o sistema calcula:

- projetos já atribuídos;
- PLN já atribuído;
- meta restante de projetos;
- meta restante de postes;
- cobertura da meta;
- carteira sem PLN, quando existir.

Quem não possui nenhuma obra atribuída inicia com a meta integral de **30 postes / 5 projetos**.

## Obra elegível para distribuição automática

Uma obra só é distribuída automaticamente quando:

- Status = `Em projeto`;
- Projetistas está vazio;
- Nota SGO está preenchida;
- PLN é maior que zero.

## Distribuição igualitária

O motor trabalha por cobertura de meta. Ele prioriza primeiro os projetistas com menor cobertura de postes/projetos e distribui uma obra por rodada antes de voltar ao mesmo projetista.

A seleção considera:

1. prioridade da obra;
2. quanto falta de postes e projetos para o projetista;
3. adequação do PLN ao restante da meta;
4. prazo;
5. equilíbrio entre as carteiras.

A distribuição para de abastecer um projetista quando sua carteira potencial cobre **30 postes e 5 projetos**.

## Dashboard

O painel possui:

- KPIs do dia;
- produção diária por projetista;
- quantidade de projetos concluídos;
- carga já atribuída;
- carga média, mínima, máxima e diferença entre carteiras;
- gráfico de equilíbrio da carteira;
- lista diária de projetistas abaixo da meta ou do ritmo esperado;
- alertas de falta de carga;
- previsão até 18h;
- acompanhamento semanal e mensal;
- análise preditiva de fechamento do mês;
- consistência de meta diária;
- insights automáticos de gestão.

## Upload e distribuição em um clique

No modo `Excel - validação`:

1. faça upload da `BASE LIST.xlsx`;
2. faça upload da `PROJETISTAS.xlsx`;
3. o botão **DISTRIBUIÇÃO AUTOMÁTICA** é habilitado;
4. clique no botão;
5. o sistema calcula as novas atribuições;
6. é gerada uma nova planilha para download.

A BASE original permanece intacta. Na planilha distribuída, somente a coluna **U — Projetistas** é preenchida nas obras selecionadas. Uma aba de auditoria da distribuição também é adicionada.

## Arquivo principal do Streamlit

Ao publicar no Streamlit, use:

```text
app.py
```

Todo o conteúdo do repositório deve permanecer no GitHub. Os usuários finais acessam apenas o link do Streamlit.

## Execução local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Microsoft Lists

A integração está preparada via Microsoft Graph. Antes de ativar escrita real, valide os nomes internos das colunas e mantenha `write_enabled = false` nos Secrets.

Nunca envie credenciais, `secrets.toml`, `BASE_LIST.xlsx` ou `PROJETISTAS.xlsx` para um repositório público.

## V8 - quadro diário simplificado
- Tabela de atenção reduzida para 6 colunas: Projetista, Produção hoje, Carteira atual, Falta para meta, Previsão 18h e Situação.
- Indicadores detalhados permanecem disponíveis em área expansível.
- Status exibidos com ícones para facilitar leitura rápida.


## V9 - carteira simplificada

A aba de carteira foi redesenhada para evitar rolagem horizontal e repetição de metas fixas. A visão principal agora contém apenas:

- Projetista
- Carteira atual (postes e projetos)
- Ainda precisa (postes e projetos)
- Cobertura efetiva da meta
- Situação

A cobertura efetiva considera simultaneamente a meta de postes e a meta de projetos, usando o menor avanço percentual entre as duas. Os campos técnicos continuam disponíveis em um expansor, sem poluir a visão operacional.
