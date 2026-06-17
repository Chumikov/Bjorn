import sys
from unittest.mock import MagicMock, patch

import pytest


class TestStealDataSqlParentAction:
    def test_b_parent_action_is_not_a_method_on_instance(self, mock_shared_data):
        sys.modules.pop('actions.steal_data_sql', None)
        from actions.steal_data_sql import StealDataSQL
        instance = StealDataSQL(mock_shared_data)

        assert not hasattr(instance, 'b_parent_action') or \
               not callable(getattr(instance, 'b_parent_action', None)), \
            "b_parent_action should not be a callable method on the instance"

    def test_b_parent_action_dead_method_has_undefined_names(self):
        import ast
        with open("actions/steal_data_sql.py") as f:
            source = f.read()

        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "b_parent_action":
                for child in ast.walk(node):
                    if isinstance(child, ast.Name) and child.id in ("b_parent", "b_status"):
                        pytest.fail(
                            f"Dead method b_parent_action references undefined global "
                            f"'{child.id}' at line {child.lineno}. "
                            f"This method is shadowed by the instance attribute set by orchestrator."
                        )
                break

    def test_execute_does_not_crash_with_string_parent_action(self, mock_shared_data):
        sys.modules.pop('actions.steal_data_sql', None)
        from actions.steal_data_sql import StealDataSQL
        instance = StealDataSQL(mock_shared_data)
        instance.b_parent_action = "SQLBruteforce"

        row = {"SQLBruteforce": "success", "IPs": "10.0.0.1"}

        with MagicMock() as mock_shared:
            instance.shared_data = mock_shared
            mock_shared.sqlfile = "/nonexistent"
            mock_shared.bjornorch_status = ""
            result = instance.execute("10.0.0.1", 3306, row, "steal_data_sql")

        assert result is not None


# ---------------------------------------------------------------------------
# SQL-1: URL-encode credentials
# ---------------------------------------------------------------------------


class TestSqlCredentialsUrlEncoded:
    """SQL-1: passwords containing @, :, /, etc. must not break the URL."""

    def test_url_create_used(self):
        """Source: connect_sql must use URL.create."""
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            src = f.read()
        assert "URL.create(" in src, (
            "connect_sql must use URL.create() (SQL-1).")
        # The old buggy f-string must be gone
        assert "mysql+pymysql://{username}:{password}@" not in src, (
            "connect_sql still uses raw f-string URL interpolation (SQL-1).")

    def test_url_create_imported(self):
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            src = f.read()
        assert "from sqlalchemy.engine import URL" in src or \
               "from sqlalchemy import URL" in src or \
               "from sqlalchemy import create_engine, URL" in src, \
               "URL must be imported from sqlalchemy."

    @pytest.mark.parametrize("password,description", [
        ("P@ssw0rd", "at-sign"),
        ("pa:ssword", "colon"),
        ("pass.word/with-slash", "slash"),
        ("P@ss:w0rd/with-all!", "all-special"),
        ("normal_password", "no-special"),
    ])
    def test_connect_sql_passes_password_verbatim(self, mock_shared_data,
                                                   password, description):
        """The create_engine call must receive a URL whose password attribute
        equals the raw password (URL.create handles the encoding)."""
        sys.modules.pop("actions.steal_data_sql", None)
        from actions import steal_data_sql as sql_mod

        instance = sql_mod.StealDataSQL(mock_shared_data)
        with patch.object(sql_mod, "create_engine") as mock_ce:
            mock_ce.return_value = MagicMock()
            instance.connect_sql("10.0.0.1", "user", password)

            assert mock_ce.called, "create_engine was not called"
            url_arg = mock_ce.call_args[0][0]
            # URL.render_as_string reveals the encoded form, but URL.password
            # gives back the raw value.
            assert url_arg.password == password, (
                f"Password with {description} ({password!r}) not preserved: "
                f"got {url_arg.password!r}")


# ---------------------------------------------------------------------------
# SQL-2: dispose engines
# ---------------------------------------------------------------------------


class TestSqlEnginesDisposed:
    def test_dispose_called_in_source(self):
        """Source-level: steal_data_sql.py must call engine.dispose()."""
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            src = f.read()
        assert ".dispose()" in src, (
            "steal_data_sql.py must call .dispose() on engines (SQL-2).")

    def test_dispose_in_finally_block(self):
        """Source-level: dispose must be inside a finally block."""
        import ast
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        # Walk the AST and find any .dispose() call; assert at least one
        # is inside a Try handler's finalbody.
        found_dispose_in_finally = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Try):
                for stmt in node.finalbody:
                    for sub in ast.walk(stmt):
                        if (isinstance(sub, ast.Call)
                                and isinstance(sub.func, ast.Attribute)
                                and sub.func.attr == "dispose"):
                            found_dispose_in_finally = True
                            break
        assert found_dispose_in_finally, (
            "engine.dispose() must be called in a finally block (SQL-2) so "
            "engines are released on both success and exception paths.")


# ---------------------------------------------------------------------------
# SQL-3: backtick-quote table/schema
# ---------------------------------------------------------------------------


class TestSqlIdentifiersQuoted:
    def test_backtick_quote_pattern(self):
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            src = f.read()
        # The query must use backticks around {schema} and {table}
        assert "`{schema}`.`{table}`" in src, (
            "steal_data must backtick-quote schema and table (SQL-3).")
        # The old unquoted form must be gone
        assert "SELECT * FROM {schema}.{table}" not in src, (
            "steal_data still uses unquoted identifiers (SQL-3).")


# ---------------------------------------------------------------------------
# SQL-4: wrap raw SQL in text()
# ---------------------------------------------------------------------------


class TestSqlTextUsed:
    def test_text_imported(self):
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            src = f.read()
        assert "text" in src, (
            "steal_data_sql.py must import text from sqlalchemy (SQL-4).")

    def test_text_wraps_find_tables_query(self):
        from inspect import getsource
        sys.modules.pop("actions.steal_data_sql", None)
        from actions.steal_data_sql import StealDataSQL
        src = getsource(StealDataSQL.find_tables)
        assert "text(" in src, (
            "find_tables must wrap its raw SQL string in text() (SQL-4).")

    def test_text_wraps_steal_data_query(self):
        from inspect import getsource
        sys.modules.pop("actions.steal_data_sql", None)
        from actions.steal_data_sql import StealDataSQL
        src = getsource(StealDataSQL.steal_data)
        assert "text(" in src, (
            "steal_data must wrap its raw SQL string in text() (SQL-4).")


# ---------------------------------------------------------------------------
# SQL-5: remove unused Console import
# ---------------------------------------------------------------------------


class TestNoDeadConsoleImport:
    def test_no_console_import(self):
        with open("actions/steal_data_sql.py", encoding="utf-8") as f:
            src = f.read()
        assert "from rich.console import Console" not in src, (
            "steal_data_sql.py must not import Console (SQL-5).")
        assert "Console(" not in src, (
            "steal_data_sql.py must not instantiate Console (SQL-5).")

