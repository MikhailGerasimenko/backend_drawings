"""Базовые схемы ответов API."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str


class AppErrorResponse(BaseModel):
    error: ErrorResponse
