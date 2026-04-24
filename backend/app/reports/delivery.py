from __future__ import annotations

import asyncio
import mimetypes
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

import httpx

from app.config import get_settings
from app.reports.artifacts import BuiltArtifact
from app.reports.errors import DeliveryConfigurationError, DeliveryTransportError

settings = get_settings()


@dataclass(frozen=True)
class DeliveryPayload:
    report_title: str
    destination: str
    channel: str
    run_status: str
    rows_returned: int
    execution_ms: int
    artifacts: list[BuiltArtifact]
    summary_text: str


@dataclass(frozen=True)
class DeliveryResult:
    adapter_key: str
    external_message_id: str
    details: dict


class DeliveryAdapter(Protocol):
    adapter_key: str

    async def send(self, payload: DeliveryPayload) -> DeliveryResult:
        ...


class SmtpEmailDeliveryAdapter:
    adapter_key = "smtp_email"

    def _build_message(self, payload: DeliveryPayload) -> EmailMessage:
        if not settings.report_smtp_host:
            raise DeliveryConfigurationError("SMTP host is not configured for email delivery.")

        message = EmailMessage()
        message["From"] = settings.report_email_from
        message["To"] = payload.destination
        message["Subject"] = f"[Tolmach] {payload.report_title}"
        message.set_content(
            "\n".join(
                [
                    f"Report: {payload.report_title}",
                    f"Status: {payload.run_status}",
                    f"Rows returned: {payload.rows_returned}",
                    f"Execution ms: {payload.execution_ms}",
                    "",
                    payload.summary_text,
                ]
            )
        )
        for artifact in payload.artifacts:
            artifact_path = Path(artifact.file_path)
            mime_type, _ = mimetypes.guess_type(str(artifact_path))
            maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
            message.add_attachment(
                artifact_path.read_bytes(),
                maintype=maintype,
                subtype=subtype,
                filename=artifact.file_name,
            )
        return message

    def _send_sync(self, payload: DeliveryPayload) -> DeliveryResult:
        message = self._build_message(payload)
        if settings.report_smtp_use_ssl:
            smtp = smtplib.SMTP_SSL(settings.report_smtp_host, settings.report_smtp_port, timeout=settings.report_delivery_timeout_seconds)
        else:
            smtp = smtplib.SMTP(settings.report_smtp_host, settings.report_smtp_port, timeout=settings.report_delivery_timeout_seconds)
        try:
            smtp.ehlo()
            if settings.report_smtp_use_tls and not settings.report_smtp_use_ssl:
                smtp.starttls()
                smtp.ehlo()
            if settings.report_smtp_username:
                smtp.login(settings.report_smtp_username, settings.report_smtp_password)
            smtp.send_message(message)
        except smtplib.SMTPException as exc:
            raise DeliveryTransportError("SMTP delivery failed.", details={"destination": payload.destination}) from exc
        finally:
            try:
                smtp.quit()
            except Exception:
                pass
        return DeliveryResult(adapter_key=self.adapter_key, external_message_id="", details={"destination": payload.destination})

    async def send(self, payload: DeliveryPayload) -> DeliveryResult:
        return await asyncio.to_thread(self._send_sync, payload)


class SlackWebhookDeliveryAdapter:
    adapter_key = "slack_webhook"

    async def send(self, payload: DeliveryPayload) -> DeliveryResult:
        if not settings.report_slack_webhook_url:
            raise DeliveryConfigurationError("Slack webhook URL is not configured.")

        artifact_lines = [f"- {item.file_name}: {item.file_path}" for item in payload.artifacts]
        body = {
            "text": f"Tolmach report: {payload.report_title}",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(
                            [
                                f"*Report*: {payload.report_title}",
                                f"*Status*: {payload.run_status}",
                                f"*Rows*: {payload.rows_returned}",
                                f"*Execution*: {payload.execution_ms} ms",
                                f"*Summary*: {payload.summary_text or 'No summary available'}",
                            ]
                        ),
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Artifacts*\n" + ("\n".join(artifact_lines) if artifact_lines else "No artifacts"),
                    },
                },
            ],
        }
        timeout = httpx.Timeout(settings.report_delivery_timeout_seconds)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(settings.report_slack_webhook_url, json=body)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DeliveryTransportError("Slack delivery failed.", details={"destination": payload.destination}) from exc
        return DeliveryResult(adapter_key=self.adapter_key, external_message_id="", details={"destination": payload.destination})


def get_delivery_adapter(channel: str) -> DeliveryAdapter:
    normalized = channel.strip().lower()
    if normalized == "email":
        return SmtpEmailDeliveryAdapter()
    if normalized == "slack":
        return SlackWebhookDeliveryAdapter()
    raise DeliveryConfigurationError(f"Unsupported delivery channel: {channel}")
