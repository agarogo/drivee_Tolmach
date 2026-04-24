from __future__ import annotations

import uuid
from datetime import datetime

from app.db import Base


PLATFORM_SCHEMA = "app"


def utcnow() -> datetime:
    return datetime.utcnow()


def uuid_pk() -> uuid.UUID:
    return uuid.uuid4()


class PlatformBase:
    __table_args__ = {"schema": PLATFORM_SCHEMA}
