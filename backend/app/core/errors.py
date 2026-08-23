from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import HTTPException as FastAPIHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_id import REQUEST_ID_HEADER, ensure_request_id


@dataclass(slots=True)
class DomainError(Exception):
    status_code: int
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)


def _sanitize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _sanitize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_sanitize_json_value(item) for item in value]
    return str(value)


def _drop_validation_error_input(errors: Sequence[Any]) -> list[dict[str, Any]]:
    sanitized_errors: list[dict[str, Any]] = []
    for raw_error in errors:
        if not isinstance(raw_error, Mapping):
            sanitized_errors.append({"message": str(raw_error)})
            continue

        sanitized_error: dict[str, Any] = {}
        for key, value in raw_error.items():
            if key == "input":
                continue
            sanitized_error[str(key)] = _sanitize_json_value(value)
        sanitized_errors.append(sanitized_error)
    return sanitized_errors


def _extract_validation_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    try:
        errors_with_hidden_input = cast(Any, exc).errors(include_input=False)
        return _drop_validation_error_input(errors_with_hidden_input)
    except TypeError:
        return _drop_validation_error_input(exc.errors())


def _map_http_status_to_code(status_code: int) -> str:
    if status_code == 401:
        return "UNAUTHENTICATED"
    if status_code == 403:
        return "FORBIDDEN"
    if status_code == 404:
        return "NOT_FOUND"
    return "HTTP_ERROR"


def _safe_http_message(detail: Any) -> str:
    if isinstance(detail, str) and detail:
        return detail
    return "请求处理失败"


def _build_error_response(
    *,
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: Mapping[str, Any] | None = None,
) -> JSONResponse:
    request_id = ensure_request_id(request)
    payload = {
        "code": code,
        "message": message,
        "request_id": request_id,
        "details": _sanitize_json_value(dict(details or {})),
    }
    return JSONResponse(
        status_code=status_code,
        content=payload,
        headers={REQUEST_ID_HEADER: request_id},
    )


async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return _build_error_response(
        request=request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return _build_error_response(
        request=request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="请求参数校验失败",
        details={"errors": _extract_validation_errors(exc)},
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return _build_error_response(
        request=request,
        status_code=exc.status_code,
        code=_map_http_status_to_code(exc.status_code),
        message=_safe_http_message(exc.detail),
        details={},
    )


async def _handle_internal_error(request: Request, exc: Exception) -> JSONResponse:
    return _build_error_response(
        request=request,
        status_code=500,
        code="INTERNAL_ERROR",
        message="服务器内部错误",
        details={},
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _handle_domain_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(FastAPIHTTPException, _handle_http_exception)
    app.add_exception_handler(Exception, _handle_internal_error)
