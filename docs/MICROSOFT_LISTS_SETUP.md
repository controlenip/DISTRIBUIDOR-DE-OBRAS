# Configuração do Microsoft Lists

A aplicação usa o Microsoft Graph para ler a lista e, após homologação, preencher a coluna **Projetistas** nas obras distribuídas.

## 1. Campos reais usados

| Uso | Nome exibido | Coluna no export Excel |
|---|---|---|
| Solicitação do cliente | `N° da nota` | A |
| Número operacional do projeto | `Nota SGO` | C |
| Status | `Status do projeto` | E |
| Regional | `Regional` | G |
| Município | `Município` | H |
| Prazo | `Prazo` | M |
| Carga planejada | `P L N` | R |
| Projetista | `Projetistas` | U |
| Data de entrega | `Data de entrega do projeto` | V |
| Quantidade final | `Qtd. de poste` | W |
| Prioridade | `Prioridade` | AP |

O Graph trabalha com **nomes internos** de coluna. A aplicação consulta `GET /sites/{site-id}/lists/{list-id}/columns` e tenta resolver automaticamente os nomes internos a partir dos nomes exibidos acima.

## 2. Regra operacional

Uma obra está na fila quando:

```text
Status do projeto = Em projeto
```

Dentro dessa fila:

```text
Projetistas vazio      -> obra disponível
Projetistas preenchido -> obra já atribuída
```

Para distribuição automática, ainda são obrigatórios:

```text
Nota SGO preenchida
PLN > 0
```

Ao atribuir uma obra, a aplicação **não altera o Status do projeto**. Ela preenche somente o projetista responsável. O status continua `Em projeto` até o processo operacional alterar a obra.

## 3. App Registration

Crie um App Registration no Microsoft Entra ID e configure as permissões adequadas ao Microsoft Graph. Para homologação com leitura e escrita de itens de lista, `Sites.ReadWrite.All` é suportada pelo endpoint de listItem. Em produção, avalie permissões selecionadas/restritas conforme a política de segurança da empresa.

Nunca versione `client_secret` no GitHub.

## 4. Secrets do Streamlit

Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` localmente ou cadastre os mesmos valores na área **Secrets** do Streamlit Cloud.

Mantenha inicialmente:

```toml
write_enabled = false
```

Primeiro valide leitura, mapeamento e cálculos. Somente depois habilite gravação.

## 5. Coluna Projetistas: Texto x Pessoa/Grupo

A aplicação detecta o tipo da coluna pelo endpoint de colunas.

### Se for Texto

A escrita pode preencher diretamente o nome do projetista.

### Se for Pessoa/Grupo

O Graph trabalha com o campo de lookup. A aplicação já aceita uma coluna opcional `SharePointLookupId` na planilha de projetistas. Sem esse ID, a escrita automática permanece bloqueada para evitar gravar um valor incorreto.

A planilha atual `PROJETISTAS.xlsx` possui `Nome` e `E-mail`. Durante a homologação da conexão real, verifique o tipo de `Projetistas`. Se for Pessoa/Grupo, a próxima etapa é resolver automaticamente o SharePoint LookupId a partir do e-mail ou fornecer esse mapeamento.

## 6. Endpoints usados

- Listar colunas: `GET /sites/{site-id}/lists/{list-id}/columns`
- Listar itens: `GET /sites/{site-id}/lists/{list-id}/items?expand=fields(...)`
- Atualizar campos: `PATCH /sites/{site-id}/lists/{list-id}/items/{item-id}/fields`

Referências oficiais:

- https://learn.microsoft.com/en-us/graph/api/list-list-columns?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/listitem-list?view=graph-rest-1.0
- https://learn.microsoft.com/en-us/graph/api/listitem-update?view=graph-rest-1.0
