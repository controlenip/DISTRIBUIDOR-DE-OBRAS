# Validação da estrutura recebida

Validação realizada sobre os arquivos enviados para homologação, sem incluí-los no repositório.

## BASE_LIST.xlsx

- Aba detectada: `query`
- Registros de dados: **7.280**
- Coluna A: `N° da nota`
- Coluna C: `Nota SGO`
- Coluna E: `Status do projeto `
- Coluna R: `P L N `
- Coluna U: `Projetistas`
- Coluna V: `Data de entrega do projeto`
- Coluna W: `Qtd. de poste`
- Coluna AP: `Prioridade`

### Situação da fila no arquivo validado

- Obras com status `Em projeto`: **31**
- `Em projeto` sem projetista: **12**
- `Em projeto` com projetista: **19**
- Disponíveis sem Postes Alterados/Novos válido: **3**
- Atribuídas sem Postes Alterados/Novos válido: **7**
- Disponíveis sem Nota SGO: **0**
- Obras elegíveis para distribuição automática na validação: **9**
- Soma do Postes Alterados/Novos das obras elegíveis: **34 postes**

Regra aplicada: somente obras `Em projeto`, sem projetista, com Nota SGO e Postes Alterados/Novos maior que zero podem ser distribuídas automaticamente.

## PROJETISTAS.xlsx

- Aba detectada: `Plan1`
- Projetistas cadastrados no arquivo validado: **21**
- Colunas: `Nome` e `E-mail`

O sistema normaliza maiúsculas/minúsculas e acentuação para comparar nomes do Microsoft Lists com a planilha de projetistas, mantendo o nome original apenas para exibição.

## Observação sobre produção

- **Postes Alterados/Novos** é usado como carga planejada para distribuição e carteira.
- Para obra concluída, a aplicação usa **Qtd. de poste** como quantidade final quando disponível.
- Se `Qtd. de poste` estiver vazia, o sistema usa o Postes Alterados/Novos como fallback.

## Validação da meta restante - V4

Com a BASE LIST e a planilha PROJETISTAS carregadas em conjunto:

- Projetistas analisados: **21**
- Projetistas com pelo menos uma obra `Em projeto` já atribuída: **9**
- Projetistas sem nenhuma obra `Em projeto` atribuída: **12**
- Projetistas cuja carteira contém pelo menos um projeto sem Postes Alterados/Novos: **3**
- Projetistas com carga parcial calculável e sem pendência de Postes Alterados/Novos: **6**

Para os **12 projetistas sem carga**, a ferramenta inicia automaticamente a necessidade em **30 postes / 5 projetos**.

Para quem já possui carga, a ferramenta calcula:

```text
Meta restante de postes = 30 - Postes Alterados/Novos conhecido já atribuído
Meta restante de projetos = 5 - quantidade de obras já atribuídas
```

O resultado nunca fica negativo: quando uma dimensão já ultrapassa a meta, sua necessidade restante fica em zero.

Se existir obra já atribuída sem Postes Alterados/Novos, o sistema exibe `Postes Alterados/Novos pendente - carga parcial` e bloqueia novas atribuições automáticas para aquele projetista até a quantidade de postes ser regularizada.
