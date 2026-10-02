from __future__ import annotations

from dataclasses import dataclass, fields as dataclass_fields
from typing import Any

import pandas as pd

from .graph_client import GraphClient
from .name_utils import normalize_column_label


@dataclass(frozen=True)
class FieldMap:
    # These can be either display names or internal SharePoint names.
    note: str = "N° da nota"
    sgo: str = "Nota SGO"
    status: str = "Status do projeto"
    project_type: str = "PI (Tipo Projeto)"
    regional: str = "Regional"
    municipality: str = "Município"
    deadline: str = "Prazo"
    posts: str = "P L N"
    assignee: str = "Projetistas"
    completed_at: str = "Data de entrega do projeto"
    actual_posts: str = "Qtd. de poste"
    priority: str = "Prioridade"

    def values(self) -> list[str]:
        return [getattr(self, f.name) for f in dataclass_fields(self) if getattr(self, f.name)]


@dataclass(frozen=True)
class ResolvedFieldMap:
    note: str
    sgo: str
    status: str
    project_type: str | None
    regional: str
    municipality: str
    deadline: str
    posts: str
    assignee: str
    completed_at: str
    actual_posts: str | None
    priority: str | None
    assignee_is_person: bool = False

    def graph_fields(self) -> list[str]:
        values = [
            self.note, self.sgo, self.status, self.project_type, self.regional, self.municipality,
            self.deadline, self.posts, self.assignee, self.completed_at,
            self.actual_posts, self.priority,
        ]
        return [v for v in values if v]


class ListsProjectRepository:
    def __init__(self, graph: GraphClient, site_id: str, list_id: str, fields: FieldMap):
        self.graph = graph
        self.site_id = site_id
        self.list_id = list_id
        self.fields = fields
        self._resolved: ResolvedFieldMap | None = None
        self._column_meta: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _value(values: dict[str, Any], name: str | None) -> Any:
        return values.get(name) if name else None

    @staticmethod
    def _person_display(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return str(value.get("displayName") or value.get("LookupValue") or value.get("value") or "").strip()
        if isinstance(value, list):
            parts = [ListsProjectRepository._person_display(v) for v in value]
            return "; ".join(p for p in parts if p)
        return str(value).strip()

    def resolve_fields(self, force: bool = False) -> ResolvedFieldMap:
        if self._resolved is not None and not force:
            return self._resolved

        columns = self.graph.list_columns(self.site_id, self.list_id)
        by_internal = {normalize_column_label(c.get("name")): c for c in columns if c.get("name")}
        by_display = {normalize_column_label(c.get("displayName")): c for c in columns if c.get("displayName")}

        def resolve(label: str, required: bool = True) -> dict[str, Any] | None:
            key = normalize_column_label(label)
            col = by_internal.get(key) or by_display.get(key)
            if col is None and required:
                raise ValueError(
                    f"Coluna '{label}' não encontrada no Microsoft Lists. "
                    "Confira o nome exibido e o nome interno da coluna."
                )
            return col

        resolved_meta: dict[str, dict[str, Any] | None] = {
            "note": resolve(self.fields.note),
            "sgo": resolve(self.fields.sgo),
            "status": resolve(self.fields.status),
            "project_type": resolve(self.fields.project_type, required=False),
            "regional": resolve(self.fields.regional),
            "municipality": resolve(self.fields.municipality),
            "deadline": resolve(self.fields.deadline),
            "posts": resolve(self.fields.posts),
            "assignee": resolve(self.fields.assignee),
            "completed_at": resolve(self.fields.completed_at),
            "actual_posts": resolve(self.fields.actual_posts, required=False),
            "priority": resolve(self.fields.priority, required=False),
        }
        self._column_meta = {k: v for k, v in resolved_meta.items() if v is not None}
        assignee_meta = resolved_meta["assignee"] or {}
        assignee_is_person = bool(assignee_meta.get("personOrGroup"))

        def internal(key: str) -> str | None:
            col = resolved_meta[key]
            return col.get("name") if col else None

        self._resolved = ResolvedFieldMap(
            note=internal("note") or "",
            sgo=internal("sgo") or "",
            status=internal("status") or "",
            project_type=internal("project_type"),
            regional=internal("regional") or "",
            municipality=internal("municipality") or "",
            deadline=internal("deadline") or "",
            posts=internal("posts") or "",
            assignee=internal("assignee") or "",
            completed_at=internal("completed_at") or "",
            actual_posts=internal("actual_posts"),
            priority=internal("priority"),
            assignee_is_person=assignee_is_person,
        )
        return self._resolved

    def column_diagnostics(self) -> pd.DataFrame:
        self.resolve_fields()
        rows = []
        for logical_name, meta in self._column_meta.items():
            rows.append(
                {
                    "Campo lógico": logical_name,
                    "Nome exibido": meta.get("displayName"),
                    "Nome interno": meta.get("name"),
                    "Pessoa/Grupo": bool(meta.get("personOrGroup")),
                    "Lookup": bool(meta.get("lookup")),
                }
            )
        return pd.DataFrame(rows)

    def fetch_projects(self) -> pd.DataFrame:
        f = self.resolve_fields()
        requested_fields = f.graph_fields()
        if f.assignee_is_person:
            requested_fields.append(f"{f.assignee}LookupId")

        raw_items = self.graph.list_items(self.site_id, self.list_id, requested_fields)
        rows: list[dict[str, Any]] = []
        for item in raw_items:
            values = item.get("fields", {}) or {}
            raw_posts = self._value(values, f.posts)
            posts_numeric = pd.to_numeric(pd.Series([raw_posts]), errors="coerce").iloc[0]
            rows.append(
                {
                    "item_id": str(item.get("id", "")),
                    "note": self._value(values, f.note),
                    "sgo": self._value(values, f.sgo),
                    "status": self._value(values, f.status),
                    "project_type": self._value(values, f.project_type),
                    "regional": self._value(values, f.regional),
                    "municipality": self._value(values, f.municipality),
                    "deadline": self._value(values, f.deadline),
                    "posts": int(posts_numeric) if pd.notna(posts_numeric) else 0,
                    "posts_valid": bool(pd.notna(posts_numeric) and float(posts_numeric) > 0),
                    "assignee": self._person_display(self._value(values, f.assignee)),
                    "assignee_lookup_id": self._value(values, f"{f.assignee}LookupId") if f.assignee_is_person else None,
                    "completed_at": self._value(values, f.completed_at),
                    "actual_posts": self._value(values, f.actual_posts),
                    "priority": self._value(values, f.priority),
                    "assigned_at": None,
                    "complexity": None,
                    "modified_at": item.get("lastModifiedDateTime"),
                    "etag": item.get("eTag") or item.get("@odata.etag"),
                }
            )
        return pd.DataFrame(rows)

    def assignee_is_person_field(self) -> bool:
        return self.resolve_fields().assignee_is_person

    def assign_project(
        self,
        item_id: str,
        designer: str,
        etag: str | None = None,
        sharepoint_lookup_id: int | str | None = None,
    ) -> dict[str, Any]:
        f = self.resolve_fields()
        if f.assignee_is_person:
            if sharepoint_lookup_id in (None, "") or pd.isna(sharepoint_lookup_id):
                raise ValueError(
                    "A coluna Projetistas é do tipo Pessoa/Grupo. "
                    "Informe SharePointLookupId para o projetista antes de habilitar a escrita automática."
                )
            payload = {f"{f.assignee}LookupId": str(int(float(sharepoint_lookup_id)))}
        else:
            payload = {f.assignee: designer}

        return self.graph.update_item_fields(
            self.site_id,
            self.list_id,
            item_id,
            payload,
            etag=etag,
        )
