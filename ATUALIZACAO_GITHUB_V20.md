# Atualizacao correta no GitHub - V20

O Streamlit executa `app.py`, mas o app depende dos modulos dentro de `src/`.
Um erro como `cannot import name load_vu_excel` significa que `app.py` foi atualizado e `src/excel_loader.py` permaneceu de uma versao anterior.

## Forma recomendada
1. Descompacte a V20.
2. Abra a pasta interna `nip-smart-distribuicao`.
3. No GitHub, substitua TODO o conteudo do repositorio pelos arquivos desta pasta.
4. Confirme que estes arquivos existem no GitHub:
   - `app.py`
   - `src/excel_loader.py`
   - `src/source_combiner.py`
   - `src/excel_writer.py`
5. Em `src/excel_loader.py`, procure por `def load_vu_excel`.
6. Salve/commit.
7. Aguarde o redeploy do Streamlit ou reinicie o app.

## Arquivos VU obrigatorios
Todos precisam ser da mesma versao:
- `app.py`
- `src/excel_loader.py`
- `src/source_combiner.py`
- `src/excel_writer.py`

Nao e necessario apagar o repositorio inteiro, mas arquivos antigos em `src/` precisam ser sobrescritos.
