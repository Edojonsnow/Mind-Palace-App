import httpx
import pytest

from app.core.config import Settings
from app.services.neon_auth_admin import NeonAuthAdminError, delete_neon_auth_user


def test_delete_neon_auth_user_calls_branch_scoped_management_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(httpx.codes.NO_CONTENT)

    app_settings = Settings(
        neon_api_key="test-api-key",
        neon_project_id="project-id",
        neon_auth_branch_id="branch-id",
    )

    delete_neon_auth_user(
        "auth-user-id",
        app_settings=app_settings,
        transport=httpx.MockTransport(handler),
    )

    assert len(requests) == 1
    assert requests[0].method == "DELETE"
    assert requests[0].url.path == (
        "/api/v2/projects/project-id/branches/branch-id/auth/users/auth-user-id"
    )
    assert requests[0].headers["authorization"] == "Bearer test-api-key"


def test_delete_neon_auth_user_treats_missing_identity_as_success() -> None:
    app_settings = Settings(
        neon_api_key="test-api-key",
        neon_project_id="project-id",
        neon_auth_branch_id="branch-id",
    )

    delete_neon_auth_user(
        "already-deleted-user",
        app_settings=app_settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(httpx.codes.NOT_FOUND),
        ),
    )


def test_delete_neon_auth_user_requires_management_configuration() -> None:
    with pytest.raises(NeonAuthAdminError, match="NEON_API_KEY"):
        delete_neon_auth_user(
            "auth-user-id",
            app_settings=Settings(
                neon_project_id="project-id",
                neon_auth_branch_id="branch-id",
            ),
        )
