"""Deterministic baseline safe-zone validation shared by master/delivery flows.

This is a layout-integrity baseline, not a claim of platform UI certification.
Vendor-specific overlays can be added later as evidence-backed profiles.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SafeZoneProfile:
    profile_id: str
    inner_fraction: float = 0.90
    reserved_top_fraction: float = 0.0
    reserved_bottom_fraction: float = 0.0

    def bounds(self, width: int, height: int) -> tuple[float, float, float, float]:
        if not 0.0 < self.inner_fraction <= 1.0:
            raise ValueError("inner_fraction must be in (0,1]")
        left = width * (1.0 - self.inner_fraction) / 2.0
        right = width - left
        top = height * (1.0 - self.inner_fraction) / 2.0 + height * self.reserved_top_fraction
        bottom = height * (1.0 + self.inner_fraction) / 2.0 - height * self.reserved_bottom_fraction
        return left, top, right, bottom


@dataclass(frozen=True)
class LayoutBox:
    box_id: str
    left: float
    top: float
    right: float
    bottom: float

    def validate(self, width: int, height: int, safe: SafeZoneProfile) -> list[str]:
        x0, y0, x1, y1 = safe.bounds(width, height)
        errors: list[str] = []
        if self.left < x0:
            errors.append(f"{self.box_id}: left {self.left:.1f} < safe {x0:.1f}")
        if self.top < y0:
            errors.append(f"{self.box_id}: top {self.top:.1f} < safe {y0:.1f}")
        if self.right > x1:
            errors.append(f"{self.box_id}: right {self.right:.1f} > safe {x1:.1f}")
        if self.bottom > y1:
            errors.append(f"{self.box_id}: bottom {self.bottom:.1f} > safe {y1:.1f}")
        if self.right <= self.left or self.bottom <= self.top:
            errors.append(f"{self.box_id}: invalid geometry")
        return errors


BASELINE_SAFE_ZONE = SafeZoneProfile(
    profile_id="hvs_inner_90_baseline",
    inner_fraction=0.90,
)


def validate_layout(
    *,
    width: int,
    height: int,
    boxes: tuple[LayoutBox, ...],
    profile: SafeZoneProfile = BASELINE_SAFE_ZONE,
) -> tuple[str, ...]:
    errors: list[str] = []
    for box in boxes:
        errors.extend(box.validate(width, height, profile))
    return tuple(errors)
