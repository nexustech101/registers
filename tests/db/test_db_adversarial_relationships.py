from __future__ import annotations

import pytest
from pydantic import BaseModel
from sqlalchemy import inspect

from conftest import db_url
from registers.db import (
    ManyToMany,
    ManyToOne,
    OneToMany,
    RelationshipError,
    SchemaError,
    database_registry,
    db_field,
)


class TestAdversarialForeignKeyIntegrity:
    def test_sqlite_foreign_keys_are_enabled_on_connections(self, tmp_path):
        @database_registry(db_url(tmp_path), table_name="users", key_field="id")
        class User(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            email: str

        with User.objects._engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1

    def test_parent_delete_is_restricted_when_children_exist(self, tmp_path):
        url = db_url(tmp_path, "restrict_delete")

        @database_registry(url, table_name="authors", key_field="id")
        class Author(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_id: int = db_field(foreign_key="authors.id", index=True)
            title: str

        author = Author.objects.create(name="Alice")
        Post.objects.create(author_id=author.id, title="Keep parent alive")

        with pytest.raises(SchemaError, match="delete_where"):
            Author.objects.delete(author.id)

        assert Author.objects.exists(id=author.id) is True
        assert Post.objects.count(author_id=author.id) == 1

    def test_fk_update_to_missing_parent_fails_and_rolls_back(self, tmp_path):
        url = db_url(tmp_path, "fk_update")

        @database_registry(url, table_name="authors", key_field="id")
        class Author(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_id: int = db_field(foreign_key="authors.id")
            title: str

        author = Author.objects.create(name="Alice")
        post = Post.objects.create(author_id=author.id, title="Valid")

        with pytest.raises(SchemaError, match="Database integrity error"):
            Post.objects.update_where({"id": post.id}, author_id=999_999)

        assert Post.objects.require(post.id).author_id == author.id

    def test_bulk_create_with_fk_violation_rolls_back_entire_batch(self, tmp_path):
        url = db_url(tmp_path, "bulk_fk")

        @database_registry(url, table_name="authors", key_field="id")
        class Author(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_id: int = db_field(foreign_key="authors.id")
            title: str

        author = Author.objects.create(name="Alice")

        with pytest.raises(SchemaError, match="Database integrity error"):
            Post.objects.bulk_create(
                [
                    {"author_id": author.id, "title": "Valid"},
                    {"author_id": 404_404, "title": "Invalid"},
                ]
            )

        assert Post.objects.count() == 0

    def test_foreign_key_child_key_can_be_indexed_for_parent_mutation_checks(self, tmp_path):
        url = db_url(tmp_path, "fk_index")

        @database_registry(url, table_name="authors", key_field="id")
        class Author(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_id: int = db_field(foreign_key="authors.id", index=True)
            title: str

        indexes = inspect(Post.objects._engine).get_indexes(Post.objects.table_name)
        indexed_columns = {tuple(index["column_names"]) for index in indexes}

        assert ("author_id",) in indexed_columns


class TestAdversarialRelationshipDescriptors:
    def test_cardinality_aliases_work_with_custom_manager_attrs_and_non_id_key(self, tmp_path):
        url = db_url(tmp_path, "aliases")

        @database_registry(url, table_name="authors", key_field="slug", manager_attr="records")
        class Author(BaseModel):
            slug: str
            name: str

        @database_registry(url, table_name="posts", key_field="id", manager_attr="records")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_slug: str = db_field(foreign_key="authors.slug")
            title: str

        Author.posts = OneToMany(Post, foreign_key="author_slug")
        Post.author = ManyToOne(Author, local_key="author_slug")

        alice = Author.records.create(slug="alice", name="Alice")
        bob = Author.records.create(slug="bob", name="Bob")
        post = Post.records.create(author_slug="alice", title="Correct parent")
        Post.records.create(author_slug="bob", title="Other parent")

        assert [row.title for row in alice.posts] == ["Correct parent"]
        assert bob.posts[0].title == "Other parent"
        assert post.author.slug == "alice"

    def test_many_to_many_alias_dedupes_duplicate_join_rows_and_skips_deleted_targets(self, tmp_path):
        url = db_url(tmp_path, "many_to_many_alias")

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            title: str

        @database_registry(url, table_name="tags", key_field="id")
        class Tag(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="post_tags", key_field="id")
        class PostTag(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            post_id: int = db_field(foreign_key="posts.id")
            tag_id: int

        Post.tags = ManyToMany(Tag, through=PostTag, source_key="post_id", target_key="tag_id")

        post = Post.objects.create(title="Relations")
        kept = Tag.objects.create(name="kept")
        removed = Tag.objects.create(name="removed")
        PostTag.objects.create(post_id=post.id, tag_id=kept.id)
        PostTag.objects.create(post_id=post.id, tag_id=kept.id)
        PostTag.objects.create(post_id=post.id, tag_id=removed.id)
        Tag.objects.delete(removed.id)

        assert [tag.name for tag in post.tags] == ["kept"]

    def test_many_to_many_with_fk_join_table_rejects_orphan_source_and_target_rows(self, tmp_path):
        url = db_url(tmp_path, "many_to_many_fk")

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            title: str

        @database_registry(url, table_name="tags", key_field="id")
        class Tag(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="post_tags", key_field="id")
        class PostTag(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            post_id: int = db_field(foreign_key="posts.id")
            tag_id: int = db_field(foreign_key="tags.id")

        post = Post.objects.create(title="Relations")
        tag = Tag.objects.create(name="db")
        PostTag.objects.create(post_id=post.id, tag_id=tag.id)

        with pytest.raises(SchemaError, match="Database integrity error"):
            PostTag.objects.create(post_id=post.id, tag_id=999)

        with pytest.raises(SchemaError, match="Database integrity error"):
            PostTag.objects.create(post_id=999, tag_id=tag.id)

    def test_misconfigured_relationships_raise_clear_errors_at_access_time(self, tmp_path):
        url = db_url(tmp_path, "misconfigured_relations")

        @database_registry(url, table_name="authors", key_field="id")
        class Author(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry(url, table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_id: int | None = None
            title: str

        @database_registry(url, table_name="post_tags", key_field="id")
        class PostTag(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            post_id: int

        Author.broken_posts = OneToMany(Post, foreign_key="missing_author_id")
        Post.broken_author = ManyToOne(Author, local_key="missing_author_id")
        Post.broken_tags = ManyToMany(Author, through=PostTag, source_key="post_id", target_key="tag_id")

        author = Author.objects.create(name="Alice")
        post = Post.objects.create(author_id=author.id, title="Broken")

        with pytest.raises(RelationshipError, match="foreign_key 'missing_author_id'"):
            _ = author.broken_posts

        with pytest.raises(RelationshipError, match="local_key 'missing_author_id'"):
            _ = post.broken_author

        with pytest.raises(RelationshipError, match="key 'tag_id'"):
            _ = post.broken_tags
