import socket
import select
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SSHTunnel:
    def __init__(self, ssh_host: str, ssh_port: int, ssh_username: str,
                 remote_host: str, remote_port: int,
                 ssh_password: str = None, ssh_pkey=None):
        self._ssh_host = ssh_host
        self._ssh_port = ssh_port
        self._ssh_username = ssh_username
        self._ssh_password = ssh_password
        self._ssh_pkey = ssh_pkey
        self._remote_host = remote_host
        self._remote_port = remote_port

        self._transport = None
        self._client = None
        self._server_socket = None
        self._local_port: Optional[int] = None
        self._running = False
        self._accept_thread: Optional[threading.Thread] = None
        self._forward_threads = []

    def start(self):
        import paramiko

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self._ssh_host,
            "port": self._ssh_port,
            "username": self._ssh_username,
            "timeout": 15,
            "allow_agent": False,
            "look_for_keys": False,
        }
        if self._ssh_pkey is not None:
            connect_kwargs["pkey"] = self._ssh_pkey
        elif self._ssh_password:
            connect_kwargs["password"] = self._ssh_password
        else:
            connect_kwargs["allow_agent"] = True
            connect_kwargs["look_for_keys"] = True

        self._client.connect(**connect_kwargs)
        self._transport = self._client.get_transport()
        if self._transport is None:
            raise RuntimeError("无法获取 SSH Transport")

        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(("127.0.0.1", 0))
        self._local_port = self._server_socket.getsockname()[1]
        self._server_socket.listen(5)
        self._server_socket.settimeout(1.0)

        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._accept_thread.start()

        logger.info(
            f"SSH隧道已建立: {self._ssh_host}:{self._ssh_port} -> "
            f"{self._remote_host}:{self._remote_port} (local_port={self._local_port})"
        )

    def _accept_loop(self):
        while self._running:
            try:
                client_sock, _ = self._server_socket.accept()
                t = threading.Thread(target=self._forward, args=(client_sock,), daemon=True)
                t.start()
                self._forward_threads.append(t)
            except socket.timeout:
                continue
            except OSError:
                break

    def _forward(self, client_sock: socket.socket):
        try:
            channel = self._transport.open_channel(
                "direct-tcpip",
                (self._remote_host, self._remote_port),
                client_sock.getpeername(),
            )
        except Exception as e:
            logger.debug(f"SSH通道打开失败: {e}")
            try:
                client_sock.close()
            except Exception:
                pass
            return

        if channel is None:
            try:
                client_sock.close()
            except Exception:
                pass
            return

        try:
            while self._running:
                r, _, _ = select.select([client_sock, channel], [], [], 1.0)
                if not r:
                    if not self._running:
                        break
                    continue
                if client_sock in r:
                    data = client_sock.recv(65536)
                    if not data:
                        break
                    channel.sendall(data)
                if channel in r:
                    data = channel.recv(65536)
                    if not data:
                        break
                    client_sock.sendall(data)
        except Exception:
            pass
        finally:
            try:
                channel.close()
            except Exception:
                pass
            try:
                client_sock.close()
            except Exception:
                pass

    @property
    def local_bind_port(self) -> int:
        return self._local_port

    def stop(self):
        self._running = False
        if self._server_socket is not None:
            try:
                self._server_socket.close()
            except Exception:
                pass
            self._server_socket = None
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self._local_port = None
        logger.info("SSH隧道已关闭")

    def is_active(self) -> bool:
        if self._transport is None:
            return False
        return self._transport.is_active()
