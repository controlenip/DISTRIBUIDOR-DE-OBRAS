from __future__ import annotations

from datetime import date, datetime, time, timedelta
from io import BytesIO
import hashlib
from uuid import uuid4
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
from src.experience_rules import (
    DIFFICULTY_LEVELS,
    EXPERIENCE_LEVELS,
    EXPERIENCE_MODES,
    match_penalty,
    normalize_difficulty_label,
    normalize_experience_label,
)
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
from src.name_utils import normalize_person_name, normalize_text
from src.notifications import send_distribution_webhook
from src.performance_analytics import (
    daily_close_summary,
    designer_attention_table,
    designer_daily_history,
    designer_monthly_prediction_advanced,
    designer_quality_proxy,
    management_insights,
    portfolio_balance_metrics,
)
from src.report_writer import generate_daily_close_excel
from src.work_schedule import (
    TOTAL_WORK_MINUTES,
    current_work_status,
    format_minutes,
    productive_minutes_remaining,
)

POSTS_LABEL = "Postes Alterados/Novos"
PROJECT_TYPE_LABEL = "PI (Tipo Projeto)"


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
        --nip-navy:#0E2C4D;
        --nip-blue:#123B68;
        --nip-blue2:#0D5EA6;
        --nip-cyan:#2D8FC7;
        --nip-orange:#F97316;
        --nip-orange2:#EA580C;
        --nip-green:#15803D;
        --nip-green2:#166534;
        --nip-red:#DC2626;
        --nip-red2:#B91C1C;
        --nip-soft:#F5F8FB;
        --nip-line:#DDE6EF;
    }
    .block-container {padding-top: 1.1rem; padding-bottom: 2.5rem; max-width: 1500px;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg,#0E2C4D 0%,#123B68 100%);}
    [data-testid="stSidebar"] * {color:#F4F8FC;}
    [data-testid="stSidebar"] [data-baseweb="radio"] label {
        background:rgba(255,255,255,.045); border-radius:8px; padding:6px 8px;
    }
    .hero {
        padding: 22px 26px; border-radius: 18px;
        background: linear-gradient(120deg,#0E2C4D 0%,#14507E 62%,#2381B6 100%);
        color: white; margin-bottom: 18px; box-shadow: 0 10px 28px rgba(13,44,77,.16);
    }
    .hero h1 {font-size: 2rem; margin:0; line-height:1.1;}
    .hero p {margin:8px 0 0 0; opacity:.92; font-size:1rem;}
    .section-title {font-size:1.16rem; font-weight:780; color:#123B68; margin:8px 0 10px;}
    .subtle {color:#5E7185; font-size:.94rem;}
    .step-card {
        border:1px solid var(--nip-line); border-radius:14px; padding:16px 18px;
        background:#FFFFFF; min-height:108px; box-shadow:0 2px 8px rgba(15,42,68,.04);
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
    .danger-card {padding:15px 18px; border:1px solid #F1B8B8; border-radius:12px; background:#FFF4F4;}
    .rule-card {padding:15px 18px; border-left:4px solid #2D8FC7; border-radius:9px; background:#F5F9FC;}
    div[data-testid="stMetric"] {background:#FFFFFF; border:1px solid #E3EAF1; padding:12px 14px; border-radius:13px; box-shadow:0 2px 9px rgba(15,42,68,.05);}
    div[data-testid="stMetric"] label {font-weight:650; color:#486176;}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {color:#123B68; font-weight:780;}

    /* Main action buttons: blue by default, orange for primary actions. */
    .stButton > button {border-radius:10px; font-weight:760; min-height:45px; border:1px solid #0D5EA6;}
    .stButton > button:not([kind="primary"]) {background:#0D5EA6; color:#FFFFFF;}
    .stButton > button:not([kind="primary"]):hover {background:#094B87; color:#FFFFFF; border-color:#094B87;}
    .stButton > button[kind="primary"] {background:#F97316; color:#FFFFFF; border-color:#F97316; min-height:48px;}
    .stButton > button[kind="primary"]:hover {background:#EA580C; color:#FFFFFF; border-color:#EA580C;}

    /* Downloads are success actions. */
    .stDownloadButton > button {border-radius:10px; font-weight:780; min-height:46px; background:#15803D; color:#FFFFFF; border:1px solid #15803D;}
    .stDownloadButton > button:hover {background:#166534; color:#FFFFFF; border-color:#166534;}

    /* The sidebar action is intentionally red so 'Limpar dados' is obvious. */
    [data-testid="stSidebar"] .stButton > button:not([kind="primary"]) {background:#1F5D96 !important; color:#FFFFFF !important; border:1px solid #2D8FC7 !important; font-weight:750 !important;}
    [data-testid="stSidebar"] .stButton > button:not([kind="primary"]):hover {background:#174B79 !important; border-color:#2D8FC7 !important;}
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {background:#DC2626 !important; color:#FFFFFF !important; border:1px solid #DC2626 !important; font-weight:850 !important;}
    [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {background:#B91C1C !important; border-color:#B91C1C !important;}
    [data-testid="stSidebar"] .stButton > button:disabled {background:#6B7280 !important; color:#E5E7EB !important; border-color:#6B7280 !important; opacity:.8;}

    /* Sidebar number inputs / steppers: force high contrast so +/- are always visible. */
    [data-testid="stSidebar"] [data-testid="stNumberInput"] label,
    [data-testid="stSidebar"] [data-testid="stNumberInput"] p {
        color:#F8FAFC !important; font-weight:650 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] input {
        background:#FFFFFF !important; color:#0F172A !important; border:1px solid #BFD2E6 !important;
        border-radius:10px 0 0 10px !important; font-weight:700 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button {
        background:#E8F0F8 !important; color:#123B68 !important; border:1px solid #BFD2E6 !important;
        opacity:1 !important; min-width:34px !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button:hover {
        background:#D7E7F5 !important; color:#0E2C4D !important; border-color:#96B5D3 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInput"] button svg {
        fill:#123B68 !important; color:#123B68 !important; opacity:1 !important;
    }
    [data-testid="stSidebar"] [data-testid="stNumberInputContainer"] {
        background:transparent !important;
    }

    /* Sidebar expander: keep header readable against the dark sidebar. */
    [data-testid="stSidebar"] [data-testid="stExpander"] details {
        border:1px solid #2D8FC7 !important;
        border-radius:10px !important;
        overflow:hidden !important;
        background:#123B68 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        background:#174B79 !important;
        color:#FFFFFF !important;
        min-height:46px !important;
        font-weight:760 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary:hover {
        background:#1F5D96 !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary *,
    [data-testid="stSidebar"] [data-testid="stExpander"] summary svg {
        color:#FFFFFF !important;
        fill:#FFFFFF !important;
        opacity:1 !important;
    }

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
        "Faixa mínima atingida": "🟢 Faixa mínima",
        "Carteira suficiente": "🔵 Carteira suficiente",
        "Falta de carga": "🟠 Precisa de mais obras",
        "Risco produtivo": "🔴 Risco de não atingir",
        "Encerrado abaixo da meta": "🔴 Fechou abaixo da meta",
        "PLN pendente na carteira": "🟡 Revisar Postes Alterados/Novos",
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
            return "🟡 Revisar Postes Alterados/Novos"
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
            "Cobertura da carteira", min_value=0, max_value=100, format="%d%%", width="medium",
        ),
        "Situação": st.column_config.TextColumn("Situação", width="medium"),
    }


def compact_daily_table(snapshot: pd.DataFrame, target_posts: int, target_projects: int) -> pd.DataFrame:
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
    df["Fez no dia"] = df.apply(lambda r: f'{fmt_num(r["Postes realizados"])} postes • {fmt_num(r["Projetos realizados"])} projetos', axis=1)
    df["Carteira atual"] = df.apply(lambda r: f'{fmt_num(r["Postes em carteira"])} postes • {fmt_num(r["Projetos em carteira"])} projetos', axis=1)
    df["Falta para a meta"] = df.apply(lambda r: f'{fmt_num(max(0, target_posts-r["Postes realizados"]))} postes • {fmt_num(max(0, target_projects-r["Projetos realizados"]))} projetos', axis=1)
    df["Estimativa"] = df.apply(lambda r: f'{fmt_num(r["Previsão postes 18h"])} postes • {fmt_num(r["Previsão projetos 18h"])} projetos', axis=1)
    df["Situação"] = df["Situação"].map(status_badge)
    return df[columns]


def compact_daily_config(current_day: bool):
    return {
        "Projetista": st.column_config.TextColumn("Projetista", width="large"),
        "Fez no dia": st.column_config.TextColumn("Fez no dia", width="medium"),
        "Carteira atual": st.column_config.TextColumn("Carteira atual", width="medium"),
        "Falta para a meta": st.column_config.TextColumn("Falta para a meta", width="medium"),
        "Estimativa": st.column_config.TextColumn("Estimativa até 18h" if current_day else "Fechamento do dia", width="medium"),
        "Situação": st.column_config.TextColumn("Situação", width="medium"),
    }


def render_insights(items: list[str], max_items: int = 4):
    if not items:
        st.info("Ainda não há dados suficientes para gerar insights.")
        return
    for item in items[:max_items]:
        st.markdown(f'<div class="info-card">💡 {item}</div>', unsafe_allow_html=True)


def reset_generated_output():
    st.session_state.generated_excel_bytes = b""
    st.session_state.generated_excel_name = ""
    st.session_state.generated_distribution_suggestions = pd.DataFrame()
    st.session_state.generated_distribution_summary = pd.DataFrame()


def reset_simulation():
    st.session_state.simulated_suggestions = pd.DataFrame()
    st.session_state.simulated_summary = pd.DataFrame()
    st.session_state.simulation_signature = ""
    st.session_state.simulation_cycle_id = ""
    reset_generated_output()


# -----------------------------------------------------------------------------
# CONFIGURATION + SESSION
# -----------------------------------------------------------------------------
SECRETS = secrets_dict()
TIMEZONE = nested(SECRETS, "app", "timezone", default="America/Fortaleza")
BASE_DEFAULTS = {
    "min_posts": int(nested(SECRETS, "app", "min_posts", default=25)),
    "target_posts": int(nested(SECRETS, "app", "target_posts", default=30)),
    "min_projects": int(nested(SECRETS, "app", "min_projects", default=4)),
    "target_projects": int(nested(SECRETS, "app", "target_projects", default=5)),
    "max_portfolio_posts": int(nested(SECRETS, "app", "max_portfolio_posts", default=36)),
    "max_portfolio_projects": int(nested(SECRETS, "app", "max_portfolio_projects", default=6)),
    "priority_enabled": bool(nested(SECRETS, "app", "priority_enabled", default=True)),
    "experience_enabled": bool(nested(SECRETS, "app", "experience_enabled", default=False)),
    "experience_mode": str(nested(SECRETS, "app", "experience_mode", default="Preferencial") or "Preferencial"),
}

SESSION_DEFAULTS = {
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
    "generated_excel_bytes": b"",
    "generated_excel_name": "",
    "generated_distribution_suggestions": pd.DataFrame(),
    "generated_distribution_summary": pd.DataFrame(),
    "simulated_suggestions": pd.DataFrame(),
    "simulated_summary": pd.DataFrame(),
    "simulation_signature": "",
    "simulation_cycle_id": "",
    "uploader_epoch": 0,
    "data_cleared_notice": False,
    "admin_authenticated": False,
    "notify_after_distribution": False,
    "auto_sync_lists": False,
    "cfg_min_posts": BASE_DEFAULTS["min_posts"],
    "cfg_target_posts": BASE_DEFAULTS["target_posts"],
    "cfg_min_projects": BASE_DEFAULTS["min_projects"],
    "cfg_target_projects": BASE_DEFAULTS["target_projects"],
    "cfg_max_portfolio_posts": BASE_DEFAULTS["max_portfolio_posts"],
    "cfg_max_portfolio_projects": BASE_DEFAULTS["max_portfolio_projects"],
    "cfg_priority_enabled": BASE_DEFAULTS["priority_enabled"],
    "cfg_experience_enabled": BASE_DEFAULTS["experience_enabled"],
    "cfg_experience_mode": BASE_DEFAULTS["experience_mode"],
    "designer_experience_profile": pd.DataFrame(),
    "project_difficulty_profile": pd.DataFrame(),
    "experience_profile_source_signature": "",
}
for key, default in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


def clear_working_data():
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
    st.session_state.designer_experience_profile = pd.DataFrame()
    st.session_state.project_difficulty_profile = pd.DataFrame()
    st.session_state.experience_profile_source_signature = ""
    for widget_key in [
        "designer_experience_editor_v13", "project_difficulty_editor_v13",
        "distribution_editor_v13", "experience_toggle_page_v13",
    ]:
        st.session_state.pop(widget_key, None)
    reset_simulation()
    st.session_state.pop("last_auto_result", None)
    st.session_state.uploader_epoch = int(st.session_state.get("uploader_epoch", 0)) + 1
    st.session_state.data_cleared_notice = True
    try:
        st.cache_data.clear()
    except Exception:
        pass


ADMIN_PIN = str(nested(SECRETS, "access", "admin_pin", default="") or "")
DEFAULT_ROLE = str(nested(SECRETS, "access", "default_role", default="Administrador") or "Administrador")
WRITE_ENABLED = bool(nested(SECRETS, "app", "write_enabled", default=False))
WEBHOOK_URL = str(nested(SECRETS, "notifications", "webhook_url", default="") or "")

STATUS = StatusConfig(
    project_pool=tuple(nested(SECRETS, "lists", "status", "project_pool", default=["Em projeto"])),
    completed=tuple(nested(SECRETS, "lists", "status", "completed", default=["Concluído", "Concluido"])),
)
FIELD_MAP = FieldMap(
    note=nested(SECRETS, "lists", "fields", "note", default="N° da nota"),
    sgo=nested(SECRETS, "lists", "fields", "sgo", default="Nota SGO"),
    status=nested(SECRETS, "lists", "fields", "status", default="Status do projeto"),
    project_type=nested(SECRETS, "lists", "fields", "project_type", default="PI (Tipo Projeto)"),
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


# -----------------------------------------------------------------------------
# SIDEBAR
# -----------------------------------------------------------------------------
st.sidebar.markdown("## ⚡ NIP Smart")
st.sidebar.caption("Distribuição de obras e produtividade")

PAGE = st.sidebar.radio(
    "Menu",
    ["🏠 Início", "⚡ Distribuir obras", "👷 Produtividade", "🔎 Dados e regras"],
    index=0,
    key="nav_page",
)

st.sidebar.divider()
role_choice = st.sidebar.selectbox("Perfil", ["Administrador", "Consulta"], index=0 if DEFAULT_ROLE == "Administrador" else 1)
if role_choice == "Administrador" and ADMIN_PIN:
    if not st.session_state.admin_authenticated:
        pin_value = st.sidebar.text_input("PIN do administrador", type="password")
        if st.sidebar.button("🔐 Liberar administração", use_container_width=True):
            if pin_value == ADMIN_PIN:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.sidebar.error("PIN inválido")
    CAN_EDIT = bool(st.session_state.admin_authenticated)
else:
    CAN_EDIT = role_choice == "Administrador"

st.sidebar.caption("Modo: **Administrador**" if CAN_EDIT else "Modo: **Consulta**")

st.sidebar.divider()
st.sidebar.markdown("**Como usar**")
st.sidebar.caption("1. Carregue as duas planilhas")
st.sidebar.caption("2. Simule e confira")
st.sidebar.caption("3. Gere e baixe a nova BASE LIST")

st.sidebar.divider()
if st.sidebar.button("🧹 LIMPAR DADOS", type="primary", use_container_width=True, help="Apaga arquivos e resultados temporários desta sessão."):
    clear_working_data()
    st.rerun()

with st.sidebar.expander("⚙️ Opções avançadas"):
    source_mode = st.selectbox("Fonte de dados", ["Excel - validação", "Microsoft Lists", "DEMO"], index=0)
    st.caption("Use Microsoft Lists somente quando a integração real estiver configurada.")

    if CAN_EDIT:
        st.markdown("**Parâmetros da distribuição**")
        st.session_state.cfg_target_posts = st.number_input("Meta postes/dia", min_value=1, max_value=200, value=int(st.session_state.cfg_target_posts))
        st.session_state.cfg_target_projects = st.number_input("Meta projetos/dia", min_value=1, max_value=30, value=int(st.session_state.cfg_target_projects))
        st.session_state.cfg_min_posts = st.number_input("Faixa mínima - postes", min_value=1, max_value=int(st.session_state.cfg_target_posts), value=min(int(st.session_state.cfg_min_posts), int(st.session_state.cfg_target_posts)))
        st.session_state.cfg_min_projects = st.number_input("Faixa mínima - projetos", min_value=1, max_value=int(st.session_state.cfg_target_projects), value=min(int(st.session_state.cfg_min_projects), int(st.session_state.cfg_target_projects)))
        st.session_state.cfg_max_portfolio_posts = st.number_input("Teto de carteira - postes", min_value=int(st.session_state.cfg_target_posts), max_value=300, value=max(int(st.session_state.cfg_max_portfolio_posts), int(st.session_state.cfg_target_posts)))
        st.session_state.cfg_max_portfolio_projects = st.number_input("Teto de carteira - projetos", min_value=int(st.session_state.cfg_target_projects), max_value=40, value=max(int(st.session_state.cfg_max_portfolio_projects), int(st.session_state.cfg_target_projects)))
        st.session_state.cfg_priority_enabled = st.toggle("Considerar Prioridade e Prazo", value=bool(st.session_state.cfg_priority_enabled))
        if WEBHOOK_URL:
            st.session_state.notify_after_distribution = st.toggle("Notificar após gerar distribuição", value=bool(st.session_state.notify_after_distribution))

TARGETS = Targets(
    min_posts=int(st.session_state.cfg_min_posts),
    target_posts=int(st.session_state.cfg_target_posts),
    min_projects=int(st.session_state.cfg_min_projects),
    target_projects=int(st.session_state.cfg_target_projects),
)
MAX_PORTFOLIO_POSTS = int(st.session_state.cfg_max_portfolio_posts)
MAX_PORTFOLIO_PROJECTS = int(st.session_state.cfg_max_portfolio_projects)
PRIORITY_ENABLED = bool(st.session_state.cfg_priority_enabled)
EXPERIENCE_ENABLED = bool(st.session_state.cfg_experience_enabled)
EXPERIENCE_MODE = str(st.session_state.cfg_experience_mode or "Preferencial")

st.sidebar.divider()
st.sidebar.caption(
    f"Meta: **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**  \n"
    f"Teto de carteira: **{MAX_PORTFOLIO_POSTS} postes / {MAX_PORTFOLIO_PROJECTS} projetos**"
)

NOW = datetime.now(ZoneInfo(TIMEZONE))
analysis_date = NOW.date()
if PAGE == "👷 Produtividade":
    analysis_date = st.sidebar.date_input("Data da produtividade", value=NOW.date(), max_value=NOW.date())
ANALYSIS_NOW = NOW if analysis_date == NOW.date() else datetime.combine(analysis_date, time(18, 0), tzinfo=ZoneInfo(TIMEZONE))


# -----------------------------------------------------------------------------
# HERO
# -----------------------------------------------------------------------------
page_subtitles = {
    "🏠 Início": "Carregue as bases, veja a situação da equipe e siga o fluxo guiado até o download.",
    "⚡ Distribuir obras": "Simule, confira, ajuste e só depois gere a distribuição definitiva.",
    "👷 Produtividade": "Acompanhe metas, consistência, histórico individual e projeções.",
    "🔎 Dados e regras": "Valide a base, consulte auditoria, regras e integrações técnicas.",
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
    st.success("🧹 Dados limpos. A sessão voltou ao estado inicial.")
    st.session_state.data_cleared_notice = False


# -----------------------------------------------------------------------------
# SOURCE INPUTS
# -----------------------------------------------------------------------------
def render_excel_uploads():
    st.markdown('<div class="section-title">Passo 1 — Carregue os arquivos</div>', unsafe_allow_html=True)
    st.caption("BASE LIST exportada + lista de projetistas habilitados a receber obras.")
    left, right = st.columns(2)
    with left:
        base_upload = st.file_uploader(
            "BASE LIST (.xlsx)", type=["xlsx"], key=f"base_list_v13_{st.session_state.uploader_epoch}",
            help="Arquivo exportado do Microsoft Lists com as obras.",
        )
        if base_upload is not None:
            try:
                base_bytes = base_upload.getvalue()
                sig = hashlib.sha256(base_bytes).hexdigest()
                if sig != st.session_state.base_excel_signature:
                    reset_simulation()
                    st.session_state.experience_profile_source_signature = ""
                    st.session_state.pop("project_difficulty_editor_v13", None)
                    st.session_state.pop("distribution_editor_v13", None)
                st.session_state.base_excel_bytes = base_bytes
                st.session_state.base_excel_name = base_upload.name
                st.session_state.base_excel_signature = sig
                st.session_state.excel_projects = load_base_excel(base_upload)
                st.success(f"✅ BASE LIST pronta — {len(st.session_state.excel_projects):,} registros".replace(",", "."))
            except Exception as exc:
                st.error(f"Não foi possível ler a BASE LIST: {exc}")
    with right:
        designer_upload = st.file_uploader(
            "PROJETISTAS (.xlsx)", type=["xlsx"], key=f"designers_v13_{st.session_state.uploader_epoch}",
            help="Lista oficial de projetistas que podem receber novas obras.",
        )
        if designer_upload is not None:
            try:
                designer_bytes = designer_upload.getvalue()
                sig = hashlib.sha256(designer_bytes).hexdigest()
                if sig != st.session_state.designers_signature:
                    reset_simulation()
                    st.session_state.experience_profile_source_signature = ""
                    st.session_state.pop("designer_experience_editor_v13", None)
                    st.session_state.pop("distribution_editor_v13", None)
                st.session_state.designers_signature = sig
                st.session_state.uploaded_designers = load_designers_excel(designer_upload)
                st.success(f"✅ Lista pronta — {len(st.session_state.uploaded_designers)} projetistas")
            except Exception as exc:
                st.error(f"Não foi possível ler PROJETISTAS.xlsx: {exc}")


def sync_lists_now():
    repo = make_repository()
    st.session_state.graph_projects = repo.fetch_projects()
    st.session_state.column_diagnostics = repo.column_diagnostics()
    st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
    st.session_state.experience_profile_source_signature = ""
    st.session_state.pop("project_difficulty_editor_v13", None)
    reset_simulation()


def render_lists_input():
    st.markdown('<div class="section-title">Conexão com Microsoft Lists</div>', unsafe_allow_html=True)
    designer_upload = st.file_uploader("PROJETISTAS.xlsx", type=["xlsx"], key=f"designers_lists_v13_{st.session_state.uploader_epoch}")
    if designer_upload is not None:
        try:
            designer_bytes = designer_upload.getvalue()
            sig = hashlib.sha256(designer_bytes).hexdigest()
            if sig != st.session_state.designers_signature:
                reset_simulation()
                st.session_state.experience_profile_source_signature = ""
                st.session_state.pop("designer_experience_editor_v13", None)
                st.session_state.designers_signature = sig
            st.session_state.uploaded_designers = load_designers_excel(BytesIO(designer_bytes))
            st.success(f"✅ {len(st.session_state.uploaded_designers)} projetistas carregados")
        except Exception as exc:
            st.error(f"Falha ao ler PROJETISTAS.xlsx: {exc}")
    if not GRAPH_READY:
        st.warning("A integração com Microsoft Lists ainda não está configurada nos Secrets do Streamlit.")
        return
    if st.button("🔄 Atualizar dados do Microsoft Lists", use_container_width=True):
        try:
            sync_lists_now()
            st.success("Microsoft Lists atualizado.")
        except Exception as exc:
            st.error(f"Falha ao sincronizar: {exc}")
    if CAN_EDIT:
        st.session_state.auto_sync_lists = st.toggle("Atualizar automaticamente a cada 5 minutos", value=bool(st.session_state.auto_sync_lists))


if PAGE == "🏠 Início":
    if source_mode == "Excel - validação":
        render_excel_uploads()
    elif source_mode == "Microsoft Lists":
        render_lists_input()

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

if source_mode == "Microsoft Lists" and GRAPH_READY and st.session_state.auto_sync_lists:
    @st.fragment(run_every="5m")
    def _lists_auto_sync_fragment():
        try:
            sync_lists_now()
            stamp = st.session_state.last_sync.strftime("%H:%M:%S") if st.session_state.last_sync else "-"
            st.caption(f"🔄 Sincronização automática ativa • última leitura {stamp}")
        except Exception as exc:
            st.caption(f"⚠️ Falha na sincronização automática: {exc}")
    _lists_auto_sync_fragment()

if not source_ready:
    if PAGE != "🏠 Início":
        st.warning("Comece pela página **Início** e carregue a BASE LIST e a planilha PROJETISTAS.")
    else:
        if source_mode == "Excel - validação":
            st.info("Assim que os dois arquivos forem carregados, a análise e os botões de distribuição serão liberados.")
        elif source_mode == "Microsoft Lists":
            st.info("Carregue PROJETISTAS.xlsx e sincronize o Microsoft Lists para continuar.")
    st.stop()


def sync_experience_profiles() -> None:
    designer_names = [str(v).strip() for v in designers_df.get("name", pd.Series(dtype=str)).tolist() if str(v).strip()]
    raw_types = projects.get("project_type", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    type_display_by_norm: dict[str, str] = {}
    for value in raw_types.tolist():
        norm = normalize_text(value)
        if norm and norm not in type_display_by_norm:
            type_display_by_norm[norm] = value
    project_types = sorted(type_display_by_norm.values(), key=normalize_text)
    signature_raw = "|".join(sorted(designer_names)) + "||" + "|".join(project_types)
    signature = hashlib.sha256(signature_raw.encode()).hexdigest()
    if signature == st.session_state.experience_profile_source_signature:
        return

    previous_designers = {}
    if isinstance(st.session_state.designer_experience_profile, pd.DataFrame) and not st.session_state.designer_experience_profile.empty:
        previous_designers = {
            normalize_person_name(r["Projetista"]): normalize_experience_label(r["Experiência"])
            for _, r in st.session_state.designer_experience_profile.iterrows()
        }
    input_experience = {}
    if "experience" in designers_df.columns:
        input_experience = {
            normalize_person_name(r["name"]): normalize_experience_label(r.get("experience"))
            for _, r in designers_df.iterrows()
        }
    designer_rows = []
    for name in designer_names:
        norm = normalize_person_name(name)
        exp = previous_designers.get(norm, input_experience.get(norm, "Intermediário"))
        designer_rows.append({"Projetista": name, "Experiência": normalize_experience_label(exp)})
    st.session_state.designer_experience_profile = pd.DataFrame(designer_rows)

    previous_types = {}
    if isinstance(st.session_state.project_difficulty_profile, pd.DataFrame) and not st.session_state.project_difficulty_profile.empty:
        previous_types = {
            normalize_text(r[PROJECT_TYPE_LABEL]): normalize_difficulty_label(r["Dificuldade"])
            for _, r in st.session_state.project_difficulty_profile.iterrows()
        }
    type_rows = [
        {PROJECT_TYPE_LABEL: value, "Dificuldade": previous_types.get(normalize_text(value), "Médio")}
        for value in project_types
    ]
    st.session_state.project_difficulty_profile = pd.DataFrame(type_rows)
    st.session_state.experience_profile_source_signature = signature


def designer_experience_map() -> dict[str, str]:
    df = st.session_state.designer_experience_profile
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    return {str(r["Projetista"]): normalize_experience_label(r["Experiência"]) for _, r in df.iterrows()}


def project_difficulty_map() -> dict[str, str]:
    df = st.session_state.project_difficulty_profile
    if not isinstance(df, pd.DataFrame) or df.empty:
        return {}
    return {str(r[PROJECT_TYPE_LABEL]): normalize_difficulty_label(r["Dificuldade"]) for _, r in df.iterrows()}


def difficulty_for_project_type(value: object) -> str:
    mapping = {normalize_text(k): v for k, v in project_difficulty_map().items()}
    return mapping.get(normalize_text(value), "Médio")


def experience_profiles_hash() -> str:
    d = st.session_state.designer_experience_profile
    p = st.session_state.project_difficulty_profile
    d_text = d.to_csv(index=False) if isinstance(d, pd.DataFrame) else ""
    p_text = p.to_csv(index=False) if isinstance(p, pd.DataFrame) else ""
    raw = f"{EXPERIENCE_ENABLED}|{EXPERIENCE_MODE}|{d_text}|{p_text}"
    return hashlib.sha256(raw.encode()).hexdigest()


sync_experience_profiles()


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
balance = portfolio_balance_metrics(baseline, TARGETS.target_posts, TARGETS.target_projects)

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


def current_simulation_signature() -> str:
    raw = "|".join([
        st.session_state.base_excel_signature or source_mode,
        st.session_state.designers_signature or str(len(DESIGNERS)),
        str(TARGETS.target_posts), str(TARGETS.target_projects),
        str(MAX_PORTFOLIO_POSTS), str(MAX_PORTFOLIO_PROJECTS), str(PRIORITY_ENABLED),
        experience_profiles_hash(),
    ])
    return hashlib.sha256(raw.encode()).hexdigest()


def compute_distribution():
    return suggest_assignments(
        projects, live_snapshot, TARGETS, STATUS,
        max_new_projects_per_designer=MAX_PORTFOLIO_PROJECTS,
        max_portfolio_posts=MAX_PORTFOLIO_POSTS,
        max_portfolio_projects=MAX_PORTFOLIO_PROJECTS,
        priority_enabled=PRIORITY_ENABLED,
        respect_time=False,
        experience_enabled=EXPERIENCE_ENABLED,
        designer_experience=designer_experience_map(),
        project_difficulty=project_difficulty_map(),
        experience_mode=EXPERIENCE_MODE,
    )


def recalculate_manual_simulation(df: pd.DataFrame) -> pd.DataFrame:
    """Recalculate before/after load when the coordinator changes a simulated assignee."""
    if df.empty:
        return df.copy()
    result = df.copy().reset_index(drop=True)
    base_posts = baseline.set_index("Projetista")["PLN já atribuído"].to_dict()
    base_projects = baseline.set_index("Projetista")["Projetos já atribuídos"].to_dict()
    original_map = {}
    if not st.session_state.simulated_suggestions.empty:
        original_map = st.session_state.simulated_suggestions.set_index("item_id")["Projetista"].to_dict()
    running_posts = {name: int(base_posts.get(name, 0)) for name in DESIGNERS}
    running_projects = {name: int(base_projects.get(name, 0)) for name in DESIGNERS}
    for idx, row in result.iterrows():
        designer = str(row.get("Projetista", ""))
        posts = int(pd.to_numeric(pd.Series([row.get(POSTS_LABEL, row.get("PLN", 0))]), errors="coerce").fillna(0).iloc[0])
        before_posts = running_posts.get(designer, 0)
        before_projects = running_projects.get(designer, 0)
        after_posts = before_posts + posts
        after_projects = before_projects + 1
        result.at[idx, "Carga antes (postes)"] = before_posts
        result.at[idx, "Carga antes (projetos)"] = before_projects
        result.at[idx, "Carga depois (postes)"] = after_posts
        result.at[idx, "Carga depois (projetos)"] = after_projects
        if EXPERIENCE_ENABLED:
            exp_map = designer_experience_map()
            result.at[idx, "Experiência projetista"] = exp_map.get(designer, "Intermediário")
            project_type = str(row.get(PROJECT_TYPE_LABEL, "") or "").strip()
            result.at[idx, "Dificuldade"] = difficulty_for_project_type(project_type)
        if original_map.get(str(row.get("item_id", ""))) != designer:
            result.at[idx, "Motivo"] = "Ajuste manual do coordenador após a simulação automática"
        running_posts[designer] = after_posts
        running_projects[designer] = after_projects
    return result


def validate_manual_simulation(df: pd.DataFrame) -> list[str]:
    errors: list[str] = []
    if df.empty:
        return errors
    if df["item_id"].astype(str).duplicated().any():
        errors.append("A mesma obra aparece mais de uma vez na simulação.")
    if (df["Projetista"].astype(str).str.strip() == "").any():
        errors.append("Existe atribuição sem projetista.")
    invalid = sorted(set(df["Projetista"].astype(str)) - set(DESIGNERS))
    if invalid:
        errors.append("Projetistas fora da lista oficial: " + ", ".join(invalid))
    # Recalculate portfolio caps after manual edits.
    base_posts = baseline.set_index("Projetista")["PLN já atribuído"].to_dict()
    base_projects = baseline.set_index("Projetista")["Projetos já atribuídos"].to_dict()
    for designer, group in df.groupby("Projetista"):
        posts_col = POSTS_LABEL if POSTS_LABEL in group.columns else "PLN"
        total_posts = int(base_posts.get(designer, 0)) + int(pd.to_numeric(group[posts_col], errors="coerce").fillna(0).sum())
        total_projects = int(base_projects.get(designer, 0)) + len(group)
        if total_posts > MAX_PORTFOLIO_POSTS or total_projects > MAX_PORTFOLIO_PROJECTS:
            errors.append(
                f"{designer}: a edição ultrapassa o teto de {MAX_PORTFOLIO_POSTS} postes / {MAX_PORTFOLIO_PROJECTS} projetos."
            )

    if EXPERIENCE_ENABLED and str(EXPERIENCE_MODE).casefold() == "estrito":
        exp_map = designer_experience_map()
        for _, row in df.iterrows():
            designer = str(row.get("Projetista", ""))
            project_type = str(row.get(PROJECT_TYPE_LABEL, "") or "").strip()
            experience = exp_map.get(designer, "Intermediário")
            difficulty = difficulty_for_project_type(project_type)
            if match_penalty(experience, difficulty, "Estrito") is None:
                errors.append(
                    f"{designer}: o PI '{project_type or 'sem tipo'}' está classificado como {difficulty} e excede o nível {experience}."
                )
    return errors


def run_simulation():
    suggestions, summary = compute_distribution()
    cycle_id = f"SIM-{NOW.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}"
    audit = AuditStore("data/automation_audit.sqlite3")
    audit.start_cycle(cycle_id, NOW, source_mode, "simulation", len(projects), len(DESIGNERS))
    for _, row in suggestions.iterrows():
        audit.log_assignment(cycle_id, NOW, row.to_dict(), "suggest", "success")
    audit.finish_cycle(cycle_id, NOW, "success", len(suggestions), 0, "Simulação gerada no Streamlit")
    st.session_state.simulated_suggestions = suggestions
    st.session_state.simulated_summary = summary
    st.session_state.simulation_signature = current_simulation_signature()
    st.session_state.simulation_cycle_id = cycle_id
    reset_generated_output()


def generate_distribution_file(suggestions: pd.DataFrame | None = None):
    try:
        suggestions = suggestions.copy() if suggestions is not None else st.session_state.simulated_suggestions.copy()
        if suggestions.empty:
            st.info("A simulação não possui novas obras para distribuir.")
            return
        errors = validate_manual_simulation(suggestions)
        if errors:
            for error in errors:
                st.error(error)
            return
        if source_mode != "Excel - validação":
            st.session_state.generated_distribution_suggestions = suggestions
            st.session_state.generated_distribution_summary = st.session_state.simulated_summary.copy()
            return
        generated_at = datetime.now(ZoneInfo(TIMEZONE))
        output_bytes = generate_distributed_excel_bytes(
            st.session_state.base_excel_bytes,
            suggestions,
            distribution_summary=st.session_state.simulated_summary,
            target_posts=TARGETS.target_posts,
            target_projects=TARGETS.target_projects,
            generated_at=generated_at,
        )
        stem = (st.session_state.base_excel_name or "BASE_LIST.xlsx").rsplit(".", 1)[0]
        st.session_state.generated_excel_bytes = output_bytes
        st.session_state.generated_excel_name = f"{stem}_DISTRIBUIDA_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
        st.session_state.generated_distribution_suggestions = suggestions
        st.session_state.generated_distribution_summary = st.session_state.simulated_summary.copy()

        cycle_id = f"EXP-{generated_at.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}"
        audit = AuditStore("data/automation_audit.sqlite3")
        audit.start_cycle(cycle_id, generated_at, source_mode, "export", len(projects), len(DESIGNERS))
        for _, row in suggestions.iterrows():
            audit.log_assignment(cycle_id, generated_at, row.to_dict(), "export", "success")
        audit.finish_cycle(cycle_id, generated_at, "success", len(suggestions), len(suggestions), "Planilha distribuída gerada")

        if WEBHOOK_URL and st.session_state.notify_after_distribution:
            try:
                send_distribution_webhook(
                    WEBHOOK_URL,
                    "NIP Smart - nova distribuição",
                    f"{len(suggestions)} obra(s) distribuídas em {generated_at.strftime('%d/%m/%Y %H:%M')}.",
                )
            except Exception as exc:
                st.warning(f"A planilha foi gerada, mas a notificação não foi enviada: {exc}")
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
                "⬇️ BAIXAR BASE LIST DISTRIBUÍDA",
                data=st.session_state.generated_excel_bytes,
                file_name=st.session_state.generated_excel_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
        right.metric("Novas atribuições", len(suggestions))
    elif source_mode == "Microsoft Lists" and not suggestions.empty:
        st.success(f"Prévia gerada com {len(suggestions)} nova(s) atribuição(ões).")


# Invalidate stale simulation if files/settings changed.
if st.session_state.simulation_signature and st.session_state.simulation_signature != current_simulation_signature():
    reset_simulation()


# -----------------------------------------------------------------------------
# PAGE: HOME
# -----------------------------------------------------------------------------
if PAGE == "🏠 Início":
    st.markdown('<div class="section-title">O fluxo é simples</div>', unsafe_allow_html=True)
    s1, s2, s3 = st.columns(3)
    with s1:
        st.markdown('<div class="step-card"><span class="num">1</span><b>Carregar</b><p>A ferramenta lê a carteira existente e valida os dados.</p></div>', unsafe_allow_html=True)
    with s2:
        st.markdown('<div class="step-card"><span class="num">2</span><b>Simular</b><p>Confira quem receberá cada obra antes de alterar qualquer planilha.</p></div>', unsafe_allow_html=True)
    with s3:
        st.markdown('<div class="step-card"><span class="num">3</span><b>Gerar e baixar</b><p>Somente após a conferência é criada uma nova BASE LIST distribuída.</p></div>', unsafe_allow_html=True)

    st.write("")
    st.markdown('<div class="section-title">Situação atual da equipe</div>', unsafe_allow_html=True)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Projetistas", len(DESIGNERS))
    k2.metric("Sem obras", without_load)
    k3.metric("Carga parcial", partial_load)
    k4.metric("Carteira completa", covered_load)
    k5.metric("Obras prontas", len(eligible_available))
    k6.metric("Equilíbrio", f'{balance["score"]:.0f}%')
    st.caption(
        f"Meta: **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos** • "
        f"Teto de segurança: **{MAX_PORTFOLIO_POSTS} postes / {MAX_PORTFOLIO_PROJECTS} projetos**."
    )

    if quality["disponiveis_sem_pln"] or quality["disponiveis_sem_sgo"] or quality.get("sgo_duplicado", 0):
        st.warning("Há pendências de dados na BASE LIST. A ferramenta bloqueia automaticamente obras sem SGO ou Postes Alterados/Novos da distribuição.")

    st.markdown('<div class="section-title">Passo 2 — Simule antes de distribuir</div>', unsafe_allow_html=True)
    if EXPERIENCE_ENABLED:
        st.info(f"Critério por experiência está ativo no modo **{EXPERIENCE_MODE}**. Antes da simulação, confira os níveis e as dificuldades na página **Distribuir obras**.")
    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Obras disponíveis", len(eligible_available))
    a2.metric("Postes disponíveis", available_posts)
    a3.metric("Bloqueadas por dados", quality["disponiveis_sem_pln"] + quality["disponiveis_sem_sgo"])
    a4.metric("Projetistas sem carga", without_load)

    if not CAN_EDIT:
        st.info("Você está no perfil Consulta. Simulação e geração de planilha ficam disponíveis apenas para Administrador.")
    else:
        if st.button("🔎 SIMULAR DISTRIBUIÇÃO", use_container_width=True, disabled=len(eligible_available) == 0):
            run_simulation()
            st.rerun()

    if not st.session_state.simulated_suggestions.empty:
        st.success(f"Simulação pronta: {len(st.session_state.simulated_suggestions)} nova(s) atribuição(ões). Confira na página **Distribuir obras**.")
        b1, b2 = st.columns(2)
        with b1:
            if source_mode == "Excel - validação" and CAN_EDIT:
                if st.button("✅ GERAR PLANILHA COM A SIMULAÇÃO", type="primary", use_container_width=True):
                    generate_distribution_file()
            else:
                st.caption("A aplicação definitiva é feita na página Distribuir obras.")
        with b2:
            if st.button("➡️ CONFERIR DISTRIBUIÇÃO DETALHADA", use_container_width=True):
                st.session_state.nav_page = "⚡ Distribuir obras"
                st.rerun()
        render_download_result()

    st.markdown('<div class="section-title">Carteira por projetista</div>', unsafe_allow_html=True)
    load_view = compact_load_table(baseline, TARGETS.target_posts, TARGETS.target_projects)
    st.dataframe(load_view, use_container_width=True, hide_index=True, column_config=compact_load_config(), height=min(620, 78 + 35 * len(load_view)))

    left, right = st.columns([1.45, 1])
    with left:
        chart = baseline[["Projetista", "PLN já atribuído", "Projetos já atribuídos"]].copy().rename(columns={"PLN já atribuído": POSTS_LABEL}).sort_values(POSTS_LABEL)
        fig = px.bar(chart, y="Projetista", x=POSTS_LABEL, orientation="h", hover_data=["Projetos já atribuídos"], title="Carga atual em postes por projetista")
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        fig.add_vline(x=MAX_PORTFOLIO_POSTS, line_dash="dot", annotation_text=f"Teto {MAX_PORTFOLIO_POSTS}")
        st.plotly_chart(style_figure(fig, max(380, 27 * len(chart))), use_container_width=True)
    with right:
        st.markdown('<div class="section-title">Leitura rápida</div>', unsafe_allow_html=True)
        insights = management_insights(live_snapshot, baseline, designer_pred, len(eligible_available), available_posts)
        render_insights(insights, max_items=5)


# -----------------------------------------------------------------------------
# PAGE: DISTRIBUTION
# -----------------------------------------------------------------------------
elif PAGE == "⚡ Distribuir obras":
    st.markdown('<div class="section-title">1 — Critério de experiência</div>', unsafe_allow_html=True)
    st.caption("Opcional: use a coluna F — PI (Tipo Projeto) para direcionar projetos simples aos menos experientes e projetos mais difíceis aos mais experientes.")

    if CAN_EDIT:
        experience_toggle = st.toggle(
            "Usar experiência do projetista na distribuição",
            value=EXPERIENCE_ENABLED,
            key="experience_toggle_page_v13",
        )
        if bool(experience_toggle) != bool(st.session_state.cfg_experience_enabled):
            st.session_state.cfg_experience_enabled = bool(experience_toggle)
            reset_simulation()
            st.rerun()
    else:
        st.info("Critério por experiência: **ativo**" if EXPERIENCE_ENABLED else "Critério por experiência: **desativado**")

    if EXPERIENCE_ENABLED:
        if CAN_EDIT:
            mode_idx = EXPERIENCE_MODES.index(EXPERIENCE_MODE) if EXPERIENCE_MODE in EXPERIENCE_MODES else 0
            selected_mode = st.radio(
                "Como aplicar a experiência?",
                EXPERIENCE_MODES,
                index=mode_idx,
                horizontal=True,
                help="Preferencial tenta casar o nível e usa outras opções apenas como fallback. Estrito nunca entrega projeto acima do nível do projetista.",
            )
            if selected_mode != st.session_state.cfg_experience_mode:
                st.session_state.cfg_experience_mode = selected_mode
                reset_simulation()
                st.rerun()

        profile_left, profile_right = st.columns(2)
        with profile_left:
            st.markdown("**Nível dos projetistas**")
            exp_current = st.session_state.designer_experience_profile.copy().reset_index(drop=True)
            if CAN_EDIT:
                exp_edited = st.data_editor(
                    exp_current,
                    use_container_width=True,
                    hide_index=True,
                    disabled=["Projetista"],
                    column_config={
                        "Projetista": st.column_config.TextColumn("Projetista", width="large"),
                        "Experiência": st.column_config.SelectboxColumn("Experiência", options=EXPERIENCE_LEVELS, required=True, width="medium"),
                    },
                    key="designer_experience_editor_v13",
                    height=min(520, 78 + 35 * max(1, len(exp_current))),
                )
                normalized_exp = exp_edited.copy()
                normalized_exp["Experiência"] = normalized_exp["Experiência"].map(normalize_experience_label)
                if not normalized_exp.astype(str).equals(exp_current.astype(str)):
                    st.session_state.designer_experience_profile = normalized_exp
                    reset_simulation()
                    st.rerun()
            else:
                st.dataframe(exp_current, use_container_width=True, hide_index=True)

        with profile_right:
            st.markdown("**Dificuldade por PI (Tipo Projeto)**")
            diff_current = st.session_state.project_difficulty_profile.copy().reset_index(drop=True)
            if diff_current.empty:
                st.warning("A BASE LIST não possui valores em PI (Tipo Projeto). O critério de experiência não poderá diferenciar as obras.")
            elif CAN_EDIT:
                diff_edited = st.data_editor(
                    diff_current,
                    use_container_width=True,
                    hide_index=True,
                    disabled=[PROJECT_TYPE_LABEL],
                    column_config={
                        PROJECT_TYPE_LABEL: st.column_config.TextColumn(PROJECT_TYPE_LABEL, width="large"),
                        "Dificuldade": st.column_config.SelectboxColumn("Dificuldade", options=DIFFICULTY_LEVELS, required=True, width="medium"),
                    },
                    key="project_difficulty_editor_v13",
                    height=min(520, 78 + 35 * max(1, len(diff_current))),
                )
                normalized_diff = diff_edited.copy()
                normalized_diff["Dificuldade"] = normalized_diff["Dificuldade"].map(normalize_difficulty_label)
                if not normalized_diff.astype(str).equals(diff_current.astype(str)):
                    st.session_state.project_difficulty_profile = normalized_diff
                    reset_simulation()
                    st.rerun()
            else:
                st.dataframe(diff_current, use_container_width=True, hide_index=True)

        e1, e2, e3, e4 = st.columns(4)
        exp_counts = st.session_state.designer_experience_profile["Experiência"].value_counts() if not st.session_state.designer_experience_profile.empty else pd.Series(dtype=int)
        diff_counts = st.session_state.project_difficulty_profile["Dificuldade"].value_counts() if not st.session_state.project_difficulty_profile.empty else pd.Series(dtype=int)
        e1.metric("Menos experientes", int(exp_counts.get("Menos experiente", 0)))
        e2.metric("Experientes", int(exp_counts.get("Experiente", 0)))
        e3.metric("PI fáceis", int(diff_counts.get("Fácil", 0)))
        e4.metric("PI difíceis", int(diff_counts.get("Difícil", 0)))
        st.caption("Encaixe preferido: **Menos experiente ↔ Fácil** • **Intermediário ↔ Médio** • **Experiente ↔ Difícil**.")
        if EXPERIENCE_MODE == "Estrito":
            st.warning("Modo Estrito: um projetista não receberá projeto classificado acima do seu nível de experiência.")
        else:
            st.info("Modo Preferencial: o sistema prioriza o melhor encaixe de experiência, mas pode usar outro nível como fallback se necessário.")

    st.markdown('<div class="section-title">2 — Fila disponível</div>', unsafe_allow_html=True)
    st.caption("Obras já atribuídas nunca são redistribuídas automaticamente.")
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Obras prontas", len(eligible_available))
    d2.metric("Postes disponíveis", available_posts)
    d3.metric("Sem obras", without_load)
    d4.metric("Equilíbrio atual", f'{balance["score"]:.0f}%')

    queue_cols = ["sgo", "project_type", "posts", "priority", "deadline", "regional", "municipality"]
    queue = eligible_available[queue_cols].copy().rename(columns={
        "sgo": "Nota SGO", "project_type": PROJECT_TYPE_LABEL, "posts": POSTS_LABEL,
        "priority": "Prioridade", "deadline": "Prazo", "regional": "Regional", "municipality": "Município"
    })
    if EXPERIENCE_ENABLED and not queue.empty:
        queue["Dificuldade"] = queue[PROJECT_TYPE_LABEL].map(difficulty_for_project_type)
    if not queue.empty:
        st.dataframe(queue.head(100), use_container_width=True, hide_index=True)

    st.markdown('<div class="section-title">3 — Simulação</div>', unsafe_allow_html=True)
    if CAN_EDIT and st.button("🔎 GERAR / ATUALIZAR SIMULAÇÃO", use_container_width=True, disabled=len(eligible_available) == 0):
        run_simulation()
        st.rerun()

    sim = st.session_state.simulated_suggestions.copy()
    if sim.empty:
        st.info("Ainda não há simulação. Clique em **Gerar / atualizar simulação** para ver quem receberá cada obra.")
    else:
        st.caption("Você pode retirar uma linha da distribuição ou trocar o projetista antes de gerar a planilha. O sistema valida o teto de carteira.")
        editor = sim.copy()
        editor.insert(0, "Incluir", True)
        editable_cols = ["Incluir", "Projetista", "Nota SGO", PROJECT_TYPE_LABEL]
        if EXPERIENCE_ENABLED:
            editable_cols += ["Dificuldade", "Experiência projetista"]
        editable_cols += [
            POSTS_LABEL, "Prioridade", "Prazo", "Regional", "Município",
            "Carga antes (postes)", "Carga depois (postes)", "Motivo", "item_id", "Nº da nota",
            "Carga antes (projetos)", "Carga depois (projetos)", "etag",
        ]
        editable_cols = [c for c in editable_cols if c in editor.columns]
        edited = st.data_editor(
            editor[editable_cols],
            use_container_width=True,
            hide_index=True,
            disabled=[c for c in editable_cols if c not in ["Incluir", "Projetista"]],
            column_config={
                "Incluir": st.column_config.CheckboxColumn("Incluir", default=True),
                "Projetista": st.column_config.SelectboxColumn("Projetista", options=DESIGNERS, required=True, width="large"),
                PROJECT_TYPE_LABEL: st.column_config.TextColumn(PROJECT_TYPE_LABEL, width="medium"),
                "Dificuldade": st.column_config.TextColumn("Dificuldade", width="small"),
                "Experiência projetista": st.column_config.TextColumn("Experiência", width="medium"),
                POSTS_LABEL: st.column_config.NumberColumn(POSTS_LABEL, width="medium"),
                "Motivo": st.column_config.TextColumn("Por que recebeu?", width="large"),
            },
            key="distribution_editor_v13",
        )
        final_sim = edited[edited["Incluir"]].drop(columns=["Incluir"], errors="ignore").copy()
        final_sim = recalculate_manual_simulation(final_sim)
        errors = validate_manual_simulation(final_sim)
        if errors:
            for error in errors:
                st.error(error)
        else:
            st.success(f"Simulação válida: {len(final_sim)} obra(s) pronta(s) para gerar.")
            if CAN_EDIT and st.button("💾 SALVAR AJUSTES DA SIMULAÇÃO", use_container_width=True):
                # Preserve any columns omitted by the editor by merging on item_id.
                original = st.session_state.simulated_suggestions.copy().set_index("item_id")
                edited_idx = final_sim.copy().set_index("item_id")
                for col in edited_idx.columns:
                    original.loc[edited_idx.index, col] = edited_idx[col]
                st.session_state.simulated_suggestions = original.loc[edited_idx.index].reset_index()
                st.success("Ajustes salvos.")

            st.markdown('<div class="section-title">4 — Gerar resultado</div>', unsafe_allow_html=True)
            if CAN_EDIT and source_mode == "Excel - validação":
                if st.button("✅ GERAR NOVA BASE LIST DISTRIBUÍDA", type="primary", use_container_width=True):
                    st.session_state.simulated_suggestions = final_sim.copy()
                    generate_distribution_file(final_sim)
                render_download_result()
            elif source_mode == "Microsoft Lists" and CAN_EDIT:
                if not WRITE_ENABLED:
                    st.warning("A gravação no Microsoft Lists está bloqueada. A simulação é somente leitura.")
                else:
                    confirm = st.checkbox("Confirmo que quero gravar estas atribuições no Microsoft Lists")
                    if st.button("✅ APLICAR NO MICROSOFT LISTS", type="primary", use_container_width=True, disabled=not confirm):
                        try:
                            repo = make_repository()
                            lookup_by_name = {normalize_person_name(r["name"]): r.get("sharepoint_lookup_id") for _, r in designers_df.iterrows()}
                            for _, row in final_sim.iterrows():
                                etag = None if pd.isna(row.get("etag")) else row.get("etag")
                                lookup_id = lookup_by_name.get(normalize_person_name(row["Projetista"]))
                                repo.assign_project(str(row["item_id"]), str(row["Projetista"]), etag, lookup_id)
                            sync_lists_now()
                            st.success(f"{len(final_sim)} projeto(s) atribuídos no Microsoft Lists.")
                            reset_simulation()
                            st.rerun()
                        except GraphError as exc:
                            st.error(str(exc))
                        except Exception as exc:
                            st.error(f"Falha ao aplicar: {exc}")

    if not st.session_state.simulated_summary.empty:
        st.markdown("#### Como fica a carga após a simulação")
        summary = st.session_state.simulated_summary.copy()
        wanted = ["Projetista", "Experiência", "Potencial postes após distribuição", "Potencial projetos após distribuição", "Novos projetos sugeridos", "Novos postes sugeridos", "Motivo"]
        wanted = [c for c in wanted if c in summary.columns]
        st.dataframe(summary[wanted], use_container_width=True, hide_index=True)
        plot = summary.sort_values("Potencial postes após distribuição")
        fig = px.bar(plot, y="Projetista", x="Potencial postes após distribuição", orientation="h", title="Carga em postes depois da simulação")
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        fig.add_vline(x=MAX_PORTFOLIO_POSTS, line_dash="dot", annotation_text=f"Teto {MAX_PORTFOLIO_POSTS}")
        st.plotly_chart(style_figure(fig, max(400, 26 * len(plot))), use_container_width=True)

    with st.expander("Como a ferramenta decide quem recebe primeiro?"):
        st.markdown(
            f"""
            - Prioriza quem está com **menor cobertura** da meta de **{TARGETS.target_posts} postes / {TARGETS.target_projects} projetos**.
            - Distribui em rodadas para evitar concentração.
            - Se habilitado, usa **Prioridade e Prazo** para ordenar a fila.
            - Nunca move automaticamente uma obra já atribuída.
            - Bloqueia obra sem Nota SGO ou Postes Alterados/Novos válido.
            - Não ultrapassa o teto de **{MAX_PORTFOLIO_POSTS} postes / {MAX_PORTFOLIO_PROJECTS} projetos**.
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
    st.caption("Produção = projetos com Data de entrega do projeto na data analisada. Postes usa Qtd. de poste final; Postes Alterados/Novos é o fallback.")

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
        st.caption(f"Jornada: **{current_work_status(NOW, TIMEZONE)}** • Tempo útil restante: **{format_minutes(productive_minutes_remaining(NOW, TIMEZONE))}**")

    day_tab, individual_tab, period_tab, predict_tab, close_tab = st.tabs([
        "📍 Dia", "👤 Histórico individual", "📅 Semana e mês", "📈 Projeção", "✅ Fechamento diário"
    ])

    with day_tab:
        st.markdown("#### Quem precisa de atenção")
        if designer_attention.empty:
            st.success("Nenhum projetista está sinalizado para atenção nesta data.")
        else:
            attention_view = designer_attention.copy()
            attention_config = compact_daily_config(is_current_day)
            if not is_current_day:
                attention_view = attention_view.drop(columns=["Carteira atual"], errors="ignore")
                attention_config.pop("Carteira atual", None)
            st.dataframe(attention_view, use_container_width=True, hide_index=True, column_config=attention_config, height=min(520, 78 + 35 * len(attention_view)))

        st.markdown("#### Resultado de toda a equipe")
        daily_view = compact_daily_table(analysis_snapshot, TARGETS.target_posts, TARGETS.target_projects)
        daily_config = compact_daily_config(is_current_day)
        if not is_current_day:
            daily_view = daily_view.drop(columns=["Carteira atual"], errors="ignore")
            daily_config.pop("Carteira atual", None)
        st.dataframe(daily_view, use_container_width=True, hide_index=True, column_config=daily_config, height=min(650, 78 + 35 * len(daily_view)))

        plot = analysis_snapshot[["Projetista", "Postes realizados"]].copy().sort_values("Postes realizados")
        fig = px.bar(plot, y="Projetista", x="Postes realizados", orientation="h", title="Postes entregues por projetista")
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        fig.add_vline(x=TARGETS.min_posts, line_dash="dot", annotation_text=f"Mínimo {TARGETS.min_posts}")
        st.plotly_chart(style_figure(fig, max(390, 27 * len(plot))), use_container_width=True)

    with individual_tab:
        selected_designer = st.selectbox("Projetista", DESIGNERS, key="designer_history_v13")
        history = designer_daily_history(projects, selected_designer, analysis_date, TARGETS, TIMEZONE, days=20)
        h1, h2, h3 = st.columns(3)
        h1.metric("Postes nos últimos 20 dias úteis", int(history["Postes"].sum()))
        h2.metric("Projetos nos últimos 20 dias úteis", int(history["Projetos"].sum()))
        consistency = float((history["Situação"] == "Meta cheia").mean() * 100) if not history.empty else 0
        h3.metric("Consistência da meta cheia", f"{consistency:.0f}%")
        fig = px.line(history, x="Data", y="Postes", markers=True, title=f"Histórico de postes — {selected_designer}")
        fig.add_hline(y=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        fig.add_hline(y=TARGETS.min_posts, line_dash="dot", annotation_text=f"Mínimo {TARGETS.min_posts}")
        st.plotly_chart(style_figure(fig, 390), use_container_width=True)
        st.dataframe(history, use_container_width=True, hide_index=True)

        month_start = analysis_date.replace(day=1)
        quality_proxy = designer_quality_proxy(projects, [selected_designer], month_start, analysis_date, TIMEZONE)
        if not quality_proxy.empty and int(quality_proxy.iloc[0]["Projetos entregues"]) > 0:
            st.markdown("#### Sinal de qualidade disponível na base")
            st.caption("'Reanálise registrada' é um indicador de processo, não uma classificação de erro do projetista.")
            st.dataframe(quality_proxy, use_container_width=True, hide_index=True)

    with period_tab:
        left, right = st.columns(2)
        with left:
            st.markdown("#### Semana")
            cols = [c for c in ["Projetista", "Postes", "Projetos", "Dias meta cheia", "Consistência meta cheia %"] if c in week.columns]
            st.dataframe(week[cols], use_container_width=True, hide_index=True)
            if not week.empty:
                fig = px.bar(week, x="Projetista", y="Postes", title="Postes entregues na semana")
                st.plotly_chart(style_figure(fig, 380), use_container_width=True)
        with right:
            st.markdown("#### Mês")
            cols = [c for c in ["Projetista", "Postes", "Projetos", "Dias meta cheia", "Consistência meta cheia %"] if c in month.columns]
            st.dataframe(month[cols], use_container_width=True, hide_index=True)
            if not month.empty:
                fig = px.bar(month, x="Projetista", y="Postes", title="Postes entregues no mês")
                st.plotly_chart(style_figure(fig, 380), use_container_width=True)
        st.info("A referência semanal e mensal é apenas acompanhamento. A meta operacional é diária e não cumulativa.")

    with predict_tab:
        st.markdown("#### Tendência de fechamento do mês")
        st.caption("A projeção usa produção acumulada e ritmo médio dos últimos 5 dias úteis.")
        if designer_pred.empty:
            st.info("Ainda não há dados suficientes para projeção.")
        else:
            simple_cols = [c for c in ["Projetista", "Postes mês", "Projetos mês", "Projeção postes mês", "Projeção projetos mês", "Consistência meta cheia %", "Tendência"] if c in designer_pred.columns]
            st.dataframe(designer_pred[simple_cols], use_container_width=True, hide_index=True)
            trend_counts = designer_pred["Tendência"].value_counts().rename_axis("Tendência").reset_index(name="Projetistas")
            fig = px.pie(trend_counts, names="Tendência", values="Projetistas", hole=.58, title="Situação projetada do mês")
            st.plotly_chart(style_figure(fig, 390), use_container_width=True)
            need = designer_pred[designer_pred["Tendência"] == "Requer acompanhamento"]
            st.markdown("#### Projetistas que merecem acompanhamento")
            if need.empty:
                st.success("Nenhum projetista está projetado abaixo da faixa de acompanhamento.")
            else:
                st.dataframe(need[simple_cols], use_container_width=True, hide_index=True)

    with close_tab:
        close = daily_close_summary(analysis_snapshot, TARGETS)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Meta cheia", close["full"])
        c2.metric("Faixa mínima", close["minimum"])
        c3.metric("Abaixo da meta", close["below"])
        c4.metric("Problemas de carga/dados", close["lack_load"] + close["data_issue"])
        close_table = compact_daily_table(analysis_snapshot, TARGETS.target_posts, TARGETS.target_projects)
        st.dataframe(close_table, use_container_width=True, hide_index=True, column_config=compact_daily_config(is_current_day))
        close_bytes = generate_daily_close_excel(analysis_snapshot, analysis_date, TARGETS.target_posts, TARGETS.target_projects)
        st.download_button(
            "⬇️ BAIXAR FECHAMENTO DIÁRIO",
            data=close_bytes,
            file_name=f"FECHAMENTO_PROJETISTAS_{analysis_date.strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )


# -----------------------------------------------------------------------------
# PAGE: DATA + RULES
# -----------------------------------------------------------------------------
elif PAGE == "🔎 Dados e regras":
    st.markdown('<div class="section-title">Qualidade da BASE LIST</div>', unsafe_allow_html=True)
    q1, q2, q3, q4, q5, q6 = st.columns(6)
    q1.metric("Em projeto", quality["em_projeto"])
    q2.metric("Disponíveis", quality["disponiveis"])
    q3.metric("Já atribuídas", quality["atribuidos"])
    q4.metric("Sem Postes Alt./Novos", quality["disponiveis_sem_pln"])
    q5.metric("Sem SGO", quality["disponiveis_sem_sgo"])
    q6.metric("SGO duplicado", quality.get("sgo_duplicado", 0))

    if quality["disponiveis_sem_pln"] or quality["disponiveis_sem_sgo"] or quality.get("sgo_duplicado", 0) or quality.get("nota_duplicada", 0):
        st.warning("Existem inconsistências que merecem revisão. Obras sem Postes Alterados/Novos ou SGO ficam bloqueadas para distribuição automática.")

    with st.expander("Obras bloqueadas para distribuição", expanded=True):
        blocked = prepared[
            prepared["status_norm"].isin(STATUS.project_pool_set)
            & (prepared["assignee_norm"] == "")
            & (~prepared["posts_valid"] | ~prepared["sgo_present"])
        ][["note", "sgo", "posts", "regional", "municipality"]].rename(columns={
            "note": "Nº da nota", "sgo": "Nota SGO", "posts": POSTS_LABEL, "regional": "Regional", "municipality": "Município"
        })
        if blocked.empty:
            st.success("Nenhuma obra disponível está bloqueada por falta de SGO ou Postes Alterados/Novos.")
        else:
            st.dataframe(blocked, use_container_width=True, hide_index=True)

    if unlisted_names:
        with st.expander("Projetistas atribuídos que não estão na planilha PROJETISTAS"):
            st.write(unlisted_names)

    with st.expander("Indicador de equilíbrio da carteira", expanded=True):
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Equilíbrio", f'{balance["score"]:.0f}%')
        b2.metric("Cobertura média", f'{balance["avg_coverage"]:.0f}%')
        b3.metric("Carga média", f'{balance["avg_posts"]:.1f} postes')
        b4.metric("Diferença maior-menor", f'{balance["spread_posts"]:.0f} postes')
        st.caption("Equilíbrio mede a dispersão entre as carteiras. Cobertura média mostra o quanto da meta está efetivamente abastecido.")

    with st.expander("Regras e parâmetros", expanded=True):
        st.markdown(
            f"""
            **Meta diária**: {TARGETS.target_posts} postes / {TARGETS.target_projects} projetos.  
            **Faixa mínima**: {TARGETS.min_posts} postes / {TARGETS.min_projects} projetos.  
            **Teto de carteira**: {MAX_PORTFOLIO_POSTS} postes / {MAX_PORTFOLIO_PROJECTS} projetos.  
            **Meta não cumulativa**: excedente de um dia não reduz a meta do dia seguinte.  
            **Carteira**: Status = Em projeto + Projetistas preenchido; peso = Postes Alterados/Novos (coluna R).  
            **Elegível para distribuição**: Em projeto + Projetistas vazio + Nota SGO + Postes Alterados/Novos válido.  
            **Produção**: Data de entrega do projeto; Qtd. de poste final, com Postes Alterados/Novos como fallback.  
            **Critério por experiência**: {"Ativo — " + EXPERIENCE_MODE if EXPERIENCE_ENABLED else "Desativado"}. Quando ativo, usa PI (Tipo Projeto) da coluna F.  
            **Jornada**: 08:00–12:00 e 13:12–18:00 ({TOTAL_WORK_MINUTES} minutos produtivos).
            """
        )

    with st.expander("Auditoria de distribuição"):
        audit = AuditStore("data/automation_audit.sqlite3")
        recent = audit.recent_cycles(30)
        assignments = audit.recent_assignments(100)
        if recent.empty:
            st.info("Ainda não há ciclos registrados nesta sessão/ambiente.")
        else:
            st.markdown("**Ciclos recentes**")
            st.dataframe(recent, use_container_width=True, hide_index=True)
        if not assignments.empty:
            st.markdown("**Decisões registradas**")
            st.dataframe(assignments, use_container_width=True, hide_index=True)

    with st.expander("Consultar a BASE LIST carregada"):
        show = prepared.copy()
        show["Disponibilidade"] = ""
        pool_mask = show["status_norm"].isin(STATUS.project_pool_set)
        show.loc[pool_mask & (show["assignee_norm"] == ""), "Disponibilidade"] = "Disponível"
        show.loc[pool_mask & (show["assignee_norm"] != ""), "Disponibilidade"] = "Atribuído"
        display = show[["note", "sgo", "status", "project_type", "posts", "assignee", "regional", "municipality", "deadline", "Disponibilidade"]].rename(columns={
            "note": "Nº da nota", "sgo": "Nota SGO", "status": "Status", "project_type": PROJECT_TYPE_LABEL, "posts": POSTS_LABEL,
            "assignee": "Projetista", "regional": "Regional", "municipality": "Município", "deadline": "Prazo",
        })
        st.dataframe(display, use_container_width=True, hide_index=True)

    with st.expander("Microsoft Lists e notificações"):
        st.write("Integração Microsoft Lists:", "**Configurada**" if GRAPH_READY else "**Aguardando Secrets**")
        st.write("Escrita no Microsoft Lists:", "**Liberada**" if WRITE_ENABLED else "**Bloqueada**")
        st.write("Webhook de notificação:", "**Configurado**" if WEBHOOK_URL else "**Não configurado**")
        if source_mode == "Microsoft Lists" and not st.session_state.column_diagnostics.empty:
            st.dataframe(st.session_state.column_diagnostics, use_container_width=True, hide_index=True)
        st.caption("A atualização automática de 5 minutos pode ser ativada na barra lateral quando a fonte for Microsoft Lists.")

    with st.expander("Automação avançada por ciclos"):
        policy = AutomationPolicy(
            timezone=TIMEZONE,
            require_work_hours=True,
            max_portfolio_posts=MAX_PORTFOLIO_POSTS,
            max_portfolio_projects=MAX_PORTFOLIO_PROJECTS,
            priority_enabled=PRIORITY_ENABLED,
            experience_enabled=EXPERIENCE_ENABLED,
            experience_mode=EXPERIENCE_MODE,
            designer_experience=designer_experience_map(),
            project_difficulty=project_difficulty_map(),
        )
        audit = AuditStore("data/automation_audit.sqlite3")
        engine = AutomationEngine(TARGETS, STATUS, policy=policy, audit=audit)
        if CAN_EDIT and st.button("Executar ciclo de simulação agora", use_container_width=True):
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
                st.dataframe(result.suggestions.drop(columns=["etag", "PLN"], errors="ignore"), use_container_width=True, hide_index=True)
