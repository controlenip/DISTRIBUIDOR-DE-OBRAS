from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src.audit_store import AuditStore
from src.automation_engine import AutomationEngine, AutomationPolicy
from src.excel_loader import load_base_excel, load_designers_excel
from src.excel_writer import apply_assignments_to_excel_copy
from src.models import StatusConfig, Targets


TIMEZONE = "America/Fortaleza"
TARGETS = Targets(min_posts=25, target_posts=30, min_projects=4, target_projects=5)
STATUSES = StatusConfig(project_pool=("Em projeto",), completed=("Concluído", "Concluido"))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="NIP Smart - worker de distribuição automática")
    p.add_argument("--base", default="BASE_LIST.xlsx", help="Caminho para BASE_LIST.xlsx")
    p.add_argument("--designers", default="PROJETISTAS.xlsx", help="Caminho para PROJETISTAS.xlsx")
    p.add_argument("--mode", choices=["dry-run", "excel-copy"], default="dry-run")
    p.add_argument("--output", default="output/BASE_LIST_DISTRIBUIDA.xlsx")
    p.add_argument("--audit", default="data/automation_audit.sqlite3")
    p.add_argument("--watch", action="store_true", help="Executa ciclos continuamente")
    p.add_argument("--interval", type=int, default=300, help="Intervalo entre ciclos em segundos (padrão 300)")
    p.add_argument("--force-time", action="store_true", help="Permite simulação fora do horário de trabalho")
    return p.parse_args()


def run_once(args: argparse.Namespace) -> int:
    base_path = Path(args.base)
    designers_path = Path(args.designers)
    if not base_path.exists():
        print(f"ERRO: base não encontrada: {base_path}")
        return 2
    if not designers_path.exists():
        print(f"ERRO: planilha de projetistas não encontrada: {designers_path}")
        return 2

    projects = load_base_excel(base_path)
    designers_df = load_designers_excel(designers_path)
    designers = designers_df["name"].tolist()
    now = datetime.now(ZoneInfo(TIMEZONE))

    audit = AuditStore(args.audit)
    policy = AutomationPolicy(timezone=TIMEZONE, require_work_hours=not args.force_time)
    engine = AutomationEngine(TARGETS, STATUSES, policy=policy, audit=audit)

    if args.mode == "dry-run":
        result = engine.run_cycle(projects, designers, now, source="excel", mode="dry-run")
    else:
        # For Excel local testing, all changes are written to a COPY in a single operation.
        # We still use the same engine to determine the suggestions.
        dry = engine.run_cycle(projects, designers, now, source="excel", mode="dry-run")
        if dry.suggestions.empty:
            result = dry
        elif dry.status != "success":
            result = dry
        else:
            output = Path(args.output)
            apply_assignments_to_excel_copy(base_path, output, dry.suggestions)
            # Record application events in a separate cycle for clear audit history.
            def noop_apply(_row: pd.Series) -> None:
                return None
            result = engine.run_cycle(projects, designers, now, source="excel-copy", mode="apply", apply_assignment=noop_apply)
            print(f"Cópia gerada: {output.resolve()}")

    print(f"[{now.strftime('%d/%m/%Y %H:%M:%S')}] {result.status.upper()} - {result.message}")
    if not result.distribution_summary.empty:
        cols = [c for c in ["Projetista", "Novos projetos sugeridos", "Novos postes sugeridos", "Risco de tempo", "Motivo"] if c in result.distribution_summary.columns]
        print(result.distribution_summary[cols].to_string(index=False))
    if not result.suggestions.empty:
        print("\nAtribuições:")
        cols = [c for c in ["Projetista", "Nº da nota", "Nota SGO", "PLN", "Regional", "Município"] if c in result.suggestions.columns]
        print(result.suggestions[cols].to_string(index=False))
    if result.errors:
        print("\nErros:")
        for err in result.errors:
            print(" -", err)
    return 0 if result.status in {"success", "skipped", "partial"} else 1


def main() -> int:
    args = parse_args()
    if not args.watch:
        return run_once(args)
    interval = max(60, int(args.interval))
    print(f"Worker contínuo iniciado. Intervalo: {interval}s. Ctrl+C para encerrar.")
    try:
        while True:
            run_once(args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("Worker encerrado pelo usuário.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
