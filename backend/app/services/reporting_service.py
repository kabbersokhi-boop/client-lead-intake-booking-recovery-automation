from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models import Appointment, FollowUp, Lead, RecoveryIncident
from app.schemas.reporting import ManagementSummary

BUSINESS_TIMEZONE = "America/Vancouver"
FURNACE_SERVICE = "furnace_service"
AIR_CONDITIONING_SERVICE = "air_conditioning_service"


def business_day_window_utc(business_date: date) -> tuple[datetime, datetime]:
    business_zone = ZoneInfo(BUSINESS_TIMEZONE)
    local_start = datetime.combine(business_date, time.min, tzinfo=business_zone)
    local_end = datetime.combine(business_date + timedelta(days=1), time.min, tzinfo=business_zone)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


class ReportingService:
    def management_summary(
        self,
        db: Session,
        *,
        business_date: date | None = None,
        generated_at: datetime | None = None,
    ) -> ManagementSummary:
        generated_at = generated_at or datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        else:
            generated_at = generated_at.astimezone(timezone.utc)
        report_date = business_date or generated_at.astimezone(
            ZoneInfo(BUSINESS_TIMEZONE)
        ).date()
        window_start, window_end = business_day_window_utc(report_date)

        lead_counts = db.execute(
            select(
                func.count(Lead.id),
                func.sum(case((Lead.service_type == FURNACE_SERVICE, 1), else_=0)),
                func.sum(
                    case((Lead.service_type == AIR_CONDITIONING_SERVICE, 1), else_=0)
                ),
                func.sum(
                    case(
                        (
                            Lead.service_type.in_(
                                [FURNACE_SERVICE, AIR_CONDITIONING_SERVICE]
                            ),
                            0,
                        ),
                        else_=1,
                    )
                ),
                func.sum(case((Lead.needs_review.is_(True), 1), else_=0)),
            ).where(Lead.created_at >= window_start, Lead.created_at < window_end)
        ).one()

        appointments_booked = db.scalar(
            select(func.count(Appointment.id)).where(
                Appointment.status == "booked",
                Appointment.created_at >= window_start,
                Appointment.created_at < window_end,
            )
        )
        follow_ups_sent = db.scalar(
            select(func.count(FollowUp.id)).where(
                FollowUp.status == "sent",
                FollowUp.sent_at >= window_start,
                FollowUp.sent_at < window_end,
            )
        )
        open_incidents = db.scalar(
            select(func.count(RecoveryIncident.id)).where(RecoveryIncident.state == "open")
        )

        return ManagementSummary(
            report_key=f"hvac-daily:{report_date.isoformat()}",
            business_date=report_date,
            window_start_utc=window_start,
            window_end_utc=window_end,
            generated_at=generated_at,
            leads_received=lead_counts[0] or 0,
            furnace_requests=lead_counts[1] or 0,
            air_conditioning_requests=lead_counts[2] or 0,
            other_or_unknown_requests=lead_counts[3] or 0,
            needs_review=lead_counts[4] or 0,
            appointments_booked=appointments_booked or 0,
            follow_ups_sent=follow_ups_sent or 0,
            open_recovery_incidents_at_generated_at=open_incidents or 0,
        )
