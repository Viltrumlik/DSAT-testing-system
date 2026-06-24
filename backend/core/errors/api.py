from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppError(Exception):
    detail: str
    code: str | None = None
    status_code: int = 400
    context_id: str | None = None


class BadRequest(AppError):
    status_code = 400


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409

