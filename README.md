# NIP Smart Distribuição — V12

Aplicação em **Python + Streamlit** para distribuição equilibrada de obras entre projetistas e acompanhamento de produtividade diária, semanal e mensal.

## O que mudou na V12

A V12 transforma o fluxo em uma operação mais segura e visual:

- **Simulação obrigatória antes de gerar a planilha**;
- possibilidade de **incluir/excluir uma obra** e ajustar o projetista na simulação;
- **teto de carteira configurável** para evitar sobrecarga;
- fila com **Prioridade e Prazo**;
- obras já atribuídas nunca são redistribuídas automaticamente;
- motivo da atribuição e carga **antes/depois** registrados;
- indicador de **equilíbrio da carteira**;
- validação de SGO/PLN e detecção de SGO/nota duplicados;
- **auditoria** dos ciclos de simulação e exportação;
- perfil **Administrador / Consulta**, com PIN opcional via Secrets;
- metas e limites configuráveis na interface;
- histórico individual dos últimos 20 dias úteis;
- consistência diária de meta;
- projeção mensal;
- fechamento diário para download em Excel;
- sinal opcional de **reanálise registrada** quando a coluna existir na BASE;
- Microsoft Lists com leitura, escrita protegida e opção de sincronização periódica;
- notificação opcional via webhook/Power Automate;
- botões com maior contraste: ações principais em laranja/azul, download em verde e **Limpar dados em vermelho**.

## Regra principal

Meta padrão por projetista:

- 30 postes/dia;
- 5 projetos/dia;
- faixa mínima de 25 postes / 4 projetos;
- meta diária e **não cumulativa**.

A carteira ativa considera obras com:

- `Status do projeto = Em projeto`;
- campo `Projetistas` preenchido;
- peso da obra = `PLN`.

Uma obra pode entrar na distribuição automática quando:

- Status = `Em projeto`;
- Projetistas está vazio;
- Nota SGO está preenchida;
- PLN é maior que zero.

## Fluxo recomendado

1. Carregue `BASE_LIST.xlsx` e `PROJETISTAS.xlsx`.
2. Clique em **SIMULAR DISTRIBUIÇÃO**.
3. Confira/ajuste a simulação.
4. Clique em **GERAR NOVA BASE LIST DISTRIBUÍDA**.
5. Baixe o arquivo gerado.
6. Use **LIMPAR DADOS** antes de começar um novo ciclo com outras bases.

## Arquivo principal no Streamlit

Use:

```text
app.py
```

Todo o conteúdo deste repositório deve permanecer no GitHub. O usuário final recebe apenas o link do Streamlit.

## Segurança

Nunca coloque credenciais reais no GitHub. Use **Streamlit Secrets**.

O arquivo `.streamlit/secrets.toml.example` mostra os campos aceitos, incluindo:

- credenciais do Microsoft Graph;
- PIN opcional de administrador;
- parâmetros padrão;
- webhook opcional para notificações.

## Testes

Execute:

```bash
pytest -q
```

A V12 inclui testes para distribuição, teto de carteira, prioridade, histórico individual, Excel e regras de jornada.
