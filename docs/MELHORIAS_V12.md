# V12 — Guia de operação

## Botões

- **Azul:** ação de análise/simulação.
- **Laranja:** confirmação que gera/aplica uma distribuição.
- **Verde:** download de arquivo pronto.
- **Vermelho:** `LIMPAR DADOS`.

## Distribuição segura

A V12 separa a decisão em duas etapas:

1. simulação;
2. geração/aplicação.

A simulação pode ser revisada. O sistema valida novamente o teto de carteira antes de aceitar ajustes manuais.

## Teto de carteira

O padrão é 36 postes / 6 projetos. Pode ser alterado pelo Administrador nas opções avançadas.

## Perfil de acesso

- **Administrador:** pode simular, editar, gerar e aplicar.
- **Consulta:** visualiza os painéis, mas não distribui.

Para impedir que qualquer usuário selecione Administrador, configure `access.admin_pin` nos Secrets do Streamlit.

## Microsoft Lists

A integração continua protegida por `write_enabled=false` por padrão. Quando a integração real for homologada, a atualização automática de 5 minutos pode ser habilitada na interface.

## Notificações

Se houver um webhook configurado, a ferramenta pode enviar um resumo após a geração. O fluxo do Power Automate fica responsável por encaminhar a mensagem ao Teams/e-mail conforme a regra corporativa.
