from urllib.parse import quote

import httpx

from app.core.config import Settings, settings


class NeonAuthAdminError(RuntimeError):
    """Raised when the Neon Auth administrative deletion cannot be completed."""


def delete_neon_auth_user(
    auth_user_id: str,
    *,
    app_settings: Settings = settings,
    transport: httpx.BaseTransport | None = None,
) -> None:
    """Permanently delete a user from the configured Neon Auth branch.

    A 404 is treated as success so a retry after an uncertain network failure is
    safe. The local Mind Palace record is only purged after this call succeeds.
    """
    required = {
        "NEON_API_KEY": app_settings.neon_api_key,
        "NEON_PROJECT_ID": app_settings.neon_project_id,
        "NEON_AUTH_BRANCH_ID": app_settings.neon_auth_branch_id,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise NeonAuthAdminError(
            "Neon Auth deletion is not configured: " + ", ".join(missing)
        )

    project_id = quote(app_settings.neon_project_id or "", safe="")
    branch_id = quote(app_settings.neon_auth_branch_id or "", safe="")
    user_id = quote(auth_user_id, safe="")
    url = (
        f"{app_settings.neon_management_api_base_url.rstrip('/')}/projects/"
        f"{project_id}/branches/{branch_id}/auth/users/{user_id}"
    )

    try:
        with httpx.Client(
            timeout=app_settings.neon_management_api_timeout_seconds,
            transport=transport,
        ) as client:
            response = client.delete(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {app_settings.neon_api_key}",
                },
            )
    except httpx.HTTPError as error:
        raise NeonAuthAdminError("Neon Auth deletion request failed") from error

    if response.status_code in {httpx.codes.NO_CONTENT, httpx.codes.NOT_FOUND}:
        return

    raise NeonAuthAdminError(
        f"Neon Auth deletion returned HTTP {response.status_code}"
    )
