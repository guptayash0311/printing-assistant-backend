from app.core.config import Settings


def test_postgres_password_at_sign_is_percent_encoded():
    settings = Settings(
        postgres_user="shop",
        postgres_password="p@ss",
        postgres_host="db.internal",
        postgres_port=5432,
        postgres_db="print",
        database_url="",
    )
    assert settings.database_url == "postgresql+psycopg://shop:p%40ss@db.internal:5432/print"


def test_explicit_database_url_overrides_postgres_parts():
    settings = Settings(
        postgres_user="shop",
        postgres_password="p@ss",
        postgres_db="print",
        database_url="sqlite+pysqlite:///./dev.db",
    )
    assert settings.database_url == "sqlite+pysqlite:///./dev.db"


def test_missing_postgres_parts_use_sqlite():
    settings = Settings(postgres_user="", postgres_password="p@ss", postgres_db="", database_url="")
    assert settings.database_url == "sqlite+pysqlite:///./dev.db"
