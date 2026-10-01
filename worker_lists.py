from __future__ import annotations

import argparse
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.audit_store import AuditStore
from src.automation_engine import AutomationEngine, AutomationPolicy
from src.excel_loader import load_designers_excel
from src.graph_client import GraphClient
from src.lists_repository import FieldMap, ListsProjectRepository
from src.models import StatusConfig, Targets
from src.name_utils import normalize_person_name


TIMEZONE = "America/Fortaleza"
TARGETS = Targets(min_posts=25, target_posts=30, min_projects=4, target_projects=5)
STATUSES = StatusConfig(project_pool=("Em projeto",), completed=("Concluído", "Concluido"))
FIELD_MAP = FieldMap(
    note="N° da nota",
    sgo="Nota SGO",
    status="Status do projeto",
    regional="Regional",
    municipality="Município",
    deadline="Prazo",
    posts="P L N",
    assignee="Projetistas",
    completed_at="Data de entrega do projeto",
    actual_posts="Qtd. de poste",
    priority="Prioridade",
)


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória não configurada: {name}")
    return value


def make_repo() -> ListsProjectRepository:
    graph = GraphClient(
        tenant_id=required_env("MS_TENANT_ID"),
        client_id=required_env("MS_CLIENT_ID"),
        client_secret=required_env("MS_CLIENT_SECRET"),
    )
    return ListsProjectRepository(
        graph,
        required_env("MS_SITE_ID"),
        required_env("MS_LIST_ID"),
        FIELD_MAP,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NIP Smart - worker Microsoft Lists")
    p.add_argument("--designers", default="PROJETISTAS.xlsx")
    p.add_argument("--audit", default="data/automation_audit.sqlite3")
    p.add_argument("--apply", action="store_true", help="Permite gravar atribuições no Lists")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--interval", type=int, default=300)
    p.add_argument("--force-time", action="store_true")
    return p.parse_args()


def run_once(args: argparse.Namespace) -> int:
    designers_path = Path(args.designers)
    if not designers_path.exists():
        print(f"ERRO: planilha de projetistas não encontrada: {designers_path}")
        return 2

    repo = make_repo()
    projects = repo.fetch_projects()
    designers_df = load_designers_excel(designers_path)
    designers = designers_df["name"].tolist()
    now = datetime.now(ZoneInfo(TIMEZONE))

    audit = AuditStore(args.audit)
    engine = AutomationEngine(
        TARGETS,
        STATUSES,
        policy=AutomationPolicy(timezone=TIMEZONE, require_work_hours=not args.force_time),
        audit=audit,
    )

    allow_write = os.getenv("NIP_ALLOW_LISTS_WRITE", "").strip().upper() == "YES"
    if args.apply and not allow_write:
        print("BLOQUEADO: --apply exige também NIP_ALLOW_LISTS_WRITE=YES.")
        return 3

    lookup_by_name = {
        normalize_person_name(row["name"]): row.get("sharepoint_lookup_id")
        for _, row in designers_df.iterrows()
    }

    def apply_assignment(row: pd.Series) -> None:
        lookup_id = lookup_by_name.get(normalize_person_name(row["Projetista"]))
        etag = None if pd.isna(row.get("etag")) else row.get("etag")
        repo.assign_project(
            item_id=str(row["item_id"]),
            designer=str(row["Projetista"]),
            etag=etag,
            sharepoint_lookup_id=lookup_id,
        )

    result = engine.run_cycle(
        projects,
        designers,
        now,
        source="microsoft-lists",
        mode="apply" if args.apply else "dry-run",
        apply_assignment=apply_assignment if args.apply else None,
    )

    print(f"[{now.strftime('%d/%m/%Y %H:%M:%S')}] {result.status.upper()} - {result.message}")
    if not result.suggestions.empty:
        cols = [c for c in ["Projetista", "Nº da nota", "Nota SGO", "PLN", "Regional", "Município"] if c in result.suggestions.columns]
        print(result.suggestions[cols].to_string(index=False))

    if args.apply and result.assignments_applied:
        # Re-read after write so the next cycle starts from the official source.
        refreshed = repo.fetch_projects()
        print(f"Pós-gravação: {len(refreshed)} item(ns) sincronizado(s) novamente do Lists.")

    if result.errors:
        for err in result.errors:
            print("ERRO:", err)
    return 0 if result.status in {"success", "skipped", "partial"} else 1


def main() -> int:
    args = parse_args()
    if not args.watch:
        return run_once(args)
    interval = max(60, int(args.interval))
    print(f"Worker Lists iniciado. Intervalo: {interval}s. Gravação: {'SIM' if args.apply else 'NÃO'}")
    try:
        while True:
            run_once(args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Worker encerrado pelo usuário.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
