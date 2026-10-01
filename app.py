from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from src.audit_store import AuditStore
from src.automation_engine import AutomationEngine, AutomationPolicy
from src.demo_data import sample_designers_df, sample_projects
from src.distribution_engine import suggest_assignments
from src.excel_loader import load_base_excel, load_designers_excel
from src.graph_client import GraphClient, GraphError
from src.lists_repository import FieldMap, ListsProjectRepository
from src.metrics import (
    build_assignment_baseline,
    build_daily_snapshots,
    data_quality_summary,
    monthly_metrics,
    monthly_prediction,
    prepare_projects,
    weekly_metrics,
)
from src.models import StatusConfig, Targets
from src.name_utils import normalize_person_name
from src.work_schedule import (
    TOTAL_WORK_MINUTES,
    current_work_status,
    format_minutes,
    productive_minutes_elapsed,
    productive_minutes_remaining,
)

st.set_page_config(page_title="NIP Smart Distribuição", page_icon="⚡", layout="wide")


def secrets_dict() -> dict:
    try:
        return st.secrets.to_dict()
    except Exception:
        return {}


def nested(data: dict, *keys, default=None):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


SECRETS = secrets_dict()
TIMEZONE = nested(SECRETS, "app", "timezone", default="America/Fortaleza")
TARGETS = Targets(
    min_posts=int(nested(SECRETS, "app", "min_posts", default=25)),
    target_posts=int(nested(SECRETS, "app", "target_posts", default=30)),
    min_projects=int(nested(SECRETS, "app", "min_projects", default=4)),
    target_projects=int(nested(SECRETS, "app", "target_projects", default=5)),
)
STATUS = StatusConfig(
    project_pool=tuple(nested(SECRETS, "lists", "status", "project_pool", default=["Em projeto"])),
    completed=tuple(nested(SECRETS, "lists", "status", "completed", default=["Concluído", "Concluido"])),
)
WRITE_ENABLED = bool(nested(SECRETS, "app", "write_enabled", default=False))

FIELD_MAP = FieldMap(
    note=nested(SECRETS, "lists", "fields", "note", default="N° da nota"),
    sgo=nested(SECRETS, "lists", "fields", "sgo", default="Nota SGO"),
    status=nested(SECRETS, "lists", "fields", "status", default="Status do projeto"),
    regional=nested(SECRETS, "lists", "fields", "regional", default="Regional"),
    municipality=nested(SECRETS, "lists", "fields", "municipality", default="Município"),
    deadline=nested(SECRETS, "lists", "fields", "deadline", default="Prazo"),
    posts=nested(SECRETS, "lists", "fields", "posts", default="P L N"),
    assignee=nested(SECRETS, "lists", "fields", "assignee", default="Projetistas"),
    completed_at=nested(SECRETS, "lists", "fields", "completed_at", default="Data de entrega do projeto"),
    actual_posts=nested(SECRETS, "lists", "fields", "actual_posts", default="Qtd. de poste"),
    priority=nested(SECRETS, "lists", "fields", "priority", default="Prioridade"),
)

GRAPH_CONFIG = {
    "tenant_id": nested(SECRETS, "graph", "tenant_id", default=""),
    "client_id": nested(SECRETS, "graph", "client_id", default=""),
    "client_secret": nested(SECRETS, "graph", "client_secret", default=""),
    "site_id": nested(SECRETS, "graph", "site_id", default=""),
    "list_id": nested(SECRETS, "graph", "list_id", default=""),
}
GRAPH_READY = all(GRAPH_CONFIG.values())


def make_repository() -> ListsProjectRepository:
    graph = GraphClient(
        tenant_id=GRAPH_CONFIG["tenant_id"],
        client_id=GRAPH_CONFIG["client_id"],
        client_secret=GRAPH_CONFIG["client_secret"],
    )
    return ListsProjectRepository(graph, GRAPH_CONFIG["site_id"], GRAPH_CONFIG["list_id"], FIELD_MAP)


# Session state keeps parsed bases available during Streamlit reruns.
for key, default in {
    "demo_projects": sample_projects(TIMEZONE),
    "excel_projects": pd.DataFrame(),
    "uploaded_designers": pd.DataFrame(),
    "graph_projects": pd.DataFrame(),
    "last_sync": None,
    "column_diagnostics": pd.DataFrame(),
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.sidebar.title("⚡ NIP Smart")
st.sidebar.caption("Distribuição inteligente de projetos")
source_mode = st.sidebar.radio(
    "Fonte da base",
    ["Excel - validação", "Microsoft Lists", "DEMO"],
    index=0,
)

st.sidebar.divider()
st.sidebar.subheader("Metas")
st.sidebar.write(f"**{TARGETS.min_posts}–{TARGETS.target_posts} postes/dia**")
st.sidebar.write(f"**{TARGETS.min_projects}–{TARGETS.target_projects} projetos/dia**")
st.sidebar.caption("Excedente diário é registrado, mas não vira crédito para o dia seguinte.")

NOW = datetime.now(ZoneInfo(TIMEZONE))
st.title("NIP Smart Distribuição de Projetos")
st.caption(
    "Base real: A = Nº da nota • C = Nota SGO • E = Status do projeto • R = PLN • U = Projetistas | "
    "Jornada 08:00–12:00 e 13:12–18:00"
)

# ---------- Data source / uploads ----------
designer_upload = None
if source_mode == "Excel - validação":
    st.subheader("📥 Carregar bases para análise e distribuição")
    up_base, up_designers = st.columns(2)
    with up_base:
        base_upload = st.file_uploader(
            "1. BASE LIST (.xlsx)",
            type=["xlsx"],
            key="base_list_main",
            help="Export da base do Microsoft Lists com Status, PLN, Nota SGO e Projetistas.",
        )
        if base_upload is not None:
            try:
                st.session_state.excel_projects = load_base_excel(base_upload)
                st.success(f"BASE LIST carregada: {len(st.session_state.excel_projects):,} registro(s).".replace(",", "."))
            except Exception as exc:
                st.error(f"Falha ao ler BASE LIST: {exc}")
    with up_designers:
        designer_upload = st.file_uploader(
            "2. PROJETISTAS (.xlsx)",
            type=["xlsx"],
            key="designers_main",
            help="Lista dos projetistas que podem receber novas obras.",
        )
        if designer_upload is not None:
            try:
                st.session_state.uploaded_designers = load_designers_excel(designer_upload)
                st.success(f"Projetistas carregados: {len(st.session_state.uploaded_designers)}.")
            except Exception as exc:
                st.error(f"Falha ao ler PROJETISTAS.xlsx: {exc}")
    st.caption(
        "A análise é automática: o sistema verifica quem já possui obra com **Status = Em projeto**, "
        "soma o **PLN** dessas obras e calcula somente o restante da meta. Quem não possui obra atribuída "
        f"começa com a meta integral de **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**."
    )

elif source_mode == "Microsoft Lists":
    designer_upload = st.sidebar.file_uploader("Planilha PROJETISTAS.xlsx", type=["xlsx"], key="designers_lists")
    if designer_upload is not None:
        try:
            st.session_state.uploaded_designers = load_designers_excel(designer_upload)
            st.sidebar.success(f"{len(st.session_state.uploaded_designers)} projetista(s) carregado(s).")
        except Exception as exc:
            st.sidebar.error(f"Falha ao ler PROJETISTAS.xlsx: {exc}")

    if not GRAPH_READY:
        st.sidebar.error("Configure tenant_id, client_id, client_secret, site_id e list_id no secrets.toml.")
    elif st.sidebar.button("🔄 Sincronizar Microsoft Lists", use_container_width=True):
        try:
            repo = make_repository()
            st.session_state.graph_projects = repo.fetch_projects()
            st.session_state.column_diagnostics = repo.column_diagnostics()
            st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
            st.sidebar.success("Microsoft Lists sincronizado.")
        except Exception as exc:
            st.sidebar.error(str(exc))

# Resolve source data.
if source_mode == "Excel - validação":
    projects = st.session_state.excel_projects.copy()
    designers_df = st.session_state.uploaded_designers.copy()
elif source_mode == "Microsoft Lists":
    projects = st.session_state.graph_projects.copy()
    designers_df = st.session_state.uploaded_designers.copy()
else:
    projects = st.session_state.demo_projects.copy()
    designers_df = sample_designers_df()

DESIGNERS = designers_df["name"].tolist() if not designers_df.empty else []

if not DESIGNERS:
    st.warning("Carregue a planilha **PROJETISTAS.xlsx** para definir quem pode receber novas obras.")
    st.stop()
if projects.empty:
    if source_mode == "Excel - validação":
        st.info("Carregue a **BASE LIST.xlsx** para iniciar a análise da carteira e da meta restante.")
    elif source_mode == "Microsoft Lists":
        st.info("Clique em **Sincronizar Microsoft Lists** na barra lateral.")
    st.stop()

# ---------- Core analysis ----------
prepared = prepare_projects(projects, TIMEZONE)
baseline = build_assignment_baseline(projects, DESIGNERS, TARGETS, STATUS, TIMEZONE)
snapshot = build_daily_snapshots(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
quality = data_quality_summary(projects, STATUS)

eligible_norm = {normalize_person_name(n) for n in DESIGNERS}
pool_assigned = prepared[
    prepared["status_norm"].isin(STATUS.project_pool_set) & (prepared["assignee_norm"] != "")
]
unlisted_names = sorted({
    name for name, norm in zip(pool_assigned["assignee"], pool_assigned["assignee_norm"]) if norm not in eligible_norm
})

elapsed = productive_minutes_elapsed(NOW, TIMEZONE)
remaining = productive_minutes_remaining(NOW, TIMEZONE)
eligible_available = prepared[
    prepared["status_norm"].isin(STATUS.project_pool_set)
    & (prepared["assignee_norm"] == "")
    & prepared["posts_valid"]
    & prepared["sgo_present"]
]

with_load = int((baseline["Projetos já atribuídos"] > 0).sum())
without_load = int((baseline["Projetos já atribuídos"] == 0).sum())
known_assigned_posts = int(baseline["PLN já atribuído"].sum())
assigned_projects = int(baseline["Projetos já atribuídos"].sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Projetistas com carga", with_load)
c2.metric("Sem carga", without_load)
c3.metric("Projetos já atribuídos", assigned_projects)
c4.metric("PLN já atribuído", known_assigned_posts)
c5.metric("Disponíveis elegíveis", len(eligible_available))
c6.metric("Tempo útil restante", format_minutes(remaining))

st.caption(
    f"**Jornada:** {current_work_status(NOW, TIMEZONE)} • "
    f"Tempo produtivo: {format_minutes(elapsed)} / {format_minutes(TOTAL_WORK_MINUTES)}"
    + (f" • Última sincronização: {st.session_state.last_sync.strftime('%d/%m/%Y %H:%M:%S')}" if st.session_state.last_sync else "")
)

if quality["disponiveis_sem_pln"] or quality["atribuidos_sem_pln"] or quality["disponiveis_sem_sgo"]:
    st.warning(
        "Qualidade da base: "
        f"{quality['disponiveis_sem_pln']} disponível(is) sem PLN válido; "
        f"{quality['atribuidos_sem_pln']} já atribuído(s) sem PLN válido; "
        f"{quality['disponiveis_sem_sgo']} disponível(is) sem Nota SGO. "
        "Se uma obra já atribuída estiver sem PLN, a meta restante de postes fica parcial e novas atribuições automáticas "
        "para esse projetista são bloqueadas até o PLN ser informado."
    )
if unlisted_names:
    st.warning(
        f"Há {len(unlisted_names)} projetista(s) com obra 'Em projeto' que não constam na planilha PROJETISTAS.xlsx: "
        + ", ".join(unlisted_names)
    )

(tab_load, tab_today, tab_distribution, tab_automation, tab_projects, tab_week, tab_month, tab_predict, tab_quality, tab_config) = st.tabs([
    "🎯 Meta restante", "📊 Hoje", "⚙️ Distribuição", "🤖 Automação", "📋 Projetos", "📅 Semana", "🗓️ Mês", "📈 Preditivo", "🔎 Qualidade", "🔧 Configuração"
])

with tab_load:
    st.subheader("Carga já atribuída e meta restante")
    st.write(
        "Este quadro olha exclusivamente a carteira que já está com cada projetista na BASE LIST: "
        "**Status = Em projeto + Projetistas preenchido**. O PLN dessas obras é abatido da meta diária de carga."
    )
    load_cols = [
        "Projetista", "Projetos já atribuídos", "PLN já atribuído", "Projetos sem PLN",
        "Meta diária postes", "Meta diária projetos", "Meta restante postes", "Meta restante projetos",
        "Cobertura postes %", "Cobertura projetos %", "Nota SGO na carteira", "Situação da carga",
    ]
    st.dataframe(baseline[load_cols], use_container_width=True, hide_index=True)

    st.markdown("#### Regra aplicada")
    st.code(
        f"""Se já possui projetos Em projeto:\n  Meta restante de postes = {TARGETS.target_posts} - soma do PLN já atribuído\n  Meta restante de projetos = {TARGETS.target_projects} - quantidade de projetos já atribuídos\n\nSe não possui nenhum projeto Em projeto:\n  Meta restante = {TARGETS.target_posts} postes / {TARGETS.target_projects} projetos\n\nSe existe projeto atribuído sem PLN:\n  o cálculo de postes é parcial e a distribuição automática fica bloqueada para esse projetista até preencher o PLN."""
    )

    no_load = baseline[baseline["Projetos já atribuídos"] == 0]
    partial = baseline[(baseline["Projetos já atribuídos"] > 0) & ((baseline["Meta restante postes"] > 0) | (baseline["Meta restante projetos"] > 0))]
    covered = baseline[(baseline["Meta restante postes"] == 0) & (baseline["Meta restante projetos"] == 0)]
    b1, b2, b3 = st.columns(3)
    b1.metric("Meta inteira a distribuir", len(no_load))
    b2.metric("Meta parcialmente coberta", len(partial))
    b3.metric("Carga já cobre a meta", len(covered))

with tab_today:
    st.subheader("Produção do dia + carteira + meta diária")
    st.caption(
        "Aqui a conta fica dinâmica: o que já foi concluído hoje é somado à carteira ainda Em projeto. "
        "Assim, a distribuição considera o que o projetista já produziu e o que ainda tem para executar."
    )
    cols = [
        "Projetista", "Postes realizados", "Projetos realizados", "Postes em carteira", "Projetos em carteira",
        "Carteira sem PLN", "Potencial postes", "Potencial projetos", "Sem cobertura postes", "Sem cobertura projetos",
        "Meta postes agora", "Ritmo postes/h", "Ritmo necessário postes/h", "Previsão postes 18h", "Situação",
    ]
    st.dataframe(snapshot[cols], use_container_width=True, hide_index=True)
    chart_df = snapshot[["Projetista", "Postes realizados", "Postes em carteira"]].melt(
        id_vars="Projetista", var_name="Indicador", value_name="Postes"
    )
    fig = px.bar(chart_df, x="Projetista", y="Postes", color="Indicador", barmode="stack", title="Realizado + carteira por projetista")
    fig.add_hline(y=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
    st.plotly_chart(fig, use_container_width=True)

with tab_distribution:
    st.subheader("Distribuição automática")
    st.write(
        "Elegível = **Status Em projeto + Projetistas vazio + Nota SGO preenchida + PLN maior que zero**. "
        "O motor parte da carga já atribuída a cada projetista e distribui apenas o que falta para cobrir a meta."
    )
    suggestions, distribution_summary = suggest_assignments(projects, snapshot, TARGETS, STATUS)
    st.dataframe(distribution_summary, use_container_width=True, hide_index=True)
    if suggestions.empty:
        st.success("Nenhuma nova atribuição elegível é necessária ou a fila não possui carga suficiente.")
    else:
        st.markdown("#### Atribuições sugeridas")
        st.dataframe(suggestions.drop(columns=["etag"], errors="ignore"), use_container_width=True, hide_index=True)

        if source_mode in {"DEMO", "Excel - validação"}:
            if st.button("Simular estas atribuições", type="primary"):
                updated = projects.copy()
                for _, row in suggestions.iterrows():
                    mask = updated["item_id"].astype(str) == str(row["item_id"])
                    updated.loc[mask, "assignee"] = row["Projetista"]
                if source_mode == "DEMO":
                    st.session_state.demo_projects = updated
                else:
                    st.session_state.excel_projects = updated
                st.success("Atribuições simuladas. Nenhum dado foi gravado no Microsoft Lists.")
                st.rerun()
        else:
            if not WRITE_ENABLED:
                st.warning("Escrita bloqueada. Ative `write_enabled = true` somente após validar a coluna Projetistas no Lists.")
            else:
                confirm = st.checkbox("Confirmo a gravação destas atribuições no Microsoft Lists")
                if st.button("Aplicar no Microsoft Lists", type="primary", disabled=not confirm):
                    try:
                        repo = make_repository()
                        lookup_by_name = {
                            normalize_person_name(r["name"]): r.get("sharepoint_lookup_id")
                            for _, r in designers_df.iterrows()
                        }
                        count = 0
                        for _, row in suggestions.iterrows():
                            etag = None if pd.isna(row.get("etag")) else row.get("etag")
                            lookup_id = lookup_by_name.get(normalize_person_name(row["Projetista"]))
                            repo.assign_project(
                                item_id=str(row["item_id"]),
                                designer=str(row["Projetista"]),
                                etag=etag,
                                sharepoint_lookup_id=lookup_id,
                            )
                            count += 1
                        st.session_state.graph_projects = repo.fetch_projects()
                        st.session_state.column_diagnostics = repo.column_diagnostics()
                        st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
                        st.success(f"{count} projeto(s) atribuídos no Microsoft Lists.")
                        st.rerun()
                    except GraphError as exc:
                        st.error(str(exc))
                    except Exception as exc:
                        st.error(f"Falha ao aplicar atribuições: {exc}")

with tab_automation:
    st.subheader("Automação da distribuição")
    st.write(
        "Este módulo executa o mesmo motor da distribuição manual, mas em ciclos auditáveis. "
        "Enquanto o Microsoft Lists real não estiver validado, use o modo simulação ou o worker local."
    )
    a1, a2, a3 = st.columns(3)
    a1.metric("Janela atual", current_work_status(NOW, TIMEZONE))
    a2.metric("Tempo útil restante", format_minutes(productive_minutes_remaining(NOW, TIMEZONE)))
    a3.metric("Escrita Lists", "Liberada" if WRITE_ENABLED else "Bloqueada")

    policy = AutomationPolicy(timezone=TIMEZONE, require_work_hours=True)
    audit_path = "data/automation_audit.sqlite3"
    audit = AuditStore(audit_path)
    engine = AutomationEngine(TARGETS, STATUS, policy=policy, audit=audit)

    if st.button("Executar ciclo automático agora", type="primary", use_container_width=True):
        result = engine.run_cycle(projects, DESIGNERS, NOW, source=source_mode, mode="dry-run")
        st.session_state["last_auto_result"] = result

    result = st.session_state.get("last_auto_result")
    if result is not None:
        if result.status == "success":
            st.success(result.message)
        elif result.status == "skipped":
            st.info(result.message)
        else:
            st.warning(result.message)
        if not result.suggestions.empty:
            st.markdown("#### Atribuições que o ciclo faria")
            st.dataframe(result.suggestions.drop(columns=["etag"], errors="ignore"), use_container_width=True, hide_index=True)
        if not result.distribution_summary.empty:
            st.markdown("#### Resultado por projetista")
            st.dataframe(result.distribution_summary, use_container_width=True, hide_index=True)

    st.markdown("#### Como automatizar sem Microsoft Lists real")
    st.code(
        "python worker.py --base BASE_LIST.xlsx --designers PROJETISTAS.xlsx --mode dry-run --watch --interval 300",
        language="bash",
    )
    st.caption(
        "O worker reavalia a carga a cada ciclo. Para gerar uma cópia do Excel com as atribuições, "
        "use --mode excel-copy. O arquivo original não é alterado."
    )

    recent = audit.recent_cycles(10)
    if not recent.empty:
        st.markdown("#### Últimos ciclos")
        st.dataframe(recent, use_container_width=True, hide_index=True)

with tab_projects:
    st.subheader("Base operacional")
    show = prepared.copy()
    show["Disponibilidade"] = ""
    pool_mask = show["status_norm"].isin(STATUS.project_pool_set)
    show.loc[pool_mask & (show["assignee_norm"] == ""), "Disponibilidade"] = "Disponível"
    show.loc[pool_mask & (show["assignee_norm"] != ""), "Disponibilidade"] = "Atribuído"
    display = show[["note", "sgo", "status", "posts", "posts_valid", "assignee", "regional", "municipality", "deadline", "Disponibilidade"]].rename(columns={
        "note": "Nº da nota", "sgo": "Nota SGO", "status": "Status", "posts": "PLN", "posts_valid": "PLN válido",
        "assignee": "Projetista", "regional": "Regional", "municipality": "Município", "deadline": "Prazo"
    })
    st.dataframe(display, use_container_width=True, hide_index=True)

with tab_week:
    st.subheader("Acompanhamento semanal")
    week = weekly_metrics(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
    st.dataframe(week, use_container_width=True, hide_index=True)
    st.caption("A meta semanal é apenas consolidada para análise. O excedente de um dia não compensa outro dia.")

with tab_month:
    st.subheader("Acompanhamento mensal")
    month = monthly_metrics(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
    st.dataframe(month, use_container_width=True, hide_index=True)
    if not month.empty:
        fig_month = px.bar(month, x="Projetista", y=["Postes", "Referência postes"], barmode="group", title="Postes x referência acumulada")
        st.plotly_chart(fig_month, use_container_width=True)

with tab_predict:
    st.subheader("Análise preditiva")
    pred = monthly_prediction(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
    cols = [
        "Projetista", "Média postes/dia útil", "Média projetos/dia útil", "Projeção postes mês", "Meta mensal postes",
        "Projeção projetos mês", "Meta mensal projetos", "Consistência meta cheia %", "Projetos sem PLN", "Tendência",
    ]
    st.dataframe(pred[cols], use_container_width=True, hide_index=True)
    st.caption("A previsão usa Data de entrega do projeto para identificar a produção concluída por dia e PLN para contabilizar postes.")

with tab_quality:
    st.subheader("Qualidade e elegibilidade da base")
    q1, q2, q3, q4, q5 = st.columns(5)
    q1.metric("Em projeto", quality["em_projeto"])
    q2.metric("Sem projetista", quality["disponiveis"])
    q3.metric("Já atribuídos", quality["atribuidos"])
    q4.metric("Disponíveis sem PLN", quality["disponiveis_sem_pln"])
    q5.metric("Atribuídos sem PLN", quality["atribuidos_sem_pln"])
    blocked = prepared[
        prepared["status_norm"].isin(STATUS.project_pool_set)
        & (prepared["assignee_norm"] == "")
        & (~prepared["posts_valid"] | ~prepared["sgo_present"])
    ][["note", "sgo", "posts", "regional", "municipality"]].rename(columns={"note": "Nº da nota", "sgo": "Nota SGO", "posts": "PLN", "regional": "Regional", "municipality": "Município"})
    if not blocked.empty:
        st.markdown("#### Obras bloqueadas para distribuição automática")
        st.dataframe(blocked, use_container_width=True, hide_index=True)
    if unlisted_names:
        st.markdown("#### Atribuições para nomes fora da planilha de projetistas")
        st.write(unlisted_names)

with tab_config:
    st.subheader("Regras atuais")
    st.code(
        f"""Jornada: 08:00–12:00 / 13:12–18:00
Tempo produtivo: 528 minutos
Meta: {TARGETS.target_posts} postes / {TARGETS.target_projects} projetos por dia
Faixa mínima: {TARGETS.min_posts} postes / {TARGETS.min_projects} projetos
Meta cumulativa: NÃO
Status da fila: Em projeto
Disponível: Em projeto + Projetistas vazio
Atribuído: Em projeto + Projetistas preenchido
Peso da obra: PLN (coluna R)
Identificador operacional: Nota SGO (coluna C)
Regra de carga existente: abater PLN e quantidade de projetos já atribuídos da meta diária
Sem projeto atribuído: meta integral {TARGETS.target_posts} postes / {TARGETS.target_projects} projetos
Projeto atribuído sem PLN: bloquear nova distribuição automática até regularização
Fonte atual: {source_mode}
Escrita no Lists: {'SIM' if WRITE_ENABLED else 'NÃO'}"""
    )
    st.markdown("#### Mapeamento configurado")
    st.json(FIELD_MAP.__dict__)
    if source_mode == "Microsoft Lists" and not st.session_state.column_diagnostics.empty:
        st.markdown("#### Colunas detectadas no Microsoft Lists")
        st.dataframe(st.session_state.column_diagnostics, use_container_width=True, hide_index=True)
        assignee_rows = st.session_state.column_diagnostics[st.session_state.column_diagnostics["Campo lógico"] == "assignee"]
        if not assignee_rows.empty and bool(assignee_rows["Pessoa/Grupo"].any()):
            st.warning("Projetistas é Pessoa/Grupo. Para escrita automática, inclua SharePointLookupId na planilha de projetistas ou configure um resolvedor corporativo de IDs.")
