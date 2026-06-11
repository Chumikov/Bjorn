import sys
from unittest.mock import MagicMock

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
