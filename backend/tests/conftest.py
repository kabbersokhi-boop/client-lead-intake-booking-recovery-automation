import os

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["CRM_PROVIDER_MODE"] = "development"
os.environ.pop("HIGHLEVEL_TOKEN", None)

from app.config import settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture()
def db(tmp_path):
    database_url = f"sqlite:///{tmp_path}/test.db"
    engine = create_engine(database_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = session_local()
    yield session
    session.close()


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    previous_key = settings.crm_adapter_api_key
    settings.crm_adapter_api_key = SecretStr("test-adapter-key")
    with TestClient(app, headers={"X-CRM-Adapter-Key": "test-adapter-key"}) as test_client:
        yield test_client
    settings.crm_adapter_api_key = previous_key
    app.dependency_overrides.clear()
