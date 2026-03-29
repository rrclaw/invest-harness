"""Unified transport message contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MessageKind(str, Enum):
    APPROVAL = "approval"
    BROADCAST = "broadcast"
    ALERT = "alert"
    REVIEW = "review"


@dataclass(frozen=True)
class TransportMessage:
    """Transport-agnostic message payload."""

    kind: MessageKind
    title: str
    body: str
    market: str | None = None
    target: str | None = None
    level: str | None = None
    hypothesis_ref: str | None = None
    source: str | None = None
    review_date: str | None = None
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    @classmethod
    def approval(
        cls,
        *,
        title: str,
        body: str,
        market: str,
        hypothesis_ref: str,
        target: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> "TransportMessage":
        return cls(
            kind=MessageKind.APPROVAL,
            title=title,
            body=body,
            market=market,
            hypothesis_ref=hypothesis_ref,
            target=target,
            metadata=metadata or {},
        )

    @classmethod
    def broadcast(
        cls,
        *,
        title: str,
        body: str,
        market: str | None = None,
        target: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> "TransportMessage":
        return cls(
            kind=MessageKind.BROADCAST,
            title=title,
            body=body,
            market=market,
            target=target,
            metadata=metadata or {},
        )

    @classmethod
    def alert(
        cls,
        *,
        title: str,
        body: str,
        market: str,
        level: str,
        source: str,
        target: str | None = None,
        hypothesis_ref: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> "TransportMessage":
        return cls(
            kind=MessageKind.ALERT,
            title=title,
            body=body,
            market=market,
            level=level,
            source=source,
            target=target,
            hypothesis_ref=hypothesis_ref,
            metadata=metadata or {},
        )

    @classmethod
    def review(
        cls,
        *,
        title: str,
        body: str,
        review_date: str,
        market: str | None = None,
        target: str | None = None,
        metadata: dict[str, str | int | float | bool | None] | None = None,
    ) -> "TransportMessage":
        return cls(
            kind=MessageKind.REVIEW,
            title=title,
            body=body,
            review_date=review_date,
            market=market,
            target=target,
            metadata=metadata or {},
        )

    def render_text(self) -> str:
        """Render the payload into a transport-ready plain text message."""
        lines = [f"[{self.kind.value.upper()}] {self.title}"]

        if self.level:
            lines.append(f"Level: {self.level}")
        if self.market:
            lines.append(f"Market: {self.market}")
        if self.hypothesis_ref:
            lines.append(f"Hypothesis: {self.hypothesis_ref}")
        if self.review_date:
            lines.append(f"Review Date: {self.review_date}")
        if self.source:
            lines.append(f"Source: {self.source}")

        lines.append("")
        lines.append(self.body)

        if self.metadata:
            lines.append("")
            lines.append("Metadata:")
            for key in sorted(self.metadata):
                lines.append(f"- {key}: {self.metadata[key]}")

        return "\n".join(lines)
