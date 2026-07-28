"""Кастомные исключения."""
import logging

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
"""Кастомные исключения."""
import logging

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
