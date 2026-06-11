import os


CONNECTOR_FILES = [
    "actions/ssh_connector.py",
    "actions/ftp_connector.py",
    "actions/smb_connector.py",
    "actions/telnet_connector.py",
    "actions/sql_connector.py",
    "actions/rdp_connector.py",
]


class TestThreadCount:
    def test_connectors_use_max_10_threads(self):
        failures = []
        for path in CONNECTOR_FILES:
            with open(path, encoding="utf-8") as f:
                source = f.read()
            for line_num, line in enumerate(source.splitlines(), 1):
                if "range(40)" in line:
                    failures.append(f"{path}:{line_num}: found range(40)")
        assert not failures, "Connectors should use range(10), not range(40):\n" + "\n".join(failures)

    def test_no_range_40_in_any_action(self):
        for root, _dirs, files in os.walk("actions"):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(root, fname)
                with open(path, encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        assert "range(40)" not in line, f"{path}:{i}: found range(40)"

    def test_scanning_semaphore_is_20(self):
        with open("actions/scanning.py", encoding="utf-8") as f:
            source = f.read()
        assert "Semaphore(200)" not in source, "scanning.py should use Semaphore(20), not Semaphore(200)"
        assert "Semaphore(20)" in source, "scanning.py should use Semaphore(20)"
