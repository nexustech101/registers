from __future__ import annotations

from pydantic import BaseModel

from conftest import db_url
from registers.db import database_registry, db_field


class TestPasswordHashing:
    def test_password_field_hashes_only_when_db_field_requests_it(self, tmp_path):
        @database_registry(db_url(tmp_path), table_name="accounts", key_field="id")
        class Account(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            email: str
            password: str = db_field(hash_password=True)

        account = Account.objects.create(email="alice@example.com", password="secret123")
        first_hash = account.password

        account.email = "alice+1@example.com"
        account.save()
        second_hash = account.password

        account.save()
        third_hash = account.password

        assert first_hash == second_hash
        assert second_hash == third_hash
        assert account.verify_password("secret123") is True

    def test_plain_password_field_is_not_hashed_or_given_verify_helper(self, tmp_path):
        @database_registry(db_url(tmp_path), table_name="plain_accounts", key_field="id")
        class Account(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            email: str
            password: str

        account = Account.objects.create(email="alice@example.com", password="secret123")

        assert account.password == "secret123"
        assert not hasattr(account, "verify_password")
