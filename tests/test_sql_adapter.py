"""Tests for SQL adapter URL normalization and safety guards."""

from __future__ import annotations

import pytest

from app.services.adapters.sql_adapter import SQLAdapter


class TestSQLAdapterNormalization:
    def test_mysql_url_is_normalized_to_pymysql(self):
        normalized = SQLAdapter._normalize_db_url("mysql://user:pass@localhost:3306/testdb")
        assert normalized.startswith("mysql+pymysql://")

    def test_mysql_mysqldb_url_is_normalized_to_pymysql(self):
        normalized = SQLAdapter._normalize_db_url(
            "mysql+mysqldb://user:pass@localhost:3306/testdb"
        )
        assert normalized.startswith("mysql+pymysql://")

    def test_existing_mysql_pymysql_url_is_preserved(self):
        original = "mysql+pymysql://user:pass@localhost:3306/testdb"
        normalized = SQLAdapter._normalize_db_url(original)
        assert normalized.startswith("mysql+pymysql://")


class TestSQLAdapterReadOnlyGuard:
    def test_blocks_stacked_statements(self):
        assert SQLAdapter._is_read_only("SELECT 1; DROP TABLE users") is False

    def test_allows_show_tables(self):
        assert SQLAdapter._is_read_only("SHOW TABLES;") is True

    def test_blocks_write_statement(self):
        assert SQLAdapter._is_read_only("DELETE FROM users") is False


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM users",
        "SHOW TABLES;",
        "DESCRIBE users",
    ],
)
def test_read_only_queries_allowed(query: str):
    assert SQLAdapter._is_read_only(query) is True
