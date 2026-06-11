import socket
import threading
import time

import pytest


class FakeTelnetServer:
    def __init__(self):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', 0))
        self.port = self.server.getsockname()[1]
        self.server.listen(1)
        self.thread = None
        self._handler = None

    def start(self, handler):
        self._handler = handler
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.server.accept()
        try:
            self._handler(conn)
        except Exception:
            pass
        finally:
            conn.close()

    def stop(self):
        self.server.close()
        if self.thread:
            self.thread.join(timeout=3)


class TestTelnetShim:
    def _make_shim(self):
        from telnet_shim import Telnet
        return Telnet

    def test_connect_and_read_until(self):
        server = FakeTelnetServer()

        def handler(conn):
            conn.sendall(b"login: ")
            data = conn.recv(1024)
            conn.sendall(b"Password: ")
            data = conn.recv(1024)
            conn.sendall(b"$ ")

        server.start(handler)

        Telnet = self._make_shim()
        tn = Telnet('127.0.0.1', port=server.port)
        result = tn.read_until(b"login: ", timeout=3)
        assert b"login: " in result

        tn.write(b"admin\n")
        result = tn.read_until(b"Password: ", timeout=3)
        assert b"Password: " in result

        tn.write(b"pass\n")
        result = tn.read_until(b"$ ", timeout=3)
        assert b"$ " in result

        tn.close()
        server.stop()

    def test_expect_returns_correct_index(self):
        server = FakeTelnetServer()

        def handler(conn):
            conn.sendall(b"$ ")
            time.sleep(0.1)

        server.start(handler)

        Telnet = self._make_shim()
        tn = Telnet('127.0.0.1', port=server.port)

        result = tn.expect([b"Login incorrect", b"Password: ", b"$ ", b"# "], timeout=3)
        assert result[0] == 2, f"Expected index 2 for '$ ', got {result[0]}"
        assert b"$ " in result[2]

        tn.close()
        server.stop()

    def test_expect_login_incorrect(self):
        server = FakeTelnetServer()

        def handler(conn):
            conn.sendall(b"Login incorrect\n")
            time.sleep(0.1)

        server.start(handler)

        Telnet = self._make_shim()
        tn = Telnet('127.0.0.1', port=server.port)

        result = tn.expect([b"Login incorrect", b"Password: ", b"$ ", b"# "], timeout=3)
        assert result[0] == 0, f"Expected index 0 for 'Login incorrect', got {result[0]}"

        tn.close()
        server.stop()

    def test_close_is_idempotent(self):
        server = FakeTelnetServer()

        def handler(conn):
            time.sleep(2)

        server.start(handler)

        Telnet = self._make_shim()
        tn = Telnet('127.0.0.1', port=server.port)
        tn.close()
        tn.close()  # should not raise

        server.stop()

    def test_connection_refused_raises(self):
        Telnet = self._make_shim()
        with pytest.raises(Exception):
            Telnet('127.0.0.1', port=1)

    def test_telnet_connector_uses_shim_not_telnetlib(self):
        import ast
        with open("actions/telnet_connector.py") as f:
            tree = ast.parse(f.read())
        imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
        from_imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        all_imports = imports + from_imports
        assert "telnetlib" not in all_imports, "telnet_connector.py still imports telnetlib"
        assert "telnet_shim" in all_imports, "telnet_connector.py should import telnet_shim"

    def test_steal_files_telnet_uses_shim_not_telnetlib(self):
        import ast
        with open("actions/steal_files_telnet.py") as f:
            tree = ast.parse(f.read())
        imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
        from_imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        all_imports = imports + from_imports
        assert "telnetlib" not in all_imports, "steal_files_telnet.py still imports telnetlib"
        assert "telnet_shim" in all_imports, "steal_files_telnet.py should import telnet_shim"
