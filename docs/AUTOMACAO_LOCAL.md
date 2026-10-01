# Automação local antes do Microsoft Lists real

Esta versão permite validar o motor automático sem gravar no ambiente corporativo.

## Regras aplicadas

- Jornada produtiva: 08:00-12:00 e 13:12-18:00.
- A meta cheia diária é 30 postes e 5 projetos.
- Faixa mínima: 25 postes e 4 projetos.
- A meta é diária e não cumulativa.
- Obra elegível: `Status do projeto = Em projeto`, `Projetistas` vazio, `Nota SGO` preenchida e `PLN > 0`.
- Obra já atribuída nunca entra novamente na fila disponível.
- PLN é usado para planejar a carga.
- Produção concluída usa `Qtd. de poste` quando disponível e PLN como fallback.
- No intervalo e fora do expediente o worker não distribui, salvo execução de teste com `--force-time`.

## Simular um ciclo

Coloque `BASE_LIST.xlsx` e `PROJETISTAS.xlsx` na raiz do repositório e execute:

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run
```

Nenhuma planilha é alterada. O worker imprime as atribuições que faria e registra auditoria em `data/automation_audit.sqlite3`.

## Simular continuamente

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run --watch --interval 300
```

Isso reavalia a base a cada 5 minutos. Como a base Excel não muda sozinha, este modo serve para validar o agendamento e os logs; a automação contínua real será ativada quando a fonte for o Microsoft Lists.

## Gerar uma cópia com as atribuições

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode excel-copy --output output/BASE_LIST_DISTRIBUIDA.xlsx
```

O arquivo original nunca é alterado. Somente a coluna `Projetistas` da cópia é preenchida nas obras selecionadas.

## Testar fora do horário

```bash
python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run --force-time
```

Use `--force-time` somente para validação técnica.

## Quando o Microsoft Lists for ativado

O `AutomationEngine` será mantido. A única mudança será a fonte e a função de escrita:

1. `ListsProjectRepository.fetch_projects()` lê o Lists.
2. `AutomationEngine.run_cycle()` calcula as atribuições.
3. `ListsProjectRepository.assign_project()` grava o projetista.
4. O worker sincroniza novamente e confirma que a obra ficou atribuída.

Isso evita manter duas lógicas diferentes entre Excel e Microsoft Lists.
