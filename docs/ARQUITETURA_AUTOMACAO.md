# Arquitetura da automação

## Objetivo

Manter cada projetista com carga suficiente para buscar a meta diária de 30 postes e 5 projetos, sem carregar excedentes para o dia seguinte.

## Ciclo operacional

```text
Fonte oficial (Excel de teste / Microsoft Lists)
        ↓
Ler projetos e projetistas
        ↓
Classificar obras
  - disponível
  - já atribuída
  - concluída hoje
  - bloqueada por falta de Postes Alterados/Novos/SGO
        ↓
Calcular por projetista
  - realizado hoje
  - carteira atual
  - potencial realizado + carteira
  - déficit de postes
  - déficit de projetos
  - tempo útil restante
  - risco de tempo
        ↓
Distribuição balanceada por rodadas
        ↓
Gerar sugestões
        ↓
Dry-run OU gravação autorizada
        ↓
Registrar auditoria
        ↓
No Lists: sincronizar novamente antes do próximo ciclo
```

## Distribuição balanceada

Quando a fila de projetos é menor que a necessidade da equipe, o motor não completa primeiro a meta de uma única pessoa. Ele usa uma lógica de `water-filling`:

1. calcula a cobertura atual de cada projetista;
2. prioriza quem possui menor cobertura combinada de postes e projetos;
3. entrega um projeto;
4. recalcula a cobertura;
5. passa para quem estiver mais descoberto;
6. volta a uma mesma pessoa somente quando o balanceamento indicar necessidade.

Isso evita concentrar seis projetos em uma pessoa enquanto outras continuam sem carteira.

## Regras de elegibilidade

Uma obra só pode ser distribuída automaticamente quando:

- `Status do projeto = Em projeto`;
- `Projetistas` está vazio;
- `Nota SGO` está preenchida;
- `Postes Alterados/Novos > 0`.

## Jornada

- 08:00-12:00
- 13:12-18:00
- 528 minutos produtivos

O worker não distribui no intervalo ou fora da jornada, salvo quando `--force-time` é usado em teste.

## Segurança

### Excel

O arquivo original nunca é alterado. `excel-copy` cria uma nova cópia e preenche somente `Projetistas`.

### Microsoft Lists

Há duas travas independentes:

1. linha de comando `--apply`;
2. variável `NIP_ALLOW_LISTS_WRITE=YES`.

Sem as duas condições, o worker não grava.

A escrita utiliza o `eTag` retornado pelo Lists para reduzir risco de sobrescrever uma alteração concorrente.

## Auditoria

`AuditStore` registra em SQLite:

- horário do ciclo;
- fonte;
- modo;
- quantidade de sugestões;
- quantidade aplicada;
- Nota/SGO;
- projetista;
- Postes Alterados/Novos;
- motivo;
- resultado/erro.

O banco local é ignorado pelo Git.
