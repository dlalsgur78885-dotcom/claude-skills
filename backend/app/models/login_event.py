"""Login event log — admin sees who logged in from where (IP + user-agent).

One row per successful login. Append-only — failed attempts are NOT recorded
(admin chose 성공만 기록). `ip` is the X-Forwarded-For first hop because nginx
sits in front and proxies the real client (see nginx.conf proxy_set_header).
`user_agent` is truncated to 500 chars to bound pathological headers without
silently dropping useful info.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LoginEvent(Base):
    __tablename__ = "login_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    ip: Mapped[str] = mapped_column(String(64))
    user_agent: Mapped[str] = mapped_column(String(500), default="")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now, index=True
    )
