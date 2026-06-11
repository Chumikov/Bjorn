import socket
import re


class Telnet:
    def __init__(self, host, port=23, timeout=5):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""

    def read_until(self, delimiter, timeout=5):
        self._sock.settimeout(timeout)
        while delimiter not in self._buf:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                self._buf += chunk
            except socket.timeout:
                break
        idx = self._buf.find(delimiter)
        if idx >= 0:
            end = idx + len(delimiter)
            result = self._buf[:end]
            self._buf = self._buf[end:]
            return result
        result = self._buf
        self._buf = b""
        return result

    def write(self, data):
        if self._sock:
            self._sock.sendall(data)

    def expect(self, patterns, timeout=5):
        compiled = [re.compile(re.escape(p)) for p in patterns]
        self._sock.settimeout(timeout)
        while True:
            for i, pat in enumerate(compiled):
                m = pat.search(self._buf)
                if m:
                    end = m.end()
                    result = self._buf[:end]
                    self._buf = self._buf[end:]
                    return (i, m, result)
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    return (-1, None, self._buf)
                self._buf += chunk
            except socket.timeout:
                return (-1, None, self._buf)

    def close(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
