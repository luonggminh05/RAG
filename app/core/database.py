import logging
import re
from typing import Generator
from urllib.parse import quote_plus
import pyodbc
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

def build_database_url(conn_str: str) -> str:
    """
    Xây dựng SQLAlchemy URL từ ODBC Connection String.
    Tự động chuẩn hóa driver và tham số mã hóa cho unixODBC/Windows pyodbc.
    """
    if not conn_str:
        return "sqlite:///:memory:"

    # Normalize connection string boolean values for pyodbc/unixODBC compatibility
    conn_str = re.sub(r'(?i)\bTrustServerCertificate\s*=\s*True\b', 'TrustServerCertificate=yes', conn_str)
    conn_str = re.sub(r'(?i)\bTrustServerCertificate\s*=\s*False\b', 'TrustServerCertificate=no', conn_str)
    conn_str = re.sub(r'(?i)\bEncrypt\s*=\s*True\b', 'Encrypt=yes', conn_str)
    conn_str = re.sub(r'(?i)\bEncrypt\s*=\s*False\b', 'Encrypt=no', conn_str)

    try:
        available_drivers = pyodbc.drivers()
    except Exception:
        available_drivers = []

    preferred_drivers = [
        "ODBC Driver 18 for SQL Server",
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 13 for SQL Server",
        "SQL Server",
    ]

    driver_match = re.search(r"Driver=\{([^}]+)\}", conn_str, re.IGNORECASE)
    if driver_match:
        current_driver = driver_match.group(1)
        if available_drivers and current_driver not in available_drivers:
            fallback_driver = next(
                (d for d in preferred_drivers if d in available_drivers), None
            )
            if fallback_driver:
                logger.warning(
                    f"ODBC Driver '{current_driver}' không có sẵn. Tự động chuyển sang '{fallback_driver}'."
                )
                conn_str = re.sub(
                    r"Driver=\{[^}]+\}",
                    f"Driver={{{fallback_driver}}}",
                    conn_str,
                    flags=re.IGNORECASE,
                )
    elif available_drivers:
        fallback_driver = next(
            (d for d in preferred_drivers if d in available_drivers), None
        )
        if fallback_driver:
            if not conn_str.rstrip().endswith(";"):
                conn_str += ";"
            conn_str = f"Driver={{{fallback_driver}}};{conn_str}"

    encoded_params = quote_plus(conn_str)
    return f"mssql+pyodbc:///?odbc_connect={encoded_params}"


SQLALCHEMY_DATABASE_URL = build_database_url(settings.sql_connection_string)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    fast_executemany=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI Dependency trả về database Session cho từng request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Tạo schema các bảng ORM nếu chưa tồn tại."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[OK] Database ORM schemas verified/created.")
    except Exception as ex:
        logger.warning(f"[WARN] init_db ORM create_all encountered: {ex}")
