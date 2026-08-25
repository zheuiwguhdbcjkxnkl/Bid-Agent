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


def test_openapi_declares_project_member_operations() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]
    expected_paths = {
        "/api/v1/projects/{project_id}/members": {"get", "post"},
        "/api/v1/projects/{project_id}/members/{user_id}": {"patch", "delete"},
    }

    for path, methods in expected_paths.items():
        assert path in paths
        assert methods <= set(paths[path])


def test_project_member_openapi_declares_typed_bodies_required_headers_and_errors() -> None:
    schema = create_app().openapi()
    member_path = "/api/v1/projects/{project_id}/members"
    member_item_path = "/api/v1/projects/{project_id}/members/{user_id}"

    post_operation = schema["paths"][member_path]["post"]
    post_body = post_operation["requestBody"]
    assert post_body["required"] is True
    assert post_body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AddMemberRequest"
    }
    post_headers = {
        parameter["name"]: parameter
        for parameter in post_operation["parameters"]
        if parameter.get("in") == "header"
    }
    post_path_parameters = {
        parameter["name"]: parameter
        for parameter in post_operation["parameters"]
        if parameter.get("in") == "path"
    }
    assert post_path_parameters["project_id"]["required"] is True
    assert post_headers["Idempotency-Key"]["required"] is True
    assert post_headers["X-CSRF-Token"]["required"] is True

    patch_operation = schema["paths"][member_item_path]["patch"]
    patch_body = patch_operation["requestBody"]
    assert patch_body["required"] is True
    assert patch_body["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/UpdateMemberRoleRequest"
    }
    for operation in (
        schema["paths"][member_path]["get"],
        post_operation,
        patch_operation,
        schema["paths"][member_item_path]["delete"],
    ):
        headers = {
            parameter["name"]: parameter
            for parameter in operation["parameters"]
            if parameter.get("in") == "header"
        }
        if operation is not schema["paths"][member_path]["get"]:
            assert headers["X-CSRF-Token"]["required"] is True
        for status_code in ("400", "401", "403", "404", "409", "422", "500"):
            assert status_code in operation["responses"], f"缺少错误响应 {status_code}"
            assert operation["responses"][status_code]["content"]["application/json"]["schema"] == {
                "$ref": "#/components/schemas/ErrorResponse"
            }

    assert post_operation["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MemberItem"
    }
    assert patch_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MemberItem"
    }
    assert schema["paths"][member_item_path]["delete"]["responses"]["204"] == {
        "description": "Successful Response"
    }


def test_create_project_schema_excludes_source_fields() -> None:
    schema = create_app().openapi()
    properties = schema["components"]["schemas"]["CreateProjectRequest"]["properties"]
    assert "project_source" not in properties
    assert "external_project_code" not in properties


def test_project_document_openapi_declares_multipart_headers_path_and_errors() -> None:
    schema = create_app().openapi()
    path = "/api/v1/projects/{project_id}/documents"
    assert path in schema["paths"]
    operation = schema["paths"][path]["post"]
    request_body = operation["requestBody"]
    assert request_body["required"] is True
    assert "multipart/form-data" in request_body["content"]
    multipart_schema = request_body["content"]["multipart/form-data"]["schema"]
    if "$ref" in multipart_schema:
        multipart_schema = _resolve_internal_ref(schema, multipart_schema["$ref"])
    assert isinstance(multipart_schema, dict)
    assert set(multipart_schema["required"]) == {"file", "document_type", "display_name"}
    parameters = operation["parameters"]
    assert any(
        parameter["name"] == "project_id"
        and parameter["in"] == "path"
        and parameter["required"] is True
        for parameter in parameters
    )
    headers = {
        parameter["name"]: parameter for parameter in parameters if parameter["in"] == "header"
    }
    assert headers["Idempotency-Key"]["required"] is True
    assert headers["X-CSRF-Token"]["required"] is True
    assert operation["security"] == [{"sessionCookie": [], "csrfToken": []}]
    for status_code in ("400", "401", "403", "404", "409", "422", "500"):
        assert operation["responses"][status_code]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }


def test_project_document_openapi_declares_list_operation() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/projects/{project_id}/documents"]["get"]
    assert operation["security"] == [{"sessionCookie": []}]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/DocumentListResponse"
    }


def test_document_parse_openapi_declares_start_operation_contract() -> None:
    schema = create_app().openapi()
    path = "/api/v1/document-versions/{document_version_id}/parse"
    operation = schema["paths"][path]["post"]

    assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/StartDocumentParseResponse"
    }
    headers = {
        parameter["name"]: parameter
        for parameter in operation["parameters"]
        if parameter.get("in") == "header"
    }
    assert headers["Idempotency-Key"]["required"] is True
    assert headers["X-CSRF-Token"]["required"] is True
    assert operation["security"] == [{"sessionCookie": [], "csrfToken": []}]


def test_task_run_openapi_declares_single_and_project_list_operations() -> None:
    schema = create_app().openapi()
    paths = schema["paths"]

    assert paths["/api/v1/task-runs/{task_run_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/TaskRunItem"}
    assert paths["/api/v1/projects/{project_id}/task-runs"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/TaskRunListResponse"}
    assert paths["/api/v1/task-runs/{task_run_id}"]["get"]["security"] == [{"sessionCookie": []}]
    assert paths["/api/v1/projects/{project_id}/task-runs"]["get"]["security"] == [
        {"sessionCookie": []}
    ]
