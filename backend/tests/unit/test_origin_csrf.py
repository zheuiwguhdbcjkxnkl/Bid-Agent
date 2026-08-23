from __future__ import annotations

import secrets

import pytest

from app.core.csrf import assert_csrf_valid, generate_csrf_token
from app.core.errors import DomainError
from app.core.origin import assert_request_origin_allowed


class TestOriginValidation:
    def test_allows_origin_when_in_allowlist(self) -> None:
        assert_request_origin_allowed(
            origin="https://Example.COM:443",
            referer="https://evil.example/path?q=1",
            allowed_origins=["https://example.com"],
        )

    def test_uses_origin_before_referer_and_rejects_invalid_origin_even_if_referer_allowed(
        self,
    ) -> None:
        with pytest.raises(DomainError) as exc_info:
            assert_request_origin_allowed(
                origin="https://evil.example",
                referer="https://trusted.example/path",
                allowed_origins=["https://trusted.example"],
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "ORIGIN_NOT_ALLOWED"
        assert exc_info.value.message == "请求来源不受信任"

    def test_falls_back_to_referer_when_origin_missing(self) -> None:
        assert_request_origin_allowed(
            origin=None,
            referer="https://Trusted.Example:443/path?query=1#fragment",
            allowed_origins=["https://trusted.example"],
        )

    @pytest.mark.parametrize(
        ("origin", "referer"),
        [
            (None, None),
            ("   ", None),
            (None, "notaurl"),
            ("https://user:pass@example.com", None),
            ("https://example.com/path", None),
            ("ftp://example.com", None),
        ],
    )
    def test_rejects_missing_or_invalid_request_source(
        self,
        origin: str | None,
        referer: str | None,
    ) -> None:
        with pytest.raises(DomainError) as exc_info:
            assert_request_origin_allowed(
                origin=origin,
                referer=referer,
                allowed_origins=["https://example.com"],
            )

        assert exc_info.value.code == "ORIGIN_NOT_ALLOWED"

    def test_allows_ipv6_origin_with_explicit_port(self) -> None:
        assert_request_origin_allowed(
            origin="https://[2001:db8::1]:8443",
            referer=None,
            allowed_origins=["https://[2001:db8::1]:8443"],
        )

    def test_rejects_ipv6_origin_that_collides_with_host_and_port_string(self) -> None:
        with pytest.raises(DomainError) as exc_info:
            assert_request_origin_allowed(
                origin="https://[2001:db8::1:8443]",
                referer=None,
                allowed_origins=["https://[2001:db8::1]:8443"],
            )

        assert exc_info.value.code == "ORIGIN_NOT_ALLOWED"

    def test_treats_ipv6_default_https_port_as_same_origin(self) -> None:
        assert_request_origin_allowed(
            origin="https://[2001:db8::1]:443",
            referer=None,
            allowed_origins=["https://[2001:db8::1]"],
        )

    def test_rejects_invalid_allowed_origin_configuration(self) -> None:
        with pytest.raises(ValueError):
            assert_request_origin_allowed(
                origin="https://example.com",
                referer=None,
                allowed_origins=["https://example.com/path"],
            )


class TestCsrfValidation:
    def test_generate_csrf_token_returns_random_urlsafe_token(self) -> None:
        first_token = generate_csrf_token()
        second_token = generate_csrf_token()

        assert first_token != second_token
        assert len(first_token) >= 43
        assert len(second_token) >= 43
        assert secrets.compare_digest(first_token, first_token) is True

    @pytest.mark.parametrize(
        ("cookie_token", "header_token"),
        [
            (None, "token"),
            ("token", None),
            ("", "token"),
            ("token", ""),
            ("   ", "token"),
            ("token", "   "),
            ("token-a", "token-b"),
            ("token", " token"),
            ("token", "token "),
        ],
    )
    def test_rejects_missing_blank_or_mismatched_tokens(
        self,
        cookie_token: str | None,
        header_token: str | None,
    ) -> None:
        with pytest.raises(DomainError) as exc_info:
            assert_csrf_valid(cookie_token, header_token)

        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "CSRF_VALIDATION_FAILED"
        assert exc_info.value.message == "CSRF 校验失败"

    def test_accepts_exactly_matching_tokens(self) -> None:
        token = generate_csrf_token()

        assert_csrf_valid(token, token)
