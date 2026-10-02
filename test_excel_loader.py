from pathlib import Path

from openpyxl import Workbook

from src.excel_loader import load_base_excel, load_designers_excel


def test_load_real_column_layout(tmp_path: Path):
    path = tmp_path / "base.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["N° da nota", "Detalhes", "Nota SGO", "Tipo", "Status do projeto ", "PI (Tipo Projeto)", "Regional", "Município", "Un", "Lat", "Long", "Despacho", "Prazo", "Campo", "Levantador", "Levantamento", "Qnt. postes levantados ", "P L N ", "Analista", "Data análise", "Projetistas", "Data de entrega do projeto", "Qtd. de poste", "Postes Existente", "Extensão MT", "BT", "Equip", "Item", "Abertura", "Técnico", "Relatório", "Conclusão amb", "Analistas", "Data", "Reanálise", "Obs", "Tipo expurgo", "Data expurgo", "Motivo", "Status expurgo", "Cancelamento", "Prioridade"])
    ws.append([111, None, 4301, "Projeto", "Em projeto", "UNI", "NORTE", "SAO LUIS", None, None, None, None, None, None, None, None, 5, 7, None, None, "", None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, None, "Alta"])
    wb.save(path)
    df = load_base_excel(path)
    assert df.iloc[0]["note"] == 111
    assert df.iloc[0]["sgo"] == 4301
    assert df.iloc[0]["posts"] == 7
    assert bool(df.iloc[0]["posts_valid"])
    assert df.iloc[0]["status"] == "Em projeto"
    assert df.iloc[0]["project_type"] == "UNI"


def test_load_designers(tmp_path: Path):
    path = tmp_path / "designers.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["Nome", "E-mail", "Experiência"])
    ws.append(["PROJETISTA TESTE", "teste@empresa.com", "Experiente"])
    wb.save(path)
    df = load_designers_excel(path)
    assert df.iloc[0]["name"] == "PROJETISTA TESTE"
    assert df.iloc[0]["email"] == "teste@empresa.com"
    assert df.iloc[0]["experience"] == "Experiente"
