import logging
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from typing import Optional, Dict, Any, List
from core.nacos_config import load_connections as nacos_load, save_connections as nacos_save
from core.ssh_tunnel import SSHTunnel

logger = logging.getLogger(__name__)


class DatabaseConnection:
    def __init__(self, name: str, db_type: str, host: str = "", port: int = 0,
                 username: str = "", password: str = "", database: str = "",
                 file_path: str = "",
                 ssh_enabled: bool = False, ssh_host: str = "", ssh_port: int = 22,
                 ssh_username: str = "", ssh_password: str = "",
                 ssh_key_file: str = "", ssh_key_password: str = ""):
        self.name = name
        self.db_type = db_type
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.database = database
        self.file_path = file_path
        self.ssh_enabled = ssh_enabled
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.ssh_key_file = ssh_key_file
        self.ssh_key_password = ssh_key_password
        self._engine: Optional[Engine] = None
        self._ssh_tunnel: Optional[SSHTunnel] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "db_type": self.db_type,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "password": self.password,
            "database": self.database,
            "file_path": self.file_path,
            "ssh_enabled": self.ssh_enabled,
            "ssh_host": self.ssh_host,
            "ssh_port": self.ssh_port,
            "ssh_username": self.ssh_username,
            "ssh_password": self.ssh_password,
            "ssh_key_file": self.ssh_key_file,
            "ssh_key_password": self.ssh_key_password,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatabaseConnection":
        return cls(
            name=data.get("name", ""),
            db_type=data.get("db_type", ""),
            host=data.get("host", ""),
            port=data.get("port", 0),
            username=data.get("username", ""),
            password=data.get("password", ""),
            database=data.get("database", ""),
            file_path=data.get("file_path", ""),
            ssh_enabled=data.get("ssh_enabled", False),
            ssh_host=data.get("ssh_host", ""),
            ssh_port=data.get("ssh_port", 22),
            ssh_username=data.get("ssh_username", ""),
            ssh_password=data.get("ssh_password", ""),
            ssh_key_file=data.get("ssh_key_file", ""),
            ssh_key_password=data.get("ssh_key_password", ""),
        )

    def _load_ssh_pkey(self):
        if not self.ssh_key_file:
            return None
        import paramiko
        key_types = [
            paramiko.RSAKey,
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
        ]
        for key_cls in key_types:
            try:
                return key_cls.from_private_key_file(
                    self.ssh_key_file,
                    password=self.ssh_key_password or None,
                )
            except Exception:
                continue
        raise ValueError(f"无法加载SSH密钥文件: {self.ssh_key_file}，请确认格式为 RSA/Ed25519/ECDSA")

    def _start_ssh_tunnel(self) -> Optional[SSHTunnel]:
        if not self.ssh_enabled or self.db_type == "sqlite":
            return None

        db_port = self.port or (3306 if self.db_type == "mysql" else 5432)
        ssh_pkey = None
        if self.ssh_key_file:
            try:
                ssh_pkey = self._load_ssh_pkey()
            except ValueError as e:
                raise

        tunnel = SSHTunnel(
            ssh_host=self.ssh_host,
            ssh_port=self.ssh_port or 22,
            ssh_username=self.ssh_username,
            remote_host=self.host,
            remote_port=db_port,
            ssh_password=self.ssh_password or None,
            ssh_pkey=ssh_pkey,
        )

        try:
            tunnel.start()
            return tunnel
        except Exception as e:
            raise RuntimeError(f"SSH隧道连接失败: {e}")

    def build_url(self, tunnel_local_port: int = None) -> str:
        if self.db_type == "sqlite":
            return f"sqlite:///{self.file_path}"

        host = "127.0.0.1" if tunnel_local_port else self.host
        port = tunnel_local_port or self.port

        if self.db_type == "mysql":
            port = port or 3306
            return f"mysql+pymysql://{self.username}:{self.password}@{host}:{port}/{self.database}?charset=utf8mb4"
        elif self.db_type == "postgresql":
            port = port or 5432
            return f"postgresql+psycopg2://{self.username}:{self.password}@{host}:{port}/{self.database}"
        raise ValueError(f"Unsupported db_type: {self.db_type}")

    def get_engine(self) -> Engine:
        if self._engine is None:
            if self._ssh_tunnel is None and self.ssh_enabled and self.db_type != "sqlite":
                self._ssh_tunnel = self._start_ssh_tunnel()

            tunnel_port = None
            if self._ssh_tunnel is not None:
                tunnel_port = self._ssh_tunnel.local_bind_port

            url = self.build_url(tunnel_local_port=tunnel_port)
            self._engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
        return self._engine

    def test_connection(self) -> tuple:
        try:
            engine = self.get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True, "连接成功"
        except Exception as e:
            return False, str(e)

    def close(self):
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
        if self._ssh_tunnel is not None:
            try:
                self._ssh_tunnel.stop()
            except Exception:
                pass
            self._ssh_tunnel = None


class DatabaseManager:
    def __init__(self):
        self._connections: Dict[str, DatabaseConnection] = {}
        self._load_connections()

    def _load_connections(self):
        data = nacos_load()
        for item in data:
            conn = DatabaseConnection.from_dict(item)
            self._connections[conn.name] = conn

    def _save_connections(self):
        data = [conn.to_dict() for conn in self._connections.values()]
        nacos_save(data)

    def add_connection(self, conn: DatabaseConnection) -> bool:
        if conn.name in self._connections:
            return False
        self._connections[conn.name] = conn
        self._save_connections()
        return True

    def update_connection(self, old_name: str, conn: DatabaseConnection) -> bool:
        if old_name not in self._connections:
            return False
        old_conn = self._connections.pop(old_name)
        old_conn.close()
        self._connections[conn.name] = conn
        self._save_connections()
        return True

    def remove_connection(self, name: str) -> bool:
        if name not in self._connections:
            return False
        conn = self._connections.pop(name)
        conn.close()
        self._save_connections()
        return True

    def get_connection(self, name: str) -> Optional[DatabaseConnection]:
        return self._connections.get(name)

    def get_all_connections(self) -> List[DatabaseConnection]:
        return list(self._connections.values())

    def get_connection_names(self) -> List[str]:
        return list(self._connections.keys())

    def get_tables(self, conn_name: str) -> List[str]:
        conn = self.get_connection(conn_name)
        if conn is None:
            return []
        try:
            engine = conn.get_engine()
            inspector = inspect(engine)
            return inspector.get_table_names()
        except Exception:
            return []

    def get_columns(self, conn_name: str, table_name: str) -> List[Dict]:
        conn = self.get_connection(conn_name)
        if conn is None:
            return []
        try:
            engine = conn.get_engine()
            inspector = inspect(engine)
            return inspector.get_columns(table_name)
        except Exception:
            return []

    def close_all(self):
        for conn in self._connections.values():
            conn.close()
        self._connections.clear()
