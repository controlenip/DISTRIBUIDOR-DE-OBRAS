# Plano seguro para iniciar os testes com Microsoft Lists

Não habilitar escrita no primeiro teste.

## Fase 1 - leitura

1. Configurar as credenciais do Microsoft Graph no ambiente.
2. Manter `NIP_ALLOW_LISTS_WRITE=NO`.
3. Executar `worker_lists.py` sem `--apply`.
4. Conferir quantidade total de registros.
5. Conferir quantas obras estão `Em projeto`.
6. Conferir obras sem projetista, PLN e Nota SGO.
7. Comparar pelo menos 10 itens entre Streamlit/worker e Microsoft Lists.

## Fase 2 - dry-run de distribuição

1. Conferir os projetistas reconhecidos.
2. Conferir carteira atual de cada um.
3. Conferir as atribuições sugeridas sem gravação.
4. Confirmar que nenhuma obra já atribuída aparece na sugestão.
5. Confirmar que obras sem PLN ou SGO ficam bloqueadas.

## Fase 3 - escrita controlada de homologação

1. Escolher um período de teste.
2. Ativar `NIP_ALLOW_LISTS_WRITE=YES` no ambiente.
3. Executar uma única vez com `--apply`.
4. Começar preferencialmente com pequena quantidade de obras/projetistas.
5. Conferir no Lists se somente `Projetistas` foi alterado.
6. Conferir se `Status do projeto` continuou `Em projeto`.
7. Sincronizar novamente e verificar se as obras deixaram a fila disponível.

## Fase 4 - worker recorrente

Somente depois da homologação:

```bash
python worker_lists.py --designers PROJETISTAS.xlsx --apply --watch --interval 300
```

O processo deve rodar em um serviço persistente. A interface Streamlit pode continuar hospedada separadamente.
