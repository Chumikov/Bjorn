import ast

import pytest


class TestParamikoPolicy:
    def test_ssh_connector_uses_warning_policy(self):
        with open("actions/ssh_connector.py") as f:
            source = f.read()
        assert "AutoAddPolicy" not in source, "ssh_connector.py still uses AutoAddPolicy"
        assert "WarningPolicy" in source, "ssh_connector.py should use WarningPolicy"

    def test_steal_files_ssh_uses_warning_policy(self):
        with open("actions/steal_files_ssh.py") as f:
            source = f.read()
        assert "AutoAddPolicy" not in source, "steal_files_ssh.py still uses AutoAddPolicy"
        assert "WarningPolicy" in source, "steal_files_ssh.py should use WarningPolicy"

    def test_no_auto_add_policy_in_any_action(self):
        grep_result = []
        for root, dirs, files in os.walk("actions"):
            for fname in files:
                if fname.endswith(".py"):
                    path = os.path.join(root, fname)
                    with open(path) as f:
                        if "AutoAddPolicy" in f.read():
                            grep_result.append(path)
        assert not grep_result, f"AutoAddPolicy found in: {grep_result}"


import os
