"""
App-to-app authentication dependency for jarvis-tts.

Phase 4 Migration: Node auth -> App-to-app auth
- Services authenticate via X-Jarvis-App-Id + X-Jarvis-App-Key headers
- Context headers (X-Context-Household-Id, X-Context-Node-Id) provide request origin
"""

from jarvis_auth_client.fastapi import require_app_auth as _require_app_auth
from jarvis_auth_client.models import AppAuthResult

# Create the app auth dependency
_app_auth_dep = _require_app_auth()


def verify_app_auth(
    x_jarvis_app_id: str | None = None,
    x_jarvis_app_key: str | None = None,
    x_context_household_id: str | None = None,
    x_context_node_id: str | None = None,
    x_context_user_id: int | None = None,
) -> AppAuthResult:
    """
    Verify app-to-app credentials against jarvis-auth service.

    This dependency validates that the calling service (e.g., command-center)
    has valid app credentials. Context headers provide information about
    the original request (household, node, user).

    Returns:
        AppAuthResult containing app validation and request context.

    Raises:
        HTTPException: If authentication fails.
    """
    return _app_auth_dep(
        x_jarvis_app_id=x_jarvis_app_id,
        x_jarvis_app_key=x_jarvis_app_key,
        x_context_household_id=x_context_household_id,
        x_context_node_id=x_context_node_id,
        x_context_user_id=x_context_user_id,
    )
