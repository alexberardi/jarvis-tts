"""
App-to-app authentication dependency for jarvis-tts.

Phase 4 Migration: Node auth -> App-to-app auth
- Services authenticate via X-Jarvis-App-Id + X-Jarvis-App-Key headers
- Context headers (X-Context-Household-Id, X-Context-Node-Id) provide request origin
"""

from jarvis_auth_client.fastapi import require_app_auth as _require_app_auth

# The dependency returned by require_app_auth() already uses Header() annotations,
# so FastAPI extracts headers correctly. Do NOT wrap it in a plain-param function.
verify_app_auth = _require_app_auth()
