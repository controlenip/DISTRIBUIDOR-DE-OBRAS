from __future__ import annotations

from datetime import datetime
import hashlib
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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

st.set_page_config(
    page_title="NIP Smart Distribuição",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- Visual system ----------
st.markdown(
    """
    <style>
    :root { --nip-blue:#123B68; --nip-blue2:#1F5D96; --nip-cyan:#2D8FC7; --nip-soft:#F3F6FA; }
    .block-container {padding-top: 1.25rem; padding-bottom: 2.5rem; max-width: 1550px;}
    [data-testid="stSidebar"] {background: linear-gradient(180deg,#0E2C4D 0%,#123B68 100%);}
    [data-testid="stSidebar"] * {color:#F4F8FC;}
    [data-testid="stSidebar"] [data-baseweb="radio"] label {background:rgba(255,255,255,.04); border-radius:8px; padding:5px 8px;}
    .hero {
        padding: 22px 26px; border-radius: 18px;
        background: linear-gradient(120deg,#0E2C4D 0%,#14507E 62%,#2381B6 100%);
        color: white; margin-bottom: 16px; box-shadow: 0 10px 28px rgba(13,44,77,.16);
    }
    .hero h1 {font-size: 2rem; margin:0; line-height:1.1;}
    .hero p {margin:8px 0 0 0; opacity:.9; font-size:.98rem;}
    .section-title {font-size:1.12rem; font-weight:700; color:#123B68; margin:4px 0 10px;}
    .insight-card {padding:13px 16px; border:1px solid #DDE6EF; border-radius:12px; background:#F8FAFC; margin-bottom:8px;}
    .rule-card {padding:15px 18px; border-left:4px solid #2D8FC7; border-radius:9px; background:#F5F9FC;}
    div[data-testid="stMetric"] {background:#FFFFFF; border:1px solid #E3EAF1; padding:12px 14px; border-radius:13px; box-shadow:0 2px 9px rgba(15,42,68,.05);}
    div[data-testid="stMetric"] label {font-weight:600; color:#486176;}
    div[data-testid="stMetric"] [data-testid="stMetricValue"] {color:#123B68; font-weight:750;}
    .stButton > button[kind="primary"] {border-radius:10px; font-weight:700; min-height:46px;}
    .stDownloadButton > button {border-radius:10px; font-weight:700; min-height:44px;}
    [data-baseweb="tab-list"] {gap:5px; flex-wrap:wrap;}
    [data-baseweb="tab"] {border-radius:9px 9px 0 0; padding-left:12px; padding-right:12px;}
    </style>
    """,
    unsafe_allow_html=True,
)


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


def render_insights(items: list[str]):
    if not items:
        st.info("Ainda não há dados suficientes para gerar insights.")
        return
    for item in items:
        st.markdown(f'<div class="insight-card">💡 {item}</div>', unsafe_allow_html=True)


def compact_daily_table(snapshot: pd.DataFrame, target_posts: int, target_projects: int) -> pd.DataFrame:
    """Compact visual table for the daily operational view."""
    if snapshot.empty:
        return pd.DataFrame(columns=["Projetista", "Produção hoje", "Carteira atual", "Falta para meta", "Previsão 18h", "Situação"])

    df = snapshot.copy()
    numeric_cols = [
        "Postes realizados", "Projetos realizados", "Postes em carteira", "Projetos em carteira",
        "Previsão postes 18h", "Previsão projetos 18h",
    ]
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    def n(value) -> str:
        value = float(value)
        return str(int(value)) if value.is_integer() else f"{value:.1f}"

    status_icon = {
        "Meta atingida": "✅ Meta atingida",
        "Faixa mínima atingida": "🟢 Faixa mínima",
        "Carteira suficiente": "🔵 Carteira suficiente",
        "Falta de carga": "🟠 Falta de carga",
        "Risco produtivo": "🔴 Risco produtivo",
        "Encerrado abaixo da meta": "🔴 Abaixo da meta",
        "PLN pendente na carteira": "🟡 PLN pendente",
    }

    df["Produção hoje"] = df.apply(
        lambda r: f'{n(r["Postes realizados"])} postes • {n(r["Projetos realizados"])} proj.', axis=1
    )
    df["Carteira atual"] = df.apply(
        lambda r: f'{n(r["Postes em carteira"])} postes • {n(r["Projetos em carteira"])} proj.', axis=1
    )
    df["Falta para meta"] = df.apply(
        lambda r: f'{n(max(0, target_posts-r["Postes realizados"]))} postes • {n(max(0, target_projects-r["Projetos realizados"]))} proj.', axis=1
    )
    df["Previsão 18h"] = df.apply(
        lambda r: f'{n(r["Previsão postes 18h"])} postes • {n(r["Previsão projetos 18h"])} proj.', axis=1
    )
    df["Situação visual"] = df["Situação"].map(status_icon).fillna(df["Situação"])
    return df[["Projetista", "Produção hoje", "Carteira atual", "Falta para meta", "Previsão 18h", "Situação visual"]].rename(
        columns={"Situação visual": "Situação"}
    )


def compact_table_config():
    return {
        "Projetista": st.column_config.TextColumn("Projetista", width="large"),
        "Produção hoje": st.column_config.TextColumn("Produção hoje", width="medium"),
        "Carteira atual": st.column_config.TextColumn("Carteira atual", width="medium"),
        "Falta para meta": st.column_config.TextColumn("Falta para meta", width="medium"),
        "Previsão 18h": st.column_config.TextColumn("Previsão 18h", width="medium"),
        "Situação": st.column_config.TextColumn("Situação", width="medium"),
    }



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
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ---------- Sidebar ----------
st.sidebar.markdown("## ⚡ NIP Smart")
st.sidebar.caption("Distribuição e gestão de produtividade")
source_mode = st.sidebar.radio("Fonte de dados", ["Excel - validação", "Microsoft Lists", "DEMO"], index=0)
st.sidebar.divider()
st.sidebar.markdown("**Metas dos projetistas**")
st.sidebar.write(f"{TARGETS.min_posts}–{TARGETS.target_posts} postes/dia")
st.sidebar.write(f"{TARGETS.min_projects}–{TARGETS.target_projects} projetos/dia")
st.sidebar.caption("O excedente diário não reduz a meta do dia seguinte.")

NOW = datetime.now(ZoneInfo(TIMEZONE))

st.markdown(
    f"""
    <div class="hero">
      <h1>⚡ NIP Smart Distribuição</h1>
      <p>Distribuição automática, equilíbrio de carteira, metas em tempo real e análise preditiva dos projetistas.</p>
      <p><b>Jornada:</b> 08:00–12:00 / 13:12–18:00 &nbsp;•&nbsp; <b>Agora:</b> {NOW.strftime('%d/%m/%Y %H:%M')}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------- Upload / source ----------
if source_mode == "Excel - validação":
    st.markdown('<div class="section-title">📥 Bases operacionais</div>', unsafe_allow_html=True)
    up_base, up_designers = st.columns(2)
    with up_base:
        base_upload = st.file_uploader(
            "1. BASE LIST (.xlsx)", type=["xlsx"], key="base_list_main",
            help="Base exportada do Microsoft Lists.",
        )
        if base_upload is not None:
            try:
                base_bytes = base_upload.getvalue()
                sig = hashlib.sha256(base_bytes).hexdigest()
                if sig != st.session_state.base_excel_signature:
                    st.session_state.generated_excel_bytes = b""
                    st.session_state.generated_excel_name = ""
                    st.session_state.generated_distribution_suggestions = pd.DataFrame()
                    st.session_state.generated_distribution_summary = pd.DataFrame()
                st.session_state.base_excel_bytes = base_bytes
                st.session_state.base_excel_name = base_upload.name
                st.session_state.base_excel_signature = sig
                st.session_state.excel_projects = load_base_excel(base_upload)
                st.success(f"BASE LIST carregada: {len(st.session_state.excel_projects):,} registros.".replace(",", "."))
            except Exception as exc:
                st.error(f"Falha ao ler BASE LIST: {exc}")

    with up_designers:
        designer_upload = st.file_uploader(
            "2. PROJETISTAS (.xlsx)", type=["xlsx"], key="designers_main",
            help="Lista de projetistas elegíveis para receber obras.",
        )
        if designer_upload is not None:
            try:
                designer_bytes = designer_upload.getvalue()
                sig = hashlib.sha256(designer_bytes).hexdigest()
                if sig != st.session_state.designers_signature:
                    st.session_state.generated_excel_bytes = b""
                    st.session_state.generated_excel_name = ""
                    st.session_state.generated_distribution_suggestions = pd.DataFrame()
                    st.session_state.generated_distribution_summary = pd.DataFrame()
                st.session_state.designers_signature = sig
                st.session_state.uploaded_designers = load_designers_excel(designer_upload)
                st.success(f"Projetistas carregados: {len(st.session_state.uploaded_designers)}.")
            except Exception as exc:
                st.error(f"Falha ao ler PROJETISTAS.xlsx: {exc}")

    files_ready = bool(st.session_state.base_excel_bytes) and not st.session_state.uploaded_designers.empty
    st.markdown("#### ⚡ Distribuição automática")
    auto_clicked = st.button(
        "DISTRIBUIÇÃO AUTOMÁTICA",
        type="primary",
        use_container_width=True,
        disabled=not files_ready,
        key="auto_distribute_uploaded_files",
        help="Habilitado assim que as duas bases forem carregadas.",
    )
    if auto_clicked:
        st.session_state.request_auto_distribution = True
    if not files_ready:
        st.caption("Carregue a BASE LIST e a planilha PROJETISTAS para habilitar o botão.")
    else:
        st.caption("A BASE original não é alterada. O resultado é gerado em uma nova planilha para download.")

elif source_mode == "Microsoft Lists":
    designer_upload = st.sidebar.file_uploader("Planilha PROJETISTAS.xlsx", type=["xlsx"], key="designers_lists")
    if designer_upload is not None:
        try:
            st.session_state.uploaded_designers = load_designers_excel(designer_upload)
            st.sidebar.success(f"{len(st.session_state.uploaded_designers)} projetista(s) carregado(s).")
        except Exception as exc:
            st.sidebar.error(f"Falha ao ler PROJETISTAS.xlsx: {exc}")
    if not GRAPH_READY:
        st.sidebar.error("Configure as credenciais do Microsoft Graph nos Secrets do Streamlit.")
    elif st.sidebar.button("🔄 Sincronizar Microsoft Lists", use_container_width=True):
        try:
            repo = make_repository()
            st.session_state.graph_projects = repo.fetch_projects()
            st.session_state.column_diagnostics = repo.column_diagnostics()
            st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
            st.sidebar.success("Microsoft Lists sincronizado.")
        except Exception as exc:
            st.sidebar.error(str(exc))

# ---------- Resolve source ----------
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
    st.warning("Carregue a planilha **PROJETISTAS.xlsx** para iniciar a análise.")
    st.stop()
if projects.empty:
    st.info("Carregue a **BASE LIST.xlsx** ou sincronize o Microsoft Lists para iniciar.")
    st.stop()

# ---------- Analytics ----------
prepared = prepare_projects(projects, TIMEZONE)
baseline = build_assignment_baseline(projects, DESIGNERS, TARGETS, STATUS, TIMEZONE)
snapshot = build_daily_snapshots(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
quality = data_quality_summary(projects, STATUS)
week = weekly_metrics(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
month = monthly_metrics(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
designer_pred = designer_monthly_prediction_advanced(projects, DESIGNERS, NOW, TARGETS, STATUS, TIMEZONE)
designer_attention = designer_attention_table(snapshot, TARGETS.target_posts, TARGETS.target_projects)

eligible_norm = {normalize_person_name(n) for n in DESIGNERS}
pool_assigned = prepared[prepared["status_norm"].isin(STATUS.project_pool_set) & (prepared["assignee_norm"] != "")]
unlisted_names = sorted({
    name for name, norm in zip(pool_assigned["assignee"], pool_assigned["assignee_norm"])
    if norm not in eligible_norm
})

elapsed = productive_minutes_elapsed(NOW, TIMEZONE)
remaining = productive_minutes_remaining(NOW, TIMEZONE)
eligible_available = prepared[
    prepared["status_norm"].isin(STATUS.project_pool_set)
    & (prepared["assignee_norm"] == "")
    & prepared["posts_valid"]
    & prepared["sgo_present"]
]
available_posts = int(eligible_available["posts"].sum())
without_load = int((baseline["Projetos já atribuídos"] == 0).sum())
meta_hit_today = int((snapshot["Situação"] == "Meta atingida").sum())
load_values = pd.to_numeric(baseline["PLN já atribuído"], errors="coerce").fillna(0)
load_avg = float(load_values.mean()) if not load_values.empty else 0.0
load_min = int(load_values.min()) if not load_values.empty else 0
load_max = int(load_values.max()) if not load_values.empty else 0
load_spread = load_max - load_min

# ---------- One-click distribution ----------
if source_mode == "Excel - validação" and st.session_state.request_auto_distribution:
    try:
        auto_suggestions, auto_summary = suggest_assignments(projects, snapshot, TARGETS, STATUS)
        if auto_suggestions.empty:
            st.session_state.generated_excel_bytes = b""
            st.session_state.generated_excel_name = ""
            st.session_state.generated_distribution_suggestions = pd.DataFrame()
            st.session_state.generated_distribution_summary = auto_summary
            st.info("Nenhuma nova obra elegível precisa ser distribuída com a situação atual da base.")
        else:
            generated_at = datetime.now(ZoneInfo(TIMEZONE))
            output_bytes = generate_distributed_excel_bytes(
                st.session_state.base_excel_bytes,
                auto_suggestions,
                distribution_summary=auto_summary,
                target_posts=TARGETS.target_posts,
                target_projects=TARGETS.target_projects,
                generated_at=generated_at,
            )
            stem = (st.session_state.base_excel_name or "BASE_LIST.xlsx").rsplit(".", 1)[0]
            st.session_state.generated_excel_bytes = output_bytes
            st.session_state.generated_excel_name = f"{stem}_DISTRIBUIDA_{generated_at.strftime('%Y%m%d_%H%M%S')}.xlsx"
            st.session_state.generated_distribution_suggestions = auto_suggestions
            st.session_state.generated_distribution_summary = auto_summary
    except Exception as exc:
        st.error(f"Falha ao gerar a BASE LIST distribuída: {exc}")
    finally:
        st.session_state.request_auto_distribution = False

if source_mode == "Excel - validação" and st.session_state.generated_excel_bytes:
    generated_suggestions = st.session_state.generated_distribution_suggestions
    st.success(f"Distribuição concluída: {len(generated_suggestions)} obra(s) atribuída(s). A BASE original foi preservada.")
    dl1, dl2 = st.columns([3, 1])
    with dl1:
        st.download_button(
            "⬇️ BAIXAR BASE LIST DISTRIBUÍDA",
            data=st.session_state.generated_excel_bytes,
            file_name=st.session_state.generated_excel_name,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    dl2.metric("Novas atribuições", len(generated_suggestions))
    with st.expander("Ver obras distribuídas"):
        st.dataframe(generated_suggestions.drop(columns=["etag"], errors="ignore"), use_container_width=True, hide_index=True)

# ---------- Executive KPI strip ----------
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Projetistas", len(DESIGNERS))
k2.metric("Meta cheia hoje", meta_hit_today)
k3.metric("Atenção hoje", len(designer_attention))
k4.metric("Obras disponíveis", len(eligible_available))
k5.metric("Postes disponíveis", available_posts)
k6.metric("Tempo útil restante", format_minutes(remaining))

st.caption(
    f"Jornada: **{current_work_status(NOW, TIMEZONE)}** • Tempo produtivo: **{format_minutes(elapsed)} / {format_minutes(TOTAL_WORK_MINUTES)}**"
    + (f" • Última sincronização: **{st.session_state.last_sync.strftime('%d/%m/%Y %H:%M:%S')}**" if st.session_state.last_sync else "")
)

if quality["disponiveis_sem_pln"] or quality["atribuidos_sem_pln"] or quality["disponiveis_sem_sgo"]:
    st.warning(
        f"Qualidade da base: {quality['disponiveis_sem_pln']} disponível(is) sem PLN; "
        f"{quality['atribuidos_sem_pln']} atribuído(s) sem PLN; "
        f"{quality['disponiveis_sem_sgo']} disponível(is) sem Nota SGO."
    )

insights = management_insights(
    snapshot, baseline, designer_pred, len(eligible_available), available_posts,
)

# ---------- Tabs ----------
(
    tab_dashboard, tab_load, tab_today, tab_distribution,
    tab_periods, tab_predict, tab_projects, tab_quality, tab_automation, tab_config,
) = st.tabs([
    "🏠 Dashboard", "🎯 Carga e meta", "📊 Projetistas hoje",
    "⚙️ Distribuição", "📅 Semana e mês", "📈 Preditivo", "📋 Projetos",
    "🔎 Qualidade", "🤖 Automação", "🔧 Configuração",
])

with tab_dashboard:
    st.markdown('<div class="section-title">Visão executiva do dia</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1.45, 1])
    with c1:
        chart = snapshot[["Projetista", "Postes realizados", "Postes em carteira", "Situação"]].copy()
        chart = chart.sort_values("Postes realizados", ascending=True)
        fig = px.bar(
            chart, y="Projetista", x="Postes realizados", orientation="h",
            title="Postes concluídos hoje por projetista", hover_data=["Postes em carteira", "Situação"],
        )
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        st.plotly_chart(style_figure(fig, max(390, 28 * len(chart))), use_container_width=True)
    with c2:
        status_counts = snapshot["Situação"].value_counts().rename_axis("Situação").reset_index(name="Quantidade")
        fig = px.pie(status_counts, names="Situação", values="Quantidade", hole=.58, title="Situação dos projetistas")
        st.plotly_chart(style_figure(fig, 390), use_container_width=True)

    st.markdown('<div class="section-title">Atenção diária — projetistas</div>', unsafe_allow_html=True)
    if designer_attention.empty:
        st.success("Nenhum projetista está sinalizado para atenção no momento.")
    else:
        label = "Não atingiram / estão abaixo da meta hoje" if remaining == 0 else "Abaixo do ritmo, sem cobertura ou em risco hoje"
        st.caption(label)
        st.dataframe(
            designer_attention,
            use_container_width=True,
            hide_index=True,
            column_config=compact_table_config(),
            height=min(520, 78 + 35 * len(designer_attention)),
        )

    c3, c4 = st.columns([1.35, 1])
    with c3:
        balance = baseline[["Projetista", "PLN já atribuído", "Projetos já atribuídos", "Situação da carga"]].copy()
        balance = balance.sort_values("PLN já atribuído", ascending=True)
        fig = px.bar(
            balance, y="Projetista", x="PLN já atribuído", orientation="h",
            title="Equilíbrio da carteira ativa por projetista",
            hover_data=["Projetos já atribuídos", "Situação da carga"],
        )
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Referência {TARGETS.target_posts}")
        st.plotly_chart(style_figure(fig, max(360, 27 * len(balance))), use_container_width=True)
    with c4:
        st.markdown('<div class="section-title">Insights automáticos</div>', unsafe_allow_html=True)
        render_insights(insights)

    st.markdown('<div class="section-title">Foco da ferramenta</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="rule-card"><b>Projetistas:</b> produtividade, cumprimento de 25–30 postes / 4–5 projetos por dia e distribuição igualitária. '
        '<b>Carga de cada obra:</b> PLN da coluna R. As colunas de levantamento não participam dos indicadores.</div>',
        unsafe_allow_html=True,
    )

with tab_load:
    st.subheader("Carga já atribuída e meta restante")
    st.write(
        "A carga considera obras com **Status = Em projeto** e **Projetistas preenchido**. "
        "Para projetistas, o peso de distribuição continua sendo o **PLN da coluna R**."
    )
    load_cols = [
        "Projetista", "Projetos já atribuídos", "PLN já atribuído", "Projetos sem PLN",
        "Meta diária postes", "Meta diária projetos", "Meta restante postes", "Meta restante projetos",
        "Cobertura postes %", "Cobertura projetos %", "Nota SGO na carteira", "Situação da carga",
    ]
    st.dataframe(baseline[load_cols], use_container_width=True, hide_index=True)
    no_load = baseline[baseline["Projetos já atribuídos"] == 0]
    partial = baseline[(baseline["Projetos já atribuídos"] > 0) & ((baseline["Meta restante postes"] > 0) | (baseline["Meta restante projetos"] > 0))]
    covered = baseline[(baseline["Meta restante postes"] == 0) & (baseline["Meta restante projetos"] == 0)]
    b1, b2, b3 = st.columns(3)
    b1.metric("Meta inteira a distribuir", len(no_load))
    b2.metric("Parcialmente coberta", len(partial))
    b3.metric("Carga cobre a meta", len(covered))

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Carga média", f"{load_avg:.1f} postes")
    e2.metric("Menor carteira", f"{load_min} postes")
    e3.metric("Maior carteira", f"{load_max} postes")
    e4.metric("Diferença maior-menor", f"{load_spread} postes")

    balance_chart = baseline[["Projetista", "PLN já atribuído", "Projetos já atribuídos"]].sort_values("PLN já atribuído", ascending=True)
    fig = px.bar(
        balance_chart, y="Projetista", x="PLN já atribuído", orientation="h",
        hover_data=["Projetos já atribuídos"], title="Distribuição atual da carga entre projetistas",
    )
    fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
    st.plotly_chart(style_figure(fig, max(420, 26 * len(balance_chart))), use_container_width=True)

with tab_today:
    st.subheader("Produção diária dos projetistas")
    st.caption("Visão resumida para decisão rápida. Os detalhes técnicos ficam recolhidos abaixo.")

    daily_compact = compact_daily_table(snapshot, TARGETS.target_posts, TARGETS.target_projects)
    st.dataframe(
        daily_compact,
        use_container_width=True,
        hide_index=True,
        column_config=compact_table_config(),
        height=min(620, 78 + 35 * len(daily_compact)),
    )

    with st.expander("Ver indicadores detalhados"):
        detail_cols = [
            "Projetista", "Postes realizados", "Projetos realizados", "Postes em carteira", "Projetos em carteira",
            "Potencial postes", "Potencial projetos", "Meta postes agora", "Meta projetos agora",
            "Aderência postes %", "Aderência projetos %", "Previsão postes 18h", "Previsão projetos 18h",
            "Sem cobertura postes", "Sem cobertura projetos", "Status ritmo", "Situação",
        ]
        st.dataframe(snapshot[detail_cols], use_container_width=True, hide_index=True)

    melted = snapshot[["Projetista", "Postes realizados", "Postes em carteira"]].melt(
        id_vars="Projetista", var_name="Componente", value_name="Postes"
    )
    fig = px.bar(melted, x="Projetista", y="Postes", color="Componente", barmode="stack", title="Realizado + carteira")
    fig.add_hline(y=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
    st.plotly_chart(style_figure(fig, 430), use_container_width=True)

    st.markdown("#### Quem precisa de atenção hoje")
    if designer_attention.empty:
        st.success("Nenhum projetista precisa de atenção neste momento.")
    else:
        st.dataframe(
            designer_attention,
            use_container_width=True,
            hide_index=True,
            column_config=compact_table_config(),
            height=min(520, 78 + 35 * len(designer_attention)),
        )

with tab_distribution:
    st.subheader("Distribuição inteligente de obras")
    st.write(
        "Elegível = **Status Em projeto + Projetistas vazio + Nota SGO preenchida + PLN maior que zero**. "
        "O motor distribui apenas o necessário para completar a cobertura de 30 postes / 5 projetos."
    )
    suggestions, distribution_summary = suggest_assignments(projects, snapshot, TARGETS, STATUS)
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Elegíveis", len(eligible_available))
    d2.metric("PLN elegível", available_posts)
    d3.metric("Sugestões agora", len(suggestions))
    d4.metric("Projetistas sem carga", without_load)

    if suggestions.empty:
        st.info("Não há novas atribuições sugeridas para a situação atual.")
    else:
        st.dataframe(suggestions.drop(columns=["etag"], errors="ignore"), use_container_width=True, hide_index=True)

    if not distribution_summary.empty:
        st.markdown("#### Cobertura após a distribuição sugerida")
        st.dataframe(distribution_summary, use_container_width=True, hide_index=True)
        post_dist = distribution_summary.sort_values("Potencial postes após distribuição", ascending=True)
        fig = px.bar(
            post_dist, y="Projetista", x="Potencial postes após distribuição", orientation="h",
            hover_data=["Potencial projetos após distribuição", "Novos projetos sugeridos", "Novos postes sugeridos"],
            title="Carga potencial após a distribuição automática",
        )
        fig.add_vline(x=TARGETS.target_posts, line_dash="dash", annotation_text=f"Meta {TARGETS.target_posts}")
        st.plotly_chart(style_figure(fig, max(420, 26 * len(post_dist))), use_container_width=True)

    if source_mode in {"DEMO", "Excel - validação"} and not suggestions.empty:
        if st.button("Simular atribuições nesta sessão", type="primary"):
            updated = projects.copy()
            for _, row in suggestions.iterrows():
                updated.loc[updated["item_id"].astype(str) == str(row["item_id"]), "assignee"] = row["Projetista"]
            if source_mode == "DEMO":
                st.session_state.demo_projects = updated
            else:
                st.session_state.excel_projects = updated
            st.success("Atribuições simuladas sem alterar a fonte original.")
            st.rerun()
    elif source_mode == "Microsoft Lists" and not suggestions.empty:
        if not WRITE_ENABLED:
            st.warning("Escrita no Microsoft Lists está bloqueada nos Secrets.")
        else:
            confirm = st.checkbox("Confirmo a gravação destas atribuições no Microsoft Lists")
            if st.button("Aplicar no Microsoft Lists", type="primary", disabled=not confirm):
                try:
                    repo = make_repository()
                    lookup_by_name = {
                        normalize_person_name(r["name"]): r.get("sharepoint_lookup_id")
                        for _, r in designers_df.iterrows()
                    }
                    for _, row in suggestions.iterrows():
                        etag = None if pd.isna(row.get("etag")) else row.get("etag")
                        lookup_id = lookup_by_name.get(normalize_person_name(row["Projetista"]))
                        repo.assign_project(str(row["item_id"]), str(row["Projetista"]), etag, lookup_id)
                    st.session_state.graph_projects = repo.fetch_projects()
                    st.session_state.column_diagnostics = repo.column_diagnostics()
                    st.session_state.last_sync = datetime.now(ZoneInfo(TIMEZONE))
                    st.success(f"{len(suggestions)} projeto(s) atribuídos no Microsoft Lists.")
                    st.rerun()
                except GraphError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Falha ao aplicar: {exc}")

with tab_periods:
    st.subheader("Acompanhamento semanal e mensal")
    p1, p2 = st.columns(2)
    with p1:
        st.markdown("#### Semana")
        st.dataframe(week, use_container_width=True, hide_index=True)
        if not week.empty:
            fig = px.bar(week, x="Projetista", y=["Postes", "Referência postes"], barmode="group", title="Semana — postes x referência")
            st.plotly_chart(style_figure(fig, 390), use_container_width=True)
    with p2:
        st.markdown("#### Mês")
        st.dataframe(month, use_container_width=True, hide_index=True)
        if not month.empty:
            fig = px.bar(month, x="Projetista", y=["Postes", "Referência postes"], barmode="group", title="Mês — postes x referência acumulada")
            st.plotly_chart(style_figure(fig, 390), use_container_width=True)
    st.caption("Metas semanais e mensais são indicadores consolidados; excedentes não compensam a meta diária seguinte.")

with tab_predict:
    st.subheader("Análise preditiva dos projetistas")
    st.caption("A previsão combina a produção acumulada com o ritmo médio dos últimos 5 dias úteis e projeta o fechamento do mês. O excedente diário não reduz a meta do dia seguinte.")

    p1, p2 = st.columns([1.3, 1])
    with p1:
        st.dataframe(designer_pred, use_container_width=True, hide_index=True)
    with p2:
        if not designer_pred.empty:
            trend_counts = designer_pred["Tendência"].value_counts().rename_axis("Tendência").reset_index(name="Projetistas")
            fig = px.pie(trend_counts, names="Tendência", values="Projetistas", hole=.58, title="Tendência de fechamento do mês")
            st.plotly_chart(style_figure(fig, 390), use_container_width=True)

    if not designer_pred.empty:
        c1, c2 = st.columns(2)
        with c1:
            pred_plot = designer_pred[["Projetista", "Projeção postes mês", "Meta mensal postes", "Tendência"]].copy()
            fig = px.scatter(
                pred_plot, x="Meta mensal postes", y="Projeção postes mês", hover_name="Projetista",
                color="Tendência", title="Projeção de postes x referência mensal",
            )
            max_v = max(pred_plot["Meta mensal postes"].max(), pred_plot["Projeção postes mês"].max(), 1)
            fig.add_shape(type="line", x0=0, y0=0, x1=max_v, y1=max_v, line=dict(dash="dash"))
            st.plotly_chart(style_figure(fig, 420), use_container_width=True)
        with c2:
            consistency = designer_pred.sort_values("Consistência meta cheia %", ascending=True)
            fig = px.bar(
                consistency, y="Projetista", x="Consistência meta cheia %", orientation="h",
                title="Consistência — dias com meta cheia atingida",
            )
            fig.add_vline(x=90, line_dash="dash", annotation_text="90%")
            st.plotly_chart(style_figure(fig, max(420, 25 * len(consistency))), use_container_width=True)

        st.markdown("#### Projetistas que requerem acompanhamento")
        need = designer_pred[designer_pred["Tendência"] == "Requer acompanhamento"]
        if need.empty:
            st.success("Nenhum projetista está classificado como 'Requer acompanhamento' na projeção atual.")
        else:
            st.dataframe(need, use_container_width=True, hide_index=True)

with tab_projects:
    st.subheader("Base operacional")
    show = prepared.copy()
    show["Disponibilidade"] = ""
    pool_mask = show["status_norm"].isin(STATUS.project_pool_set)
    show.loc[pool_mask & (show["assignee_norm"] == ""), "Disponibilidade"] = "Disponível"
    show.loc[pool_mask & (show["assignee_norm"] != ""), "Disponibilidade"] = "Atribuído"
    display = show[[
        "note", "sgo", "status", "posts", "posts_valid", "assignee",
        "regional", "municipality", "deadline", "Disponibilidade",
    ]].rename(columns={
        "note": "Nº da nota", "sgo": "Nota SGO", "status": "Status", "posts": "R - PLN",
        "posts_valid": "PLN válido", "assignee": "Projetista",
        "regional": "Regional", "municipality": "Município", "deadline": "Prazo",
    })
    st.dataframe(display, use_container_width=True, hide_index=True)

with tab_quality:
    st.subheader("Qualidade e elegibilidade da base")
    q1, q2, q3, q4, q5 = st.columns(5)
    q1.metric("Em projeto", quality["em_projeto"])
    q2.metric("Sem projetista", quality["disponiveis"])
    q3.metric("Já atribuídos", quality["atribuidos"])
    q4.metric("Disponíveis sem PLN", quality["disponiveis_sem_pln"])
    q5.metric("Atribuídos sem PLN", quality["atribuidos_sem_pln"])

    status_counts = prepared["status"].replace("", "Sem status").value_counts().head(15).rename_axis("Status").reset_index(name="Quantidade")
    fig = px.bar(status_counts, x="Quantidade", y="Status", orientation="h", title="Principais status da BASE LIST")
    st.plotly_chart(style_figure(fig, 470), use_container_width=True)

    blocked = prepared[
        prepared["status_norm"].isin(STATUS.project_pool_set)
        & (prepared["assignee_norm"] == "")
        & (~prepared["posts_valid"] | ~prepared["sgo_present"])
    ][["note", "sgo", "posts", "regional", "municipality"]].rename(columns={
        "note": "Nº da nota", "sgo": "Nota SGO", "posts": "PLN", "regional": "Regional", "municipality": "Município"
    })
    if not blocked.empty:
        st.markdown("#### Obras bloqueadas para distribuição automática")
        st.dataframe(blocked, use_container_width=True, hide_index=True)
    if unlisted_names:
        st.markdown("#### Projetistas atribuídos que não constam na planilha PROJETISTAS")
        st.write(unlisted_names)

with tab_automation:
    st.subheader("Automação por ciclos")
    a1, a2, a3 = st.columns(3)
    a1.metric("Janela", current_work_status(NOW, TIMEZONE))
    a2.metric("Tempo útil restante", format_minutes(remaining))
    a3.metric("Escrita no Lists", "Liberada" if WRITE_ENABLED else "Bloqueada")

    policy = AutomationPolicy(timezone=TIMEZONE, require_work_hours=True)
    audit = AuditStore("data/automation_audit.sqlite3")
    engine = AutomationEngine(TARGETS, STATUS, policy=policy, audit=audit)
    if st.button("Executar ciclo automático agora", type="primary", use_container_width=True):
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
        st.markdown("#### Últimos ciclos")
        st.dataframe(recent, use_container_width=True, hide_index=True)

with tab_config:
    st.subheader("Regras da ferramenta")
    st.code(
        f"""Jornada: 08:00–12:00 / 13:12–18:00
Tempo produtivo: 528 minutos
Projetistas: {TARGETS.target_posts} postes / {TARGETS.target_projects} projetos por dia
Faixa mínima projetistas: {TARGETS.min_posts} postes / {TARGETS.min_projects} projetos
Meta cumulativa: NÃO

Distribuição de projetos:
- Status: Em projeto
- Disponível: Projetistas vazio
- Peso da obra: coluna R (PLN)
- Identificador: coluna C (Nota SGO)

Produção do projetista:
- Dia: Data de entrega do projeto
- Postes: Qtd. de poste final; se vazia, PLN como fallback

Fonte atual: {source_mode}
Escrita no Microsoft Lists: {'SIM' if WRITE_ENABLED else 'NÃO'}"""
    )
    st.markdown("#### Mapeamento Microsoft Lists")
    st.json(FIELD_MAP.__dict__)
    if source_mode == "Microsoft Lists" and not st.session_state.column_diagnostics.empty:
        st.dataframe(st.session_state.column_diagnostics, use_container_width=True, hide_index=True)
