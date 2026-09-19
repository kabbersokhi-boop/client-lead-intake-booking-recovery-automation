import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from app.config import settings


def require_crm_adapter_key(
    x_crm_adapter_key: Annotated[str | None, Header()] = None,
) -> None:
    configured = settings.crm_adapter_api_key
    if configured is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="CRM adapter authentication is not configured.",
        )
    if not x_crm_adapter_key or not secrets.compare_digest(
        x_crm_adapter_key, configured.get_secret_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized CRM request."
        )
