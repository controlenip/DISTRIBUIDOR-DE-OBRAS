from __future__ import annotations

from datetime import datetime, time
import hashlib
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st

from src.audit_store import AuditStore
from src.automation_engine import AutomationEngine, AutomationPolicy
from src.demo_data import sample_designers_df, sample_projects
from src.distribution_engine import suggest_assignments
from src.excel_loader import load_base_excel, load_designers_excel
from src.excel_writer import generate_distributed_excel_bytes
from src.graph_client import GraphClient, GraphError
from src.lists_repository import FieldMap, ListsProjectRepository
from src.metrics import (
    build_assignment_baseline,
    build_daily_snapshots,
    data_quality_summary,
    monthly_metrics,
    prepare_projects,
    weekly_metrics,
)
from src.models import StatusConfig, Targets
from src.name_utils import normalize_person_name
from src.performance_analytics import (
    designer_attention_table,
    designer_monthly_prediction_advanced,
    management_insights,
)
from src.work_schedule import (
    TOTAL_WORK_MINUTES,
    current_work_status,
    format_minutes,
    productive_minutes_elapsed,
    productive_minutes_remaining,
)


# -----------------------------------------------------------------------------
# APP + VISUAL SYSTEM
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="NIP Smart Distribuição",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --nip-blue:#123B68;
        --nip-blue2:#1F5D96;
        --nip-cyan:#2D8FC7;
        --nip-soft:#F5F8FB;
        --nip-line:#DDE6EF;
        --nip-green:#1F7A55;
        --nip-orange:#B76A00;
        --nip-red:#B42318;
    }
    .block-container {padding-top: 1.2rem; padding-bottom: 2.5rem; max-width: 1500px;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg,#0E2C4D 0%,#123B68 100%);}
    [data-testid="stSidebar"] * {color:#F4F8FC;}
    [data-testid="stSidebar"] [data-baseweb="radio"] label {
        background:rgba(255,255,255,.04); border-radius:8px; padding:6px 8px;
    }
    .hero {
        padding: 22px 26px; border-radius: 18px;
        background: linear-gradient(120deg,#0E2C4D 0%,#14507E 62%,#2381B6 100%);
        color: white; margin-bottom: 18px; box-shadow: 0 10px 28px rgba(13,44,77,.16);
    }
    .hero h1 {font-size: 2rem; margin:0; line-height:1.1;}
    .hero p {margin:8px 0 0 0; opacity:.92; font-size:1rem;}
    .section-title {font-size:1.15rem; font-weight:750; color:#123B68; margin:6px 0 10px;}
    .subtle {color:#5E7185; font-size:.94rem;}
    .step-card {
        border:1px solid var(--nip-line); border-radius:14px; padding:16px 18px;
        background:#FFFFFF; min-height:105px; box-shadow:0 2px 8px rgba(15,42,68,.04);
    }
    .step-card .num {
        display:inline-flex; width:28px; height:28px; border-radius:50%;
        align-items:center; justify-content:center; background:#E7F1F8; color:#123B68;
        font-weight:800; margin-right:7px;
    }
    .step-card b {color:#123B68; font-size:1.02rem;}
    .step-card p {margin:8px 0 0; color:#62778A; font-size:.91rem;}
    .info-card {padding:14px 16px; border:1px solid var(--nip-line); border-radius:12px; background:#F8FAFC; margin-bottom:9px;}
    .success-card {padding:15px 18px; border:1px solid #B8E2CB; border-radius:12px; background:#F1FBF5;}
    .warning-card {padding:15px 18px; border:1px solid #F2D2A4; border-radius:12px; background:#FFF8ED;}
    .rule-card {padding:15px 18px; border-left:4px solid #2D8FC7; border-radius:9px; background:#F5F9FC;}
    div[data-testid="stMetric"] {background:#FFFFFF; border:1px solid #E3EAF1; padding:12px 14px; border-radius:13px; box-shadow:0 2px 9px rgba(15,42,68,.05);}
    div[data-testid="stMetric"] label {font-weight:650; color:#486176;}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {color:#123B68; font-weight:780;}
    .stButton > button[kind="primary"] {border-radius:10px; font-weight:750; min-height:47px;}
    .stDownloadButton > button {border-radius:10px; font-weight:750; min-height:45px;}
    [data-baseweb="tab-list"] {gap:5px; flex-wrap:wrap;}
    [data-baseweb="tab"] {border-radius:9px 9px 0 0; padding-left:12px; padding-right:12px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------
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


def style_figure(fig, height: int = 390):
    fig.update_layout(
        height=height,
        margin=dict(l=12, r=12, t=55, b=15),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text="",
        font=dict(size=12),
    )
    fig.update_xaxes(gridcolor="rgba(120,140,160,.12)")
    fig.update_yaxes(gridcolor="rgba(120,140,160,.12)")
    return fig


def fmt_num(value) -> str:
    value = float(value or 0)
    return str(int(value)) if value.is_integer() else f"{value:.1f}"


def status_badge(status: str) -> str:
    mapping = {
        "Meta atingida": "✅ Meta atingida",
        "Faixa mínima atingida": "🟢 Faixa mínima atingida",
        "Carteira suficiente": "🔵 Carteira suficiente",
        "Falta de carga": "🟠 Precisa de mais obras",
        "Risco produtivo": "🔴 Risco de não atingir",
        "Encerrado abaixo da meta": "🔴 Fechou abaixo da meta",
        "PLN pendente na carteira": "🟡 Revisar PLN",
    }
    return mapping.get(status, status)


def compact_load_table(baseline: pd.DataFrame, target_posts: int, target_projects: int) -> pd.DataFrame:
    columns = ["Projetista", "Carteira atual", "Ainda precisa", "Cobertura da carteira", "Situação"]
    if baseline.empty:
        return pd.DataFrame(columns=columns)

    df = baseline.copy()
    for col in ["Projetos já atribuídos", "PLN já atribuído", "Projetos sem PLN", "Meta restante postes", "Meta restante projetos"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    def friendly_status(row) -> str:
        if row["Projetos sem PLN"] > 0:
            return "🟡 Revisar PLN"
        if row["Projetos já atribuídos"] <= 0:
            return "🔴 Sem obras"
        if row["Meta restante postes"] <= 0 and row["Meta restante projetos"] <= 0:
            return "✅ Carteira completa"
        return "🟠 Precisa de mais obras"

    df["Carteira atual"] = df.apply(
        lambda r: f'{fmt_num(r["PLN já atribuído"])} postes • {fmt_num(r["Projetos já atribuídos"])} projetos', axis=1
    )
    df["Ainda precisa"] = df.apply(
        lambda r: f'{fmt_num(max(0, r["Meta restante postes"]))} postes • {fmt_num(max(0, r["Meta restante projetos"]))} projetos', axis=1
    )
    posts_cov = (df["PLN já atribuído"] / max(1, target_posts) * 100).clip(lower=0, upper=100)
    projects_cov = (df["Projetos já atribuídos"] / max(1, target_projects) * 100).clip(lower=0, upper=100)
    df["Cobertura da carteira"] = pd.concat([posts_cov, projects_cov], axis=1).min(axis=1).round(0)
    df["Situação"] = df.apply(friendly_status, axis=1)
    return df.sort_values(["Cobertura da carteira", "Projetista"])[columns].reset_index(drop=True)


def compact_load_config():
    return {
        "Projetista": st.column_config.TextColumn("Projetista", width="large"),
        "Carteira atual": st.column_config.TextColumn("Carteira atual", width="medium"),
        "Ainda precisa": st.column_config.TextColumn("Ainda precisa", width="medium"),
        "Cobertura da carteira": st.column_config.ProgressColumn(
            "Cobertura da carteira",
            help="Quanto da meta de 30 postes e 5 projetos já está coberto pelas obras atualmente atribuídas.",
            min_value=0,
            max_value=100,
            format="%d%%",
            width="medium",
        ),
        "Situação": st.column_config.TextColumn("Situação", width="medium"),
    }


def compact_daily_table(snapshot: pd.DataFrame, target_posts: int, target_projects: int, current_day: bool) -> pd.DataFrame:
    columns = ["Projetista", "Fez no dia", "Carteira atual", "Falta para a meta", "Estimativa", "Situação"]
    if snapshot.empty:
        return pd.DataFrame(columns=columns)

    df = snapshot.copy()
    numeric_cols = [
        "Postes realizados", "Projetos realizados", "Postes em carteira", "Projetos em carteira",
        "Previsão postes 18h", "Previsão projetos 18h",
    ]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df["Fez no dia"] = df.apply(
        lambda r: f'{fmt_num(r["Postes realizados"])} postes • {fmt_num(r["Projetos realizados"])} projetos', axis=1
    )
    df["Carteira atual"] = df.apply(
        lambda r: f'{fmt_num(r["Postes em carteira"])} postes • {fmt_num(r["Projetos em carteira"])} projetos', axis=1
    )
    df["Falta para a meta"] = df.apply(
        lambda r: f'{fmt_num(max(0, target_posts-r["Postes realizados"]))} postes • {fmt_num(max(0, target_projects-r["Projetos realizados"]))} projetos', axis=1
    )
    df["Estimativa"] = df.apply(
        lambda r: f'{fmt_num(r["Previsão postes 18h"])} postes • {fmt_num(r["Previsão projetos 18h"])} projetos', axis=1
    )
    df["Situação"] = df["Situação"].map(status_badge)
    return df[columns]


def compact_daily_config(current_day: bool):
    estimate_name = "Estimativa até 18h" if current_day else "Fechamento do dia"
    return {
        "Projetista": st.column_config.TextColumn("Projetista", width="large"),
        "Fez no dia": st.column_config.TextColumn("Fez no dia", width="medium"),
        "Carteira atual": st.column_config.TextColumn("Carteira atual", width="medium"),
        "Falta para a meta": st.column_config.TextColumn("Falta para a meta", width="medium"),
        "Estimativa": st.column_config.TextColumn(estimate_name, width="medium"),
        "Situação": st.column_config.TextColumn("Situação", width="medium"),
    }


def render_insights(items: list[str], max_items: int = 4):
    if not items:
        st.info("Ainda não há dados suficientes para gerar insights.")
        return
    for item in items[:max_items]:
        st.markdown(f'<div class="info-card">💡 {item}</div>', unsafe_allow_html=True)


# -----------------------------------------------------------------------------
# CONFIGURATION
# -----------------------------------------------------------------------------
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


for key, default in {
    "demo_projects": sample_projects(TIMEZONE),
    "excel_projects": pd.DataFrame(),
    "uploaded_designers": pd.DataFrame(),
    "graph_projects": pd.DataFrame(),
    "last_sync": None,
    "column_diagnostics": pd.DataFrame(),
    "base_excel_bytes": b"",
    "base_excel_name": "",
    "base_excel_signature": "",
    "designers_signature": "",
    "request_auto_distribution": False,
    "generated_excel_bytes": b"",
    "generated_excel_name": "",
    "generated_distribution_suggestions": pd.DataFrame(),
    "generated_distribution_summary": pd.DataFrame(),
    "uploader_epoch": 0,
    "data_cleared_notice": False,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def clear_working_data():
    """Return the app to a clean state without changing configuration/secrets."""
    st.session_state.demo_projects = sample_projects(TIMEZONE)
    st.session_state.excel_projects = pd.DataFrame()
    st.session_state.uploaded_designers = pd.DataFrame()
    st.session_state.graph_projects = pd.DataFrame()
    st.session_state.last_sync = None
    st.session_state.column_diagnostics = pd.DataFrame()
    st.session_state.base_excel_bytes = b""
    st.session_state.base_excel_name = ""
    st.session_state.base_excel_signature = ""
    st.session_state.designers_signature = ""
    st.session_state.request_auto_distribution = False
    st.session_state.generated_excel_bytes = b""
    st.session_state.generated_excel_name = ""
    st.session_state.generated_distribution_suggestions = pd.DataFrame()
    st.session_state.generated_distribution_summary = pd.DataFrame()
    st.session_state.pop("last_auto_result", None)

    # Force file uploaders to be recreated with fresh widget keys.
    st.session_state.uploader_epoch = int(st.session_state.get("uploader_epoch", 0)) + 1
    st.session_state.data_cleared_notice = True

    # Clear cached data, if any helper has been cached in future versions.
    try:
        st.cache_data.clear()
    except Exception:
        pass


NOW = datetime.now(ZoneInfo(TIMEZONE))


# -----------------------------------------------------------------------------
# SIDEBAR: SIMPLE NAVIGATION FIRST, TECHNICAL OPTIONS SECOND
# -----------------------------------------------------------------------------
st.sidebar.markdown("## ⚡ NIP Smart")
st.sidebar.caption("Distribuição de obras e produtividade")

PAGE = st.sidebar.radio(
    "Menu",
    ["🏠 Início", "⚡ Distribuir obras", "👷 Produtividade", "🔎 Dados e regras"],
    index=0,
)

st.sidebar.divider()
st.sidebar.markdown("**Como usar**")
st.sidebar.caption("1. Carregue as duas planilhas")
st.sidebar.caption("2. Gere a distribuição")
st.sidebar.caption("3. Baixe a nova BASE LIST")

st.sidebar.divider()
if st.sidebar.button(
    "🧹 Limpar dados",
    use_container_width=True,
    help="Remove os arquivos carregados e todos os resultados temporários desta sessão.",
):
    clear_working_data()
    st.rerun()

with st.sidebar.expander("Opções avançadas"):
    source_mode = st.selectbox("Fonte de dados", ["Excel - validação", "Microsoft Lists", "DEMO"], index=0)
    st.caption("Use Microsoft Lists somente quando a integração real estiver configurada.")

st.sidebar.divider()
st.sidebar.caption(
    f"Meta diária: **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**  \n"
    f"Faixa mínima: **{TARGETS.min_posts} postes / {TARGETS.min_projects} projetos**"
)

analysis_date = NOW.date()
if PAGE == "👷 Produtividade":
    analysis_date = st.sidebar.date_input(
        "Data da produtividade",
        value=NOW.date(),
        max_value=NOW.date(),
        help="Use para consultar um dia anterior. Para o dia atual, a ferramenta considera o horário corrente.",
    )

if analysis_date == NOW.date():
    ANALYSIS_NOW = NOW
else:
    ANALYSIS_NOW = datetime.combine(analysis_date, time(18, 0), tzinfo=ZoneInfo(TIMEZONE))


# -----------------------------------------------------------------------------
# HERO
# -----------------------------------------------------------------------------
page_subtitles = {
    "🏠 Início": "Carregue as bases, entenda a carga atual da equipe e faça a distribuição em poucos passos.",
    "⚡ Distribuir obras": "Veja o que está disponível, como a carga será equilibrada e gere a planilha distribuída.",
    "👷 Produtividade": "Acompanhe quem cumpriu a meta, quem precisa de atenção e a tendência semanal e mensal.",
    "🔎 Dados e regras": "Consulte qualidade da base, regras da distribuição e opções técnicas sem poluir a operação diária.",
}
st.markdown(
    f"""
    <div class="hero">
      <h1>⚡ NIP Smart Distribuição</h1>
      <p>{page_subtitles[PAGE]}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if st.session_state.get("data_cleared_notice"):
    st.success("🧹 Dados limpos. A ferramenta está pronta para receber uma nova BASE LIST e uma nova lista de projetistas.")
    st.session_state.data_cleared_notice = False


# -----------------------------------------------------------------------------
# SOURCE INPUTS
# -----------------------------------------------------------------------------
def reset_generated_output():
    st.session_state.generated_excel_bytes = b""
    st.session_state.generated_excel_name = ""
    st.session_state.generated_distribution_suggestions = pd.DataFrame()
    st.session_state.generated_distribution_summary = pd.DataFrame()


def render_excel_uploads():
    st.markdown('<div class="section-title">Passo 1 — Carregue os arquivos</div>', unsafe_allow_html=True)
    st.caption("Você precisa de dois arquivos: a BASE LIST exportada e a lista de projetistas que podem receber obras.")
    left, right = st.columns(2)
    with left:
        base_upload = st.file_uploader(
            "BASE LIST (.xlsx)",
            type=["xlsx"],
            key=f"base_list_main_v11_{st.session_state.uploader_epoch}",
            help="Arquivo exportado do Microsoft Lists com as obras.",
        )
        if base_upload is not None:
            try:
                base_bytes = base_upload.getvalue()
                sig = hashlib.sha256(base_bytes).hexdigest()
                if sig != st.session_state.base_excel_signature:
                    reset_generated_output()
                st.session_state.base_excel_bytes = base_bytes
                st.session_state.base_excel_name = base_upload.name
                st.session_state.base_excel_signature = sig
                st.session_state.excel_projects = load_base_excel(base_upload)
                st.success(f"✅ BASE LIST pronta — {len(st.session_state.excel_projects):,} registros".replace(",", "."))
            except Exception as exc:
                st.error(f"Não foi possível ler a BASE LIST: {exc}")
    with right:
        designer_upload = st.file_uploader(
            "PROJETISTAS (.xlsx)",
            type=["xlsx"],
            key=f"designers_main_v11_{st.session_state.uploader_epoch}",
            help="Lista de projetistas que podem receber novas obras.",
        )
        if designer_upload is not None:
            try:
                designer_bytes = designer_upload.getvalue()
                sig = hashlib.sha256(designer_bytes).hexdigest()
                if sig != st.session_state.designers_signature:
                    reset_generated_output()
                st.session_state.designers_signature = sig
                st.session_state.uploaded_designers = load_designers_excel(designer_upload)
                st.success(f"✅ Lista pronta — {len(st.session_state.uploaded_designers)} projetistas")
            except Exception as exc:
                st.error(f"Não foi possível ler PROJETISTAS.xlsx: {exc}")


def render_lists_input():
    st.markdown('<div class="section-title">Conexão com Microsoft Lists</div>', unsafe_allow_html=True)
    designer_upload = st.file_uploader("PROJETISTAS.xlsx", type=["xlsx"], key=f"designers_lists_v11_{st.session_state.uploader_epoch}")
    if designer_upload is not None:
        try:
            st.session_state.uploaded_designers = load_designers_excel(designer_upload)
            st.success(f"✅ {len(st.session_state.uploaded_designers)} projetistas carregados")
        except Exception as exc:
            st.error(f"Falha ao ler PROJETISTAS.xlsx: {exc}")
    if not GRAPH_READY:
        st.warning("A integração com Microsoft Lists ainda não está configurada nos Secrets do Streamlit.")
    elif st.button("🔄 Atualizar dados do Microsoft Lists", use_container_width=True):
        try:
            repo = make_repository()
            st.session_state.graph_projects = repo.fetch_projects()
            st.session_state.column_diagnostics = repo.column_diagnostics()
            st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
            st.success("Dados atualizados com sucesso.")
        except Exception as exc:
            st.error(str(exc))


if PAGE == "🏠 Início":
    if source_mode == "Excel - validação":
        render_excel_uploads()
    elif source_mode == "Microsoft Lists":
        render_lists_input()

# Resolve source after potential uploads
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
source_ready = bool(DESIGNERS) and not projects.empty

if not source_ready:
    if PAGE != "🏠 Início":
        st.warning("Comece pela página **Início** e carregue a BASE LIST e a planilha PROJETISTAS.")
    else:
        if source_mode == "Excel - validação":
            st.info("Assim que os dois arquivos forem carregados, o resumo da equipe e o botão de distribuição serão liberados.")
        elif source_mode == "Microsoft Lists":
            st.info("Carregue PROJETISTAS.xlsx e sincronize o Microsoft Lists para continuar.")
    st.stop()


# -----------------------------------------------------------------------------
# COMMON ANALYTICS
# -----------------------------------------------------------------------------
prepared = prepare_projects(projects, TIMEZONE)
baseline = build_assignment_baseline(projects, DESIGNERS, TARGETS, STATUS, TIMEZONE)
live_snapshot = build_daily_snapshots(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
analysis_snapshot = build_daily_snapshots(projects, DESIGNERS, ANALYSIS_NOW, TARGETS, STATUS, TIMEZONE)
quality = data_quality_summary(projects, STATUS)
week = weekly_metrics(projects, DESIGNERS, ANALYSIS_NOW, TARGETS, STATUS, TIMEZONE)
month = monthly_metrics(projects, DESIGNERS, ANALYSIS_NOW, TARGETS, STATUS, TIMEZONE)
designer_pred = designer_monthly_prediction_advanced(projects, DESIGNERS, ANALYSIS_NOW, TARGETS, STATUS, TIMEZONE)
designer_attention = designer_attention_table(analysis_snapshot, TARGETS.target_posts, TARGETS.target_projects)

eligible_norm = {normalize_person_name(n) for n in DESIGNERS}
pool_assigned = prepared[prepared["status_norm"].isin(STATUS.project_pool_set) & (prepared["assignee_norm"] != "")]
unlisted_names = sorted({
    name for name, norm in zip(pool_assigned["assignee"], pool_assigned["assignee_norm"])
    if norm not in eligible_norm
})

eligible_available = prepared[
    prepared["status_norm"].isin(STATUS.project_pool_set)
    & (prepared["assignee_norm"] == "")
    & prepared["posts_valid"]
    & prepared["sgo_present"]
]
available_posts = int(eligible_available["posts"].sum())
without_load = int((baseline["Projetos já atribuídos"] == 0).sum())
pending_pln = int((baseline["Projetos sem PLN"] > 0).sum())
partial_load = int(((baseline["Projetos já atribuídos"] > 0) & ((baseline["Meta restante postes"] > 0) | (baseline["Meta restante projetos"] > 0))).sum())
covered_load = int(((baseline["Projetos sem PLN"] == 0) & (baseline["Meta restante postes"] == 0) & (baseline["Meta restante projetos"] == 0)).sum())

elapsed = productive_minutes_elapsed(NOW, TIMEZONE)
remaining = productive_minutes_remaining(NOW, TIMEZONE)

live_suggestions, live_distribution_summary = suggest_assignments(projects, live_snapshot, TARGETS, STATUS)


def generate_distribution_file():
    try:
        suggestions, distribution_summary = suggest_assignments(projects, live_snapshot, TARGETS, STATUS)
        if suggestions.empty:
            reset_generated_output()
            st.session_state.generated_distribution_summary = distribution_summary
            st.info("No momento, não há novas obras elegíveis que precisem ser distribuídas.")
            return
        if source_mode != "Excel - validação":
            st.session_state.generated_distribution_suggestions = suggestions
            st.session_state.generated_distribution_summary = distribution_summary
            return
        generated_at = datetime.now(ZoneInfo(TIMEZONE))
        output_bytes = generate_distributed_excel_bytes(
            st.session_state.base_excel_bytes,
            suggestions,
            distribution_summary=distribution_summary,
            target_posts=TARGETS.target_posts,
            target_projects=TARGETS.target_projects,
            generated_at=generated_at,
        )
        stem = (st.session_state.base_excel_name or "BASE_LIST.xlsx").rsplit(".", 1)[0]
        st.session_state.generated_excel_bytes = output_bytes
        st.session_state.generated_excel_name = f"{stem}_DISTRIBUIDA_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
        st.session_state.generated_distribution_suggestions = suggestions
        st.session_state.generated_distribution_summary = distribution_summary
    except Exception as exc:
        st.error(f"Não foi possível gerar a distribuição: {exc}")


def render_download_result():
    suggestions = st.session_state.generated_distribution_suggestions
    if source_mode == "Excel - validação" and st.session_state.generated_excel_bytes:
        st.markdown(
            f'<div class="success-card"><b>✅ Distribuição pronta.</b><br>{len(suggestions)} obra(s) foram atribuídas em uma cópia da BASE LIST. O arquivo original não foi alterado.</div>',
            unsafe_allow_html=True,
        )
        st.write("")
        left, right = st.columns([3, 1])
        with left:
            st.download_button(
                "⬇️ Baixar BASE LIST distribuída",
                data=st.session_state.generated_excel_bytes,
                file_name=st.session_state.generated_excel_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        right.metric("Novas atribuições", len(suggestions))
    elif source_mode == "Microsoft Lists" and not suggestions.empty:
        st.success(f"Prévia gerada com {len(suggestions)} nova(s) atribuição(ões).")


# -----------------------------------------------------------------------------
# PAGE: HOME
# -----------------------------------------------------------------------------
if PAGE == "🏠 Início":
    st.markdown('<div class="section-title">O fluxo é este</div>', unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown('<div class="step-card"><span class="num">1</span><b>Carregar as bases</b><p>BASE LIST + PROJETISTAS. A ferramenta identifica o que cada pessoa já tem em carteira.</p></div>', unsafe_allow_html=True)
    with s2:
        st.markdown('<div class="step-card"><span class="num">2</span><b>Distribuir automaticamente</b><p>As obras são direcionadas primeiro para quem tem menor cobertura da meta diária.</p></div>', unsafe_allow_html=True)
    with s3:
        st.markdown('<div class="step-card"><span class="num">3</span><b>Baixar e usar</b><p>Você recebe uma nova BASE LIST com a coluna Projetistas preenchida nas obras distribuídas.</p></div>', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="section-title">Resumo da equipe antes da distribuição</div>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Projetistas", len(DESIGNERS))
    k2.metric("Sem obras", without_load)
    k3.metric("Carga parcial", partial_load)
    k4.metric("Carteira completa", covered_load)
    k5.metric("Obras prontas p/ distribuir", len(eligible_available))

    st.caption(
        "**Carteira** = obras com Status **Em projeto** já atribuídas ao projetista. "
        f"A referência diária é **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**."
    )

    st.markdown('<div class="section-title">Passo 2 — Gerar a distribuição</div>', unsafe_allow_html=True)
    blocked_count = quality["disponiveis_sem_pln"] + quality["disponiveis_sem_sgo"]
    a1, a2, a3 = st.columns(3)
    a1.metric("Obras disponíveis", len(eligible_available))
    a2.metric("Postes disponíveis", available_posts)
    a3.metric("Obras bloqueadas por dados", blocked_count)

    if source_mode == "Excel - validação":
        if st.button("⚡ GERAR DISTRIBUIÇÃO AUTOMÁTICA", type="primary", use_container_width=True):
            generate_distribution_file()
        st.caption("A BASE original não é modificada. A ferramenta cria uma nova planilha para download.")
        render_download_result()
    else:
        st.info("A distribuição detalhada está disponível na página **Distribuir obras**.")

    st.markdown('<div class="section-title">Conferir carga da equipe</div>', unsafe_allow_html=True)
    load_view = compact_load_table(baseline, TARGETS.target_posts, TARGETS.target_projects)
    st.dataframe(
        load_view,
        use_container_width=True,
        hide_index=True,
        column_config=compact_load_config(),
        height=min(620, 78 + 35 * len(load_view)),
    )

    st.write("")
    left, right = st.columns([1.45, 1])
    with left:
        chart = baseline[["Projetista", "PLN já atribuído", "Projetos já atribuídos"]].copy().sort_values("PLN já atribuído")
        fig = px.bar(
            chart,
            y="Projetista",
            x="PLN já atribuído",
            orientation="h",
            hover_data=["Projetos já atribuídos"],
            title="Carga atual em postes por projetista",
        )
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        st.plotly_chart(style_figure(fig, max(380, 27 * len(chart))), use_container_width=True)
    with right:
        st.markdown('<div class="section-title">Leitura rápida</div>', unsafe_allow_html=True)
        insights = management_insights(live_snapshot, baseline, designer_pred, len(eligible_available), available_posts)
        render_insights(insights, max_items=4)


# -----------------------------------------------------------------------------
# PAGE: DISTRIBUTION
# -----------------------------------------------------------------------------
elif PAGE == "⚡ Distribuir obras":
    st.markdown('<div class="section-title">Antes de distribuir</div>', unsafe_allow_html=True)
    st.caption("A ferramenta só considera obras prontas para uso e não retira obras que já estão atribuídas a alguém.")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Obras prontas", len(eligible_available))
    d2.metric("Postes disponíveis", available_posts)
    d3.metric("Projetistas sem obras", without_load)
    d4.metric("Novas atribuições sugeridas", len(live_suggestions))

    st.markdown(
        '<div class="rule-card"><b>Uma obra entra na distribuição quando:</b> Status = Em projeto, Projetistas está vazio, Nota SGO está preenchida e PLN é maior que zero.</div>',
        unsafe_allow_html=True,
    )
    st.write("")

    if live_suggestions.empty:
        st.info("Não há novas atribuições sugeridas com a situação atual da base.")
    else:
        preview_cols = [c for c in ["Projetista", "Nota SGO", "PLN", "Regional", "Município"] if c in live_suggestions.columns]
        preview = live_suggestions[preview_cols].copy() if preview_cols else live_suggestions.drop(columns=["etag"], errors="ignore")
        st.markdown("#### Prévia — quem receberá cada obra")
        st.dataframe(preview, use_container_width=True, hide_index=True)

    if source_mode == "Excel - validação":
        if st.button("⚡ Gerar nova BASE LIST distribuída", type="primary", use_container_width=True, disabled=live_suggestions.empty):
            generate_distribution_file()
        render_download_result()
    elif source_mode == "DEMO" and not live_suggestions.empty:
        if st.button("Simular distribuição nesta sessão", type="primary", use_container_width=True):
            updated = projects.copy()
            for _, row in live_suggestions.iterrows():
                updated.loc[updated["item_id"].astype(str) == str(row["item_id"]), "assignee"] = row["Projetista"]
            st.session_state.demo_projects = updated
            st.success("Distribuição simulada.")
            st.rerun()
    elif source_mode == "Microsoft Lists" and not live_suggestions.empty:
        if not WRITE_ENABLED:
            st.warning("A gravação no Microsoft Lists está bloqueada. A prévia acima é somente leitura.")
        else:
            confirm = st.checkbox("Confirmo que quero gravar essas atribuições no Microsoft Lists")
            if st.button("Aplicar no Microsoft Lists", type="primary", use_container_width=True, disabled=not confirm):
                try:
                    repo = make_repository()
                    lookup_by_name = {
                        normalize_person_name(r["name"]): r.get("sharepoint_lookup_id")
                        for _, r in designers_df.iterrows()
                    }
                    for _, row in live_suggestions.iterrows():
                        etag = None if pd.isna(row.get("etag")) else row.get("etag")
                        lookup_id = lookup_by_name.get(normalize_person_name(row["Projetista"]))
                        repo.assign_project(str(row["item_id"]), str(row["Projetista"]), etag, lookup_id)
                    st.session_state.graph_projects = repo.fetch_projects()
                    st.session_state.column_diagnostics = repo.column_diagnostics()
                    st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
                    st.success(f"{len(live_suggestions)} projeto(s) atribuídos no Microsoft Lists.")
                    st.rerun()
                except GraphError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Falha ao aplicar: {exc}")

    if not live_distribution_summary.empty:
        st.markdown("#### Como fica a carga depois da distribuição")
        summary = live_distribution_summary.copy()
        wanted = [
            "Projetista", "Potencial postes após distribuição", "Potencial projetos após distribuição",
            "Novos projetos sugeridos", "Novos postes sugeridos",
        ]
        wanted = [c for c in wanted if c in summary.columns]
        st.dataframe(summary[wanted], use_container_width=True, hide_index=True)
        if "Potencial postes após distribuição" in summary.columns:
            plot = summary.sort_values("Potencial postes após distribuição")
            fig = px.bar(
                plot,
                y="Projetista",
                x="Potencial postes após distribuição",
                orientation="h",
                title="Carga em postes após a distribuição sugerida",
            )
            fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
            st.plotly_chart(style_figure(fig, max(400, 26 * len(plot))), use_container_width=True)

    with st.expander("Como a ferramenta decide quem recebe primeiro?"):
        st.markdown(
            f"""
            - Primeiro olha quanto cada projetista já tem em carteira.
            - Prioriza quem está com **menor cobertura** da meta de **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**.
            - Distribui em rodadas para evitar concentrar várias obras em uma única pessoa.
            - Obra já atribuída não é redistribuída automaticamente.
            - Obra sem Nota SGO ou sem PLN válido fica fora da distribuição até o dado ser corrigido.
            - Excedente de um dia não reduz a meta do dia seguinte.
            """
        )


# -----------------------------------------------------------------------------
# PAGE: PRODUCTIVITY
# -----------------------------------------------------------------------------
elif PAGE == "👷 Produtividade":
    selected_label = ANALYSIS_NOW.strftime("%d/%m/%Y")
    is_current_day = analysis_date == NOW.date()
    st.markdown(f'<div class="section-title">Produtividade em {selected_label}</div>', unsafe_allow_html=True)
    st.caption(
        "**Produção do dia** = projetos com Data de entrega do projeto na data selecionada. "
        "Postes = Qtd. de poste final; quando estiver vazia, o sistema usa o PLN como apoio."
    )

    total_posts_day = int(pd.to_numeric(analysis_snapshot["Postes realizados"], errors="coerce").fillna(0).sum())
    total_projects_day = int(pd.to_numeric(analysis_snapshot["Projetos realizados"], errors="coerce").fillna(0).sum())
    full_meta = int((analysis_snapshot["Situação"] == "Meta atingida").sum())
    attention_count = len(designer_attention)

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Postes entregues", total_posts_day)
    p2.metric("Projetos entregues", total_projects_day)
    p3.metric("Meta cheia atingida", full_meta)
    p4.metric("Precisam de atenção", attention_count)

    if is_current_day:
        st.caption(
            f"Jornada agora: **{current_work_status(NOW, TIMEZONE)}** • "
            f"Tempo útil restante: **{format_minutes(productive_minutes_remaining(NOW, TIMEZONE))}**"
        )

    today_tab, period_tab, predict_tab = st.tabs(["📍 Dia selecionado", "📅 Semana e mês", "📈 Projeção"])

    with today_tab:
        st.markdown("#### Quem precisa de atenção")
        if designer_attention.empty:
            st.success("Nenhum projetista está sinalizado para atenção nesta data.")
        else:
            if is_current_day and productive_minutes_remaining(NOW, TIMEZONE) > 0:
                st.caption("Durante o expediente, entram aqui quem está abaixo do ritmo, sem carga suficiente ou com risco de não fechar a meta.")
            else:
                st.caption("Após o fim do dia, entram aqui os projetistas que fecharam abaixo da meta ou tiveram pendência de carga/dados.")
            attention_view = designer_attention.copy()
            attention_config = compact_daily_config(is_current_day)
            if not is_current_day:
                attention_view = attention_view.drop(columns=["Carteira atual"], errors="ignore")
                attention_config.pop("Carteira atual", None)
            st.dataframe(
                attention_view,
                use_container_width=True,
                hide_index=True,
                column_config=attention_config,
                height=min(520, 78 + 35 * len(attention_view)),
            )

        st.markdown("#### Resultado de toda a equipe")
        daily_view = compact_daily_table(analysis_snapshot, TARGETS.target_posts, TARGETS.target_projects, is_current_day)
        daily_config = compact_daily_config(is_current_day)
        if not is_current_day:
            daily_view = daily_view.drop(columns=["Carteira atual"], errors="ignore")
            daily_config.pop("Carteira atual", None)
        st.dataframe(
            daily_view,
            use_container_width=True,
            hide_index=True,
            column_config=daily_config,
            height=min(650, 78 + 35 * len(daily_view)),
        )

        plot = analysis_snapshot[["Projetista", "Postes realizados"]].copy().sort_values("Postes realizados")
        fig = px.bar(plot, y="Projetista", x="Postes realizados", orientation="h", title="Postes entregues por projetista")
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        fig.add_vline(x=TARGETS.min_posts, line_dash="dot", annotation_text=f"Mínimo {TARGETS.min_posts}")
        st.plotly_chart(style_figure(fig, max(390, 27 * len(plot))), use_container_width=True)

        with st.expander("Ver indicadores detalhados do dia"):
            detail_cols = [
                "Projetista", "Postes realizados", "Projetos realizados", "Postes em carteira", "Projetos em carteira",
                "Meta postes agora", "Meta projetos agora", "Aderência postes %", "Aderência projetos %",
                "Previsão postes 18h", "Previsão projetos 18h", "Status ritmo", "Situação",
            ]
            st.dataframe(analysis_snapshot[detail_cols], use_container_width=True, hide_index=True)

    with period_tab:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Semana")
            week_simple_cols = [c for c in ["Projetista", "Postes", "Projetos", "Dias meta cheia", "Consistência meta cheia %"] if c in week.columns]
            st.dataframe(week[week_simple_cols], use_container_width=True, hide_index=True)
            if not week.empty:
                fig = px.bar(week, x="Projetista", y="Postes", title="Postes entregues na semana")
                st.plotly_chart(style_figure(fig, 380), use_container_width=True)
        with right:
            st.markdown("#### Mês")
            month_simple_cols = [c for c in ["Projetista", "Postes", "Projetos", "Dias meta cheia", "Consistência meta cheia %"] if c in month.columns]
            st.dataframe(month[month_simple_cols], use_container_width=True, hide_index=True)
            if not month.empty:
                fig = px.bar(month, x="Projetista", y="Postes", title="Postes entregues no mês")
                st.plotly_chart(style_figure(fig, 380), use_container_width=True)
        st.info("A referência semanal e mensal serve para acompanhamento. O excedente de um dia não vira crédito para o dia seguinte.")

    with predict_tab:
        st.markdown("#### Tendência de fechamento do mês")
        st.caption("A projeção usa a produção acumulada e o ritmo médio dos últimos 5 dias úteis.")
        if designer_pred.empty:
            st.info("Ainda não há dados suficientes para projeção.")
        else:
            simple_cols = [
                c for c in [
                    "Projetista", "Postes mês", "Projetos mês", "Projeção postes mês", "Projeção projetos mês",
                    "Consistência meta cheia %", "Tendência",
                ] if c in designer_pred.columns
            ]
            st.dataframe(designer_pred[simple_cols], use_container_width=True, hide_index=True)

            trend_counts = designer_pred["Tendência"].value_counts().rename_axis("Tendência").reset_index(name="Projetistas")
            fig = px.pie(trend_counts, names="Tendência", values="Projetistas", hole=.58, title="Situação projetada do mês")
            st.plotly_chart(style_figure(fig, 390), use_container_width=True)

            need = designer_pred[designer_pred["Tendência"] == "Requer acompanhamento"]
            st.markdown("#### Projetistas que merecem acompanhamento")
            if need.empty:
                st.success("Nenhum projetista está projetado abaixo da faixa de acompanhamento neste momento.")
            else:
                st.dataframe(need[simple_cols], use_container_width=True, hide_index=True)

            with st.expander("Ver análise preditiva completa"):
                st.dataframe(designer_pred, use_container_width=True, hide_index=True)


# -----------------------------------------------------------------------------
# PAGE: DATA + RULES
# -----------------------------------------------------------------------------
elif PAGE == "🔎 Dados e regras":
    st.markdown('<div class="section-title">Qualidade da BASE LIST</div>', unsafe_allow_html=True)
    q1, q2, q3, q4, q5 = st.columns(5)
    q1.metric("Obras Em projeto", quality["em_projeto"])
    q2.metric("Disponíveis", quality["disponiveis"])
    q3.metric("Já atribuídas", quality["atribuidos"])
    q4.metric("Disponíveis sem PLN", quality["disponiveis_sem_pln"])
    q5.metric("Disponíveis sem SGO", quality["disponiveis_sem_sgo"])

    if quality["disponiveis_sem_pln"] or quality["disponiveis_sem_sgo"] or quality["atribuidos_sem_pln"]:
        st.warning(
            "Algumas obras precisam de correção de dados antes de serem tratadas com segurança. "
            "Use as seções abaixo para localizar essas pendências."
        )

    with st.expander("Obras bloqueadas para distribuição"):
        blocked = prepared[
            prepared["status_norm"].isin(STATUS.project_pool_set)
            & (prepared["assignee_norm"] == "")
            & (~prepared["posts_valid"] | ~prepared["sgo_present"])
        ][["note", "sgo", "posts", "regional", "municipality"]].rename(columns={
            "note": "Nº da nota", "sgo": "Nota SGO", "posts": "PLN", "regional": "Regional", "municipality": "Município"
        })
        if blocked.empty:
            st.success("Nenhuma obra disponível está bloqueada por falta de SGO ou PLN.")
        else:
            st.dataframe(blocked, use_container_width=True, hide_index=True)

    if unlisted_names:
        with st.expander("Projetistas atribuídos que não estão na planilha PROJETISTAS"):
            st.write(unlisted_names)

    with st.expander("Consultar a BASE LIST carregada"):
        show = prepared.copy()
        show["Disponibilidade"] = ""
        pool_mask = show["status_norm"].isin(STATUS.project_pool_set)
        show.loc[pool_mask & (show["assignee_norm"] == ""), "Disponibilidade"] = "Disponível"
        show.loc[pool_mask & (show["assignee_norm"] != ""), "Disponibilidade"] = "Atribuído"
        display = show[[
            "note", "sgo", "status", "posts", "assignee", "regional", "municipality", "deadline", "Disponibilidade",
        ]].rename(columns={
            "note": "Nº da nota", "sgo": "Nota SGO", "status": "Status", "posts": "PLN",
            "assignee": "Projetista", "regional": "Regional", "municipality": "Município", "deadline": "Prazo",
        })
        st.dataframe(display, use_container_width=True, hide_index=True)

    with st.expander("Regras da ferramenta", expanded=True):
        st.markdown(
            f"""
            **Meta diária do projetista**
            - Referência: **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**.
            - Faixa mínima: **{TARGETS.min_posts} postes / {TARGETS.min_projects} projetos**.
            - A meta é **diária e não cumulativa**.

            **O que conta como carteira**
            - Obra com Status **Em projeto** e campo **Projetistas preenchido**.
            - O peso da obra é o **PLN da coluna R**.

            **O que pode ser distribuído**
            - Status **Em projeto**.
            - Projetistas vazio.
            - Nota SGO preenchida.
            - PLN maior que zero.

            **O que conta como produção**
            - Projeto com **Data de entrega do projeto** na data analisada.
            - Postes: **Qtd. de poste**; se estiver vazia, PLN é usado como apoio.

            **Jornada**
            - 08:00–12:00 e 13:12–18:00.
            - Tempo produtivo total: **{TOTAL_WORK_MINUTES} minutos**.
            """
        )

    with st.expander("Microsoft Lists — configuração avançada"):
        if source_mode != "Microsoft Lists":
            st.caption("Altere a Fonte de dados para Microsoft Lists em Opções avançadas, na barra lateral, quando for iniciar a integração real.")
        st.write("Escrita no Microsoft Lists:", "**Liberada**" if WRITE_ENABLED else "**Bloqueada**")
        if source_mode == "Microsoft Lists" and not st.session_state.column_diagnostics.empty:
            st.dataframe(st.session_state.column_diagnostics, use_container_width=True, hide_index=True)
        with st.expander("Ver mapeamento técnico de colunas"):
            st.json(FIELD_MAP.__dict__)

    with st.expander("Automação avançada por ciclos"):
        st.caption("Área técnica para executar o motor de automação sem alterar o fluxo simples de uso diário.")
        policy = AutomationPolicy(timezone=TIMEZONE, require_work_hours=True)
        audit = AuditStore("data/automation_audit.sqlite3")
        engine = AutomationEngine(TARGETS, STATUS, policy=policy, audit=audit)
        if st.button("Executar ciclo de simulação agora", use_container_width=True):
            st.session_state["last_auto_result"] = engine.run_cycle(projects, DESIGNERS, NOW, source=source_mode, mode="dry-run")
        result = st.session_state.get("last_auto_result")
        if result is not None:
            if result.status == "success":
                st.success(result.message)
            elif result.status == "skipped":
                st.info(result.message)
            else:
                st.warning(result.message)
            if not result.suggestions.empty:
                st.dataframe(result.suggestions.drop(columns=["etag"], errors="ignore"), use_container_width=True, hide_index=True)
        recent = audit.recent_cycles(10)
        if not recent.empty:
            st.markdown("**Últimos ciclos**")
            st.dataframe(recent, use_container_width=True, hide_index=True)
