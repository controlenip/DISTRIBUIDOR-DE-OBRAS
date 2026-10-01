from __future__ import annotations

from typing import Any, Iterable

import msal
import requests


class GraphError(RuntimeError):
    pass


class GraphClient:
    BASE_URL = "https://graph.microsoft.com/v1.0"
    SCOPES = ["https://graph.microsoft.com/.default"]

    def __init__(self, tenant_id: str, client_id: str, client_secret: str, timeout: int = 30):
        if not all([tenant_id, client_id, client_secret]):
            raise ValueError("tenant_id, client_id e client_secret são obrigatórios.")
        self.timeout = timeout
        self.app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret,
        )
        self.session = requests.Session()

    def _token(self) -> str:
        result = self.app.acquire_token_for_client(scopes=self.SCOPES)
        token = result.get("access_token")
        if not token:
            detail = result.get("error_description") or result.get("error") or "Falha desconhecida"
            raise GraphError(f"Não foi possível autenticar no Microsoft Graph: {detail}")
        return token

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _raise(self, response: requests.Response) -> None:
        if response.ok:
            return
        try:
            body: Any = response.json()
        except Exception:
            body = response.text
        raise GraphError(f"Microsoft Graph retornou HTTP {response.status_code}: {body}")

    def get_all(self, path_or_url: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        url = path_or_url if path_or_url.startswith("http") else f"{self.BASE_URL}/{path_or_url.lstrip('/')}"
        items: list[dict[str, Any]] = []
        current_params = params
        while url:
            response = self.session.get(url, headers=self._headers(), params=current_params, timeout=self.timeout)
            self._raise(response)
            payload = response.json()
            items.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
            current_params = None
        return items

    def list_columns(self, site_id: str, list_id: str) -> list[dict[str, Any]]:
        return self.get_all(f"sites/{site_id}/lists/{list_id}/columns", params={"$top": "200"})

    def list_items(self, site_id: str, list_id: str, fields: Iterable[str]) -> list[dict[str, Any]]:
        selected = ",".join(dict.fromkeys(f for f in fields if f))
        params = {"$top": "200"}
        params["$expand"] = f"fields($select={selected})" if selected else "fields"
        return self.get_all(f"sites/{site_id}/lists/{list_id}/items", params=params)

    def update_item_fields(
        self,
        site_id: str,
        list_id: str,
        item_id: str,
        fields: dict[str, Any],
        etag: str | None = None,
    ) -> dict[str, Any]:
        url = f"{self.BASE_URL}/sites/{site_id}/lists/{list_id}/items/{item_id}/fields"
        extra_headers = {"If-Match": etag} if etag else None
        response = self.session.patch(
            url,
            headers=self._headers(extra_headers),
            json=fields,
            timeout=self.timeout,
        )
        self._raise(response)
        return response.json()
