import httpx

from app.main import create_app


def _resolve_internal_ref(schema: dict[str, object], reference: str) -> object:
    assert reference.startswith("#/")
    resolved: object = schema
    for segment in reference.removeprefix("#/").split("/"):
        assert isinstance(resolved, dict)
        assert segment in resolved, f"无法解析内部引用: {reference}"
        resolved = resolved[segment]
    return resolved


def _assert_internal_refs_resolve(value: object, schema: dict[str, object]) -> None:
    if isinstance(value, dict):
        reference = value.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/"):
            _resolve_internal_ref(schema, reference)
        for nested_value in value.values():
            _assert_internal_refs_resolve(nested_value, schema)
    elif isinstance(value, list):
        for nested_value in value:
            _assert_internal_refs_resolve(nested_value, schema)


async def test_health_returns_ok_status() -> None:
    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_project_openapi_declares_request_body_schema() -> None:
    schema = create_app().openapi()

    operation = schema["paths"]["/api/v1/projects"]["post"]
    request_body = operation["requestBody"]
    body_schema = request_body["content"]["application/json"]["schema"]

    assert request_body["required"] is True
    assert body_schema == {"$ref": "#/components/schemas/CreateProjectRequest"}
    assert set(schema["components"]["schemas"]["CreateProjectRequest"]["required"]) == {
        "project_name",
        "procurement_method",
        "regime_type",
        "deadline_at",
        "owner_user_id",
    }


def test_openapi_internal_references_are_resolvable() -> None:
    schema = create_app().openapi()

    assert "$defs" not in schema["components"]["schemas"]["CreateProjectRequest"]
    _assert_internal_refs_resolve(schema, schema)


def test_create_project_openapi_declares_required_headers() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/projects"]["post"]

    parameters = operation.get("parameters") or []
    headers = {
        parameter["name"]: parameter for parameter in parameters if parameter.get("in") == "header"
    }

    assert set(headers) == {"Idempotency-Key", "X-CSRF-Token"}
    assert headers["Idempotency-Key"]["required"] is True
    assert headers["X-CSRF-Token"]["required"] is True


def test_create_project_openapi_declares_session_and_csrf_security() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/projects"]["post"]

    security_schemes = schema["components"]["securitySchemes"]
    assert security_schemes["sessionCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "bid_session",
    }
    assert security_schemes["csrfToken"] == {
        "type": "apiKey",
        "in": "header",
        "name": "X-CSRF-Token",
    }
    assert operation["security"] == [{"sessionCookie": [], "csrfToken": []}]


def test_create_project_openapi_declares_unified_error_responses() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/projects"]["post"]

    responses = operation["responses"]
    for status_code in ("400", "401", "403", "409", "422", "500"):
        assert status_code in responses, f"缺少错误响应 {status_code}"
        content = responses[status_code]["content"]["application/json"]["schema"]
        assert content == {"$ref": "#/components/schemas/ErrorResponse"}

    error_schema = schema["components"]["schemas"]["ErrorResponse"]
    assert set(error_schema["required"]) == {"code", "message", "request_id", "details"}
    assert set(error_schema["properties"]) == {"code", "message", "request_id", "details"}


EXPECTED_OPERATIONS = {
    ("post", "/api/v1/auth/login"),
    ("get", "/api/v1/auth/session"),
    ("post", "/api/v1/auth/logout"),
    ("post", "/api/v1/auth/password/change"),
    ("get", "/api/v1/me/workbench"),
    ("get", "/api/v1/projects"),
    ("post", "/api/v1/projects"),
    ("get", "/api/v1/projects/{project_id}/overview"),
}


def test_openapi_contains_exact_first_slice_operations() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    actual = {(method, path) for path, methods in paths.items() for method in methods}
    assert EXPECTED_OPERATIONS <= actual


def test_create_project_schema_excludes_source_fields() -> None:
    schema = create_app().openapi()
    properties = schema["components"]["schemas"]["CreateProjectRequest"]["properties"]
    assert "project_source" not in properties
    assert "external_project_code" not in properties
