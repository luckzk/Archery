from __future__ import annotations

import select
import socket
import socketserver
import threading
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

import socks


PROXY_TYPES = {
    "http": socks.HTTP,
    "socks4": socks.SOCKS4,
    "socks5": socks.SOCKS5,
}


class ProxyForwardServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        target_host: str,
        target_port: int,
        proxy_type: str,
        proxy_host: str,
        proxy_port: int,
        proxy_username: Optional[str],
        proxy_password: Optional[str],
    ) -> None:
        super().__init__(server_address, ProxyForwardHandler)
        self.target_host = target_host
        self.target_port = target_port
        self.proxy_type = proxy_type
        self.proxy_host = proxy_host
        self.proxy_port = proxy_port
        self.proxy_username = proxy_username
        self.proxy_password = proxy_password

    def open_upstream(self) -> socks.socksocket:
        upstream = socks.socksocket()
        upstream.set_proxy(
            proxy_type=PROXY_TYPES[self.proxy_type],
            addr=self.proxy_host,
            port=self.proxy_port,
            username=self.proxy_username,
            password=self.proxy_password,
        )
        upstream.settimeout(15)
        upstream.connect((self.target_host, self.target_port))
        upstream.settimeout(None)
        return upstream


class ProxyForwardHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        upstream = self.server.open_upstream()
        sockets = [self.request, upstream]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 60)
                if errored:
                    break
                if not readable:
                    continue
                for sock in readable:
                    data = sock.recv(65536)
                    if not data:
                        return
                    target = upstream if sock is self.request else self.request
                    target.sendall(data)
        finally:
            upstream.close()


@contextmanager
def proxy_tunnel(
    target_host: str,
    target_port: int,
    proxy_type: str,
    proxy_host: str,
    proxy_port: int,
    proxy_username: Optional[str] = None,
    proxy_password: Optional[str] = None,
) -> Iterator[Tuple[str, int]]:
    if proxy_type not in PROXY_TYPES:
        raise ValueError(f"Unsupported proxy type: {proxy_type}")

    server = ProxyForwardServer(
        ("127.0.0.1", 0),
        target_host,
        target_port,
        proxy_type,
        proxy_host,
        proxy_port,
        proxy_username,
        proxy_password,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield server.server_address
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
