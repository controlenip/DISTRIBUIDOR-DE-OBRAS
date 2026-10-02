# NIP Smart Distribuição — V10

Aplicação **Python + Streamlit** para dois objetivos principais:

1. **distribuir obras de forma equilibrada entre os projetistas**;
2. **acompanhar a produtividade diária, semanal e mensal dos projetistas**.

A V10 foi reorganizada para ficar mais simples para quem usa a ferramenta pela primeira vez.

## Fluxo de uso

No modo Excel, o usuário segue apenas três passos:

1. carregar `BASE LIST.xlsx`;
2. carregar `PROJETISTAS.xlsx`;
3. clicar em **GERAR DISTRIBUIÇÃO AUTOMÁTICA** e baixar a nova BASE LIST.

A planilha original não é alterada.

## Menu simplificado

A interface possui somente quatro áreas principais:

- **Início** — upload, resumo da equipe, botão de distribuição e download;
- **Distribuir obras** — prévia das novas atribuições e carga após a distribuição;
- **Produtividade** — resultado diário, semana/mês e análise preditiva;
- **Dados e regras** — qualidade da base, regras técnicas e integração Microsoft Lists.

Recursos técnicos ficam recolhidos para não poluir a operação diária.

## Metas

- referência diária: **30 postes / 5 projetos**;
- faixa mínima: **25 postes / 4 projetos**;
- jornada: **08:00–12:00 e 13:12–18:00**;
- total produtivo: **528 minutos**;
- meta diária **não cumulativa**.

O excedente de um dia não diminui a meta do dia seguinte.

## Conceitos exibidos na ferramenta

### Carteira

São as obras com:

- `Status do projeto = Em projeto`;
- campo `Projetistas` preenchido.

O peso da obra é o **PLN da coluna R**.

### Produção

É o que o projetista efetivamente entregou na data analisada.

- data: `Data de entrega do projeto`;
- postes: `Qtd. de poste`;
- quando a quantidade final estiver vazia, o PLN pode ser usado como apoio.

### Obras prontas para distribuir

Uma obra só entra na distribuição automática quando:

- Status = `Em projeto`;
- Projetistas está vazio;
- Nota SGO está preenchida;
- PLN é maior que zero.

## Colunas principais da BASE LIST

| Coluna | Campo | Uso |
|---|---|---|
| A | Nº da nota | solicitação do cliente |
| C | Nota SGO | número usado pelo projetista para iniciar o projeto |
| E | Status do projeto | identifica as obras `Em projeto` |
| R | P L N | quantidade de postes usada como peso da obra |
| U | Projetistas | projetista responsável |
| V | Data de entrega do projeto | data usada na produtividade diária |
| W | Qtd. de poste | quantidade final entregue |

As colunas de levantamento não fazem parte dos indicadores da ferramenta.

## Como a distribuição funciona

O sistema:

1. identifica o que cada projetista já tem em carteira;
2. calcula quanto falta para 30 postes e 5 projetos;
3. prioriza quem tem menor cobertura;
4. distribui uma obra por rodada para evitar concentração;
5. para de abastecer o projetista quando a carteira cobre a referência diária;
6. mantém obras já atribuídas com o responsável atual.

## Produtividade

A página de produtividade permite escolher a data da análise e mostra:

- postes entregues;
- projetos entregues;
- projetistas que atingiram a meta cheia;
- quem precisa de atenção;
- resultado da semana;
- resultado do mês;
- consistência da meta diária;
- projeção de fechamento do mês.

Para uma data anterior, a tela não apresenta a carteira atual como se fosse histórica.

## Arquivo principal do Streamlit

Use:

```text
app.py
```

Todo o repositório deve permanecer no GitHub. Os usuários finais acessam apenas o link do Streamlit.

## Execução local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Microsoft Lists

A integração via Microsoft Graph continua preparada, mas fica em **Opções avançadas / Dados e regras** para não confundir o uso diário.

Nunca envie credenciais, `secrets.toml`, `BASE_LIST.xlsx` ou `PROJETISTAS.xlsx` para um repositório público.

## Validação da V10

- 21 testes automatizados aprovados;
- leitura validada com a BASE LIST e PROJETISTAS fornecidos;
- 21 projetistas reconhecidos;
- 12 projetistas sem obra na carteira atual;
- 9 novas atribuições sugeridas na base de validação;
- 9 projetistas diferentes contemplados nessas sugestões.
