from __future__ import annotations

import requests


def send_distribution_webhook(webhook_url: str, title: str, message: str, timeout: int = 12) -> None:
    """Send a generic JSON payload to a configured Power Automate/Teams-compatible webhook.

    The exact downstream formatting is intentionally left to the Power Automate flow.
    No credentials are stored here; the URL must come from Streamlit Secrets.
    """
    if not webhook_url:
        raise ValueError("Webhook não configurado.")
    response = requests.post(webhook_url, json={"title": title, "message": message}, timeout=timeout)
    response.raise_for_status()
