from __future__ import annotations

from app.utils.db_url import split_ssl_ca_b64_from_url, split_ssl_options_from_url


def test_extracts_ssl_ca_b64_and_removes_it_from_url():
    url = "mysql://u:p@h:3306/db?charset=utf8mb4&ssl_ca_b64=abc123&autocommit=true"
    clean, ca = split_ssl_ca_b64_from_url(url)

    assert ca == "abc123"
    assert "ssl_ca_b64=" not in clean
    assert "charset=utf8mb4" in clean
    assert "autocommit=true" in clean


def test_returns_same_url_when_ssl_ca_b64_missing():
    url = "mysql://u:p@h:3306/db?charset=utf8mb4"
    clean, ca = split_ssl_ca_b64_from_url(url)

    assert clean == url
    assert ca == ""


def test_extracts_ssl_verify_false_and_removes_it_from_url():
    url = "mysql://u:p@h:3306/db?ssl_verify=false&charset=utf8mb4"
    clean, ca, verify = split_ssl_options_from_url(url)

    assert ca == ""
    assert verify is False
    assert "ssl_verify=" not in clean
    assert "charset=utf8mb4" in clean


def test_extracts_ssl_verify_true_and_ssl_ca_b64():
    url = "mysql://u:p@h:3306/db?ssl_ca_b64=abc&ssl_verify=true"
    clean, ca, verify = split_ssl_options_from_url(url)

    assert ca == "abc"
    assert verify is True
    assert "ssl_ca_b64=" not in clean
    assert "ssl_verify=" not in clean
