from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class ManagementSummary(BaseModel):
    report_version: Literal[1] = 1
    report_type: Literal["hvac_management_snapshot"] = "hvac_management_snapshot"
    report_key: str
    business_date: date
    business_timezone: Literal["America/Vancouver"] = "America/Vancouver"
    window_start_utc: datetime
    window_end_utc: datetime
    generated_at: datetime
    leads_received: int = Field(ge=0)
    furnace_requests: int = Field(ge=0)
    air_conditioning_requests: int = Field(ge=0)
    other_or_unknown_requests: int = Field(ge=0)
    needs_review: int = Field(ge=0)
    appointments_booked: int = Field(ge=0)
    follow_ups_sent: int = Field(ge=0)
    open_recovery_incidents_at_generated_at: int = Field(ge=0)
