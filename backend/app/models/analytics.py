from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, PLATFORM_SCHEMA, PlatformBase, utcnow, uuid_pk


class City(Base):
    __tablename__ = "cities"

    city_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    country: Mapped[str] = mapped_column(String(64), default="RU", index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class Driver(Base):
    __tablename__ = "drivers"

    driver_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.city_id"), index=True)
    rating: Mapped[float] = mapped_column(Numeric(3, 2), default=5)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    total_trips: Mapped[int] = mapped_column(Integer, default=0)

    city: Mapped["City"] = relationship("City")

class Client(Base):
    __tablename__ = "clients"

    user_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.city_id"), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    total_orders: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    city: Mapped["City"] = relationship("City")

class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tender_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.city_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("clients.user_id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.driver_id"), index=True)
    offset_hours: Mapped[int] = mapped_column(Integer, default=3)
    status_order: Mapped[str] = mapped_column(String(32), index=True)
    status_tender: Mapped[str] = mapped_column(String(32), index=True)
    order_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    tender_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    driverdone_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clientcancel_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    drivercancel_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    order_modified_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_before_accept_local: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    distance_in_meters: Mapped[int] = mapped_column(Integer, default=0)
    duration_in_seconds: Mapped[int] = mapped_column(Integer, default=0)
    price_order_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    price_tender_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    price_start_local: Mapped[float] = mapped_column(Numeric(10, 2), default=0)

    city: Mapped["City"] = relationship("City")
    driver: Mapped["Driver"] = relationship("Driver")
    client: Mapped["Client"] = relationship("Client")

