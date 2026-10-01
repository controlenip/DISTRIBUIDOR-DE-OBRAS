# NIP Smart Distribuição de Projetos - V4

Aplicação **Python + Streamlit** com motor independente para distribuição automática de projetos de rede de distribuição.

A V4 mantém a automação da V3 e adiciona um fluxo explícito de **upload da BASE LIST e da planilha PROJETISTAS** no Streamlit. Assim que os dois arquivos são carregados, a aplicação identifica a carga já atribuída a cada projetista e calcula automaticamente a meta restante antes de sugerir novas obras.

## Regras principais

- Jornada: **08:00-12:00 e 13:12-18:00**.
- Tempo produtivo: **528 min/dia (8h48min)**.
- Faixa diária: **25-30 postes** e **4-5 projetos**.
- Meta cheia do motor: **30 postes / 5 projetos**.
- Meta diária **não cumulativa**.
- Excedente é registrado como desempenho, mas não reduz a meta do próximo dia.
- PLN planeja a carga; `Qtd. de poste` representa a produção final quando disponível.

## Mapeamento real da BASE_LIST

| Coluna | Campo | Uso |
|---|---|---|
| A | `N° da nota` | solicitação do cliente |
| C | `Nota SGO` | número usado pelo projetista para iniciar o projeto |
| E | `Status do projeto` | somente `Em projeto` entra na fila operacional |
| R | `P L N` | quantidade planejada de postes |
| U | `Projetistas` | responsável atribuído |
| V | `Data de entrega do projeto` | data usada para produção concluída |
| W | `Qtd. de poste` | quantidade final de postes |

Também são lidos Regional, Município, Prazo e Prioridade quando disponíveis.


## Carga já atribuída e meta restante - V4

No modo `Excel - validação`, a tela principal possui dois uploads:

1. `BASE LIST.xlsx`;
2. `PROJETISTAS.xlsx`.

A análise é feita automaticamente. Para cada nome da planilha de projetistas, o sistema procura na BASE LIST obras com:

```text
Status do projeto = Em projeto
Projetistas = nome do projetista
```

Depois calcula:

```text
Meta restante de postes = 30 - soma do PLN já atribuído
Meta restante de projetos = 5 - quantidade de projetos já atribuídos
```

Se não houver nenhuma obra atribuída, a meta restante começa inteira em **30 postes / 5 projetos**.

Se houver projeto já atribuído sem PLN, a tela marca `PLN pendente - carga parcial` e o motor bloqueia novas atribuições automáticas para esse projetista até o PLN ser regularizado. Isso evita sobrecarga por uma carteira cujo peso ainda é desconhecido.

A aba **Meta restante** mostra, por projetista:

- quantidade de projetos já atribuídos;
- PLN já atribuído;
- quantidade de projetos sem PLN;
- meta diária;
- meta restante de postes;
- meta restante de projetos;
- cobertura percentual;
- Notas SGO já presentes na carteira;
- situação da carga.

## Obra elegível para distribuição

```text
Status do projeto = Em projeto
Projetistas = vazio
Nota SGO = preenchida
PLN > 0
```

Ao atribuir uma obra, o sistema **mantém o status Em projeto** e altera somente o projetista.

## Balanceamento V4

A distribuição é feita por rodadas. O sistema prioriza o projetista com menor cobertura combinada de postes e projetos, entrega uma obra, recalcula e só depois decide o próximo destino.

Isso evita concentrar toda a fila disponível em um único projetista quando a quantidade de obras é limitada.

## Arquivos de automação

### `worker.py`

Automação local usando `BASE_LIST.xlsx` e `PROJETISTAS.xlsx`.

Simulação única:

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run
```

Gerar cópia da base com as atribuições:

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode excel-copy --output output/BASE_LIST_DISTRIBUIDA.xlsx
```

Executar simulações a cada 5 minutos:

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run --watch --interval 300
```

### `worker_lists.py`

Worker já preparado para o Microsoft Lists.

Por padrão é somente leitura + dry-run:

```bash
python worker_lists.py --designers PROJETISTAS.xlsx
```

Para gravar no Lists são obrigatórias **duas liberações simultâneas**:

```text
--apply
NIP_ALLOW_LISTS_WRITE=YES
```

Depois da homologação, o modo recorrente será:

```bash
python worker_lists.py --designers PROJETISTAS.xlsx --apply --watch --interval 300
```

## Auditoria

Os ciclos são registrados em:

```text
data/automation_audit.sqlite3
```

O banco guarda ciclos, sugestões, atribuições, erros e motivos. Ele não é versionado no GitHub.

## Estrutura

```text
nip-smart-distribuicao/
├── app.py
├── worker.py
├── worker_lists.py
├── requirements.txt
├── executar_local.bat
├── executar_automacao_simulacao.bat
├── executar_automacao_copia_excel.bat
├── executar_worker_lists_simulacao.bat
├── config/
│   └── microsoft_lists.env.example
├── docs/
│   ├── ARQUITETURA_AUTOMACAO.md
│   ├── AUTOMACAO_LOCAL.md
│   ├── MICROSOFT_LISTS_SETUP.md
│   ├── PLANO_TESTE_MICROSOFT_LISTS.md
│   └── VALIDACAO_BASE_REAL.md
├── src/
│   ├── audit_store.py
│   ├── automation_engine.py
│   ├── distribution_engine.py
│   ├── excel_loader.py
│   ├── excel_writer.py
│   ├── graph_client.py
│   ├── lists_repository.py
│   ├── metrics.py
│   ├── models.py
│   ├── name_utils.py
│   └── work_schedule.py
└── tests/
```

## Segurança do repositório

Não enviar ao GitHub:

- `BASE_LIST.xlsx`;
- `PROJETISTAS.xlsx`;
- `.streamlit/secrets.toml`;
- banco SQLite de auditoria;
- cópias Excel geradas pela automação.

Esses arquivos já estão cobertos pelo `.gitignore`.

## Executar Streamlit

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Ou use `executar_local.bat`.

## Testes

```bash
pytest -q
```

A V4 inclui testes de jornada, intervalo, Excel real, elegibilidade, distribuição balanceada, automação e escrita somente em cópia.

## Validação realizada com a base recebida

Na base de homologação foram encontrados 31 registros `Em projeto`, sendo 12 sem projetista e 19 já atribuídos. Nove obras estavam aptas à distribuição automática (34 postes de PLN).

No teste da V4, as 9 obras elegíveis foram distribuídas de forma balanceada entre 9 projetistas conforme a cobertura existente. Ao gerar uma cópia do Excel, exatamente 9 linhas foram alteradas e todas continuaram com status `Em projeto`.

Os arquivos operacionais reais não fazem parte do repositório.
