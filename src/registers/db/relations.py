"""
Explicit, lazy-loaded relationship descriptors.

Usage pattern
-------------
Relationships must be **assigned after** the class body is executed.
This is necessary because Pydantic v2's metaclass validates the class body
at class-creation time and rejects unannotated non-field attributes.

By assigning after the class (and after ``@database_registry`` decoration),
Pydantic's metaclass has already run and we can safely attach descriptors::

    @database_registry("app.db", table_name="authors", key_field="id")
    class Author(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        name: str

    @database_registry("app.db", table_name="posts", key_field="id")
    class Post(BaseModel):
        id: int | None = db_field(id_strategy="autoincrement", default=None)
        author_id: int
        title: str

    # Declare relationships AFTER both classes are decorated
    Author.posts = HasMany(Post, foreign_key="author_id")
    Post.author  = BelongsTo(Author, local_key="author_id")

This pattern also naturally solves forward-reference ordering — related
models must exist before you can reference them in a relationship, which is
the same constraint you'd face with inline declarations anyway.

Relationship types
------------------
* :class:`HasMany`         — one-to-many  (Author → Posts)
* :class:`BelongsTo`       — many-to-one  (Post → Author)
* :class:`HasManyThrough`  — many-to-many via join table (Post ↔ Tag)

All relationships are:
* **Lazy-loaded** — no query runs until the descriptor is accessed.
* **Read-only** — assignment raises :class:`RelationshipError`.
* **Self-validating** — misconfiguration is detected at access time with
  a clear error message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from registers.db.exceptions import RelationshipError

if TYPE_CHECKING:
    from pydantic import BaseModel


_PREFETCH_PREFIX = "__registers_prefetch_"


def _prefetch_cache_name(name: str) -> str:
    return f"{_PREFETCH_PREFIX}{name}"


# ---------------------------------------------------------------------------
# Base descriptor
# ---------------------------------------------------------------------------

class _BaseRelationship:
    """
    Common validation and attribute-name bookkeeping for all relationship
    descriptors.

    ``__set_name__`` is called automatically by Python when the descriptor is
    assigned as a class attribute, giving us the attribute name for use in
    error messages.  Because we also support post-class assignment
    (``Author.posts = HasMany(...)``), we fall back to ``'<unbound>'`` until
    ``__set_name__`` is called.
    """

    _attr_name: str = "<unbound>"

    def __set_name__(self, owner: type, name: str) -> None:
        self._attr_name = name

    def __set__(self, obj: Any, value: Any) -> None:
        raise RelationshipError(
            f"Relationship '{self._attr_name}' is read-only. "
            "To associate records, use the related model's manager directly "
            f"(e.g. Post.objects.create(author_id=...))."
        )

    def _get_manager(self, model_cls: Any, manager_attr: str | None = None) -> Any:
        """Retrieve the DatabaseRegistry attached to *model_cls*."""
        if manager_attr is not None:
            manager = getattr(model_cls, manager_attr, None)
        else:
            manager = self._find_attached_manager(model_cls)
        if manager is None:
            expected = manager_attr or "registered manager"
            raise RelationshipError(
                f"Model '{model_cls.__name__}' has no '{expected}' manager. "
                "Make sure it is decorated with @database_registry before "
                f"the relationship '{self._attr_name}' is accessed."
            )
        return manager

    @staticmethod
    def _find_attached_manager(model_cls: Any) -> Any:
        manager = getattr(model_cls, "objects", None)
        if manager is not None and getattr(getattr(manager, "config", None), "model_cls", None) is model_cls:
            return manager

        for value in vars(model_cls).values():
            config = getattr(value, "config", None)
            if getattr(config, "model_cls", None) is model_cls:
                return value
        return None

    def _cached(self, obj: Any) -> Any:
        if self._attr_name == "<unbound>":
            return None
        return getattr(obj, _prefetch_cache_name(self._attr_name), None)


# ---------------------------------------------------------------------------
# HasMany  (one-to-many)
# ---------------------------------------------------------------------------

class HasMany(_BaseRelationship):
    """
    Declares a one-to-many relationship.

    The *foreign_key* is the column on the **related** model that stores the
    primary key of **this** model.

    Example::

        @database_registry("app.db", table_name="authors", key_field="id")
        class Author(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            name: str

        @database_registry("app.db", table_name="posts", key_field="id")
        class Post(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            author_id: int
            title: str

        Author.posts = HasMany(Post, foreign_key="author_id")

        author = Author.objects.require(1)
        author.posts  # → list[Post]

    Parameters
    ----------
    related_model:
        The model class on the **many** side of the relationship.
    foreign_key:
        The field name on *related_model* that stores this model's primary key.
    """

    def __init__(self, related_model: type, *, foreign_key: str) -> None:
        self._related_model = related_model
        self._foreign_key = foreign_key

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        # Accessed on the class itself → return the descriptor for introspection
        if obj is None:
            return self
        cached = self._cached(obj)
        if cached is not None:
            return cached

        manager = self._get_manager(self._related_model)

        if self._foreign_key not in self._related_model.model_fields:
            raise RelationshipError(
                f"HasMany foreign_key '{self._foreign_key}' is not a field on "
                f"'{self._related_model.__name__}'. "
                f"Available fields: {list(self._related_model.model_fields.keys())}"
            )

        # Determine the local primary key value
        local_manager = self._get_manager(type(obj))
        local_key_field = local_manager.config.key_field
        local_key_value = getattr(obj, local_key_field)

        return manager.filter(**{self._foreign_key: local_key_value})


# ---------------------------------------------------------------------------
# BelongsTo  (many-to-one / inverse of HasMany)
# ---------------------------------------------------------------------------

class BelongsTo(_BaseRelationship):
    """
    Declares a many-to-one relationship.

    The *local_key* is the column on **this** model that stores the foreign key
    pointing at the related model's primary key.

    Example::

        Post.author = BelongsTo(Author, local_key="author_id")

        post = Post.objects.require(1)
        post.author  # → Author | None

    Parameters
    ----------
    related_model:
        The model class on the **one** side of the relationship.
    local_key:
        The field name on **this** model that stores the foreign key.
    """

    def __init__(self, related_model: type, *, local_key: str) -> None:
        self._related_model = related_model
        self._local_key = local_key

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        cached = self._cached(obj)
        if cached is not None:
            return cached

        manager = self._get_manager(self._related_model)

        local_fields = type(obj).model_fields
        if self._local_key not in local_fields:
            raise RelationshipError(
                f"BelongsTo local_key '{self._local_key}' is not a field on "
                f"'{type(obj).__name__}'. "
                f"Available fields: {list(local_fields.keys())}"
            )

        fk_value = getattr(obj, self._local_key)
        if fk_value is None:
            return None

        return manager.get(fk_value)


# ---------------------------------------------------------------------------
# HasManyThrough  (many-to-many via join table)
# ---------------------------------------------------------------------------

class HasManyThrough(_BaseRelationship):
    """
    Declares a many-to-many relationship via an explicit join table.

    Example::

        @database_registry("app.db", table_name="post_tags", key_field="id")
        class PostTag(BaseModel):
            id: int | None = db_field(id_strategy="autoincrement", default=None)
            post_id: int
            tag_id: int

        Post.tags = HasManyThrough(Tag, through=PostTag,
                                   source_key="post_id", target_key="tag_id")

        post = Post.objects.require(1)
        post.tags  # → list[Tag]

    Parameters
    ----------
    related_model:
        The model class on the far side of the relationship.
    through:
        The join-table model.  Must have fields named *source_key* and
        *target_key*.
    source_key:
        Column on *through* that stores **this** model's primary key.
    target_key:
        Column on *through* that stores *related_model*'s primary key.
    """

    def __init__(
        self,
        related_model: type,
        *,
        through: type,
        source_key: str,
        target_key: str,
    ) -> None:
        self._related_model = related_model
        self._through = through
        self._source_key = source_key
        self._target_key = target_key

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        if obj is None:
            return self
        cached = self._cached(obj)
        if cached is not None:
            return cached

        through_manager = self._get_manager(self._through)
        related_manager = self._get_manager(self._related_model)

        # Validate join-table fields
        through_fields = self._through.model_fields
        for key_attr in (self._source_key, self._target_key):
            if key_attr not in through_fields:
                raise RelationshipError(
                    f"HasManyThrough key '{key_attr}' is not a field on "
                    f"through-model '{self._through.__name__}'. "
                    f"Available fields: {list(through_fields.keys())}"
                )

        # Determine local primary key
        local_manager = self._get_manager(type(obj))
        local_key_field = local_manager.config.key_field
        local_key_value = getattr(obj, local_key_field)

        # Step 1: find all join-table rows matching this instance
        join_rows = through_manager.filter(**{self._source_key: local_key_value})
        if not join_rows:
            return []

        # Step 2: collect target PKs
        related_ids = [getattr(row, self._target_key) for row in join_rows]

        # Step 3: fetch related records; skip any that were deleted
        records: list[Any] = []
        seen: set[Any] = set()
        for pk in related_ids:
            if pk in seen:
                continue
            seen.add(pk)
            record = related_manager.get(pk)
            if record is not None:
                records.append(record)
        return records


class OneToMany(HasMany):
    """Explicit cardinality alias for :class:`HasMany`."""


class ManyToOne(BelongsTo):
    """Explicit cardinality alias for :class:`BelongsTo`."""


class ManyToMany(HasManyThrough):
    """Explicit cardinality alias for :class:`HasManyThrough`."""


def prefetch(records: list[Any] | tuple[Any, ...], relationship_name: str) -> list[Any] | tuple[Any, ...]:
    """Batch-load a relationship descriptor for a collection of records."""
    if not records:
        return records

    owner = type(records[0])
    relationship = getattr(owner, relationship_name, None)
    if not isinstance(relationship, _BaseRelationship):
        raise RelationshipError(
            f"'{relationship_name}' is not a registers.db relationship on '{owner.__name__}'."
        )
    relationship._attr_name = relationship_name

    if isinstance(relationship, HasManyThrough):
        _prefetch_many_to_many(records, relationship_name, relationship)
    elif isinstance(relationship, HasMany):
        _prefetch_has_many(records, relationship_name, relationship)
    elif isinstance(relationship, BelongsTo):
        _prefetch_belongs_to(records, relationship_name, relationship)
    else:  # pragma: no cover - defensive for future relationship types
        raise RelationshipError(f"Unsupported relationship type for '{relationship_name}'.")
    return records


def _prefetch_has_many(
    records: list[Any] | tuple[Any, ...],
    relationship_name: str,
    relationship: HasMany,
) -> None:
    local_manager = relationship._get_manager(type(records[0]))
    local_values = [getattr(record, local_manager.config.key_field) for record in records]
    related_manager = relationship._get_manager(relationship._related_model)
    rows = related_manager.filter(**{f"{relationship._foreign_key}__in": local_values})

    grouped: dict[Any, list[Any]] = {value: [] for value in local_values}
    for row in rows:
        grouped.setdefault(getattr(row, relationship._foreign_key), []).append(row)
    for record in records:
        local_value = getattr(record, local_manager.config.key_field)
        object.__setattr__(record, _prefetch_cache_name(relationship_name), grouped.get(local_value, []))


def _prefetch_belongs_to(
    records: list[Any] | tuple[Any, ...],
    relationship_name: str,
    relationship: BelongsTo,
) -> None:
    related_manager = relationship._get_manager(relationship._related_model)
    values = [getattr(record, relationship._local_key) for record in records]
    lookup_values = [value for value in values if value is not None]
    related_rows = (
        related_manager.filter(**{f"{related_manager.key_field}__in": lookup_values})
        if lookup_values
        else []
    )
    by_key = {getattr(row, related_manager.key_field): row for row in related_rows}
    for record, value in zip(records, values):
        object.__setattr__(record, _prefetch_cache_name(relationship_name), by_key.get(value))


def _prefetch_many_to_many(
    records: list[Any] | tuple[Any, ...],
    relationship_name: str,
    relationship: HasManyThrough,
) -> None:
    local_manager = relationship._get_manager(type(records[0]))
    local_values = [getattr(record, local_manager.config.key_field) for record in records]
    through_manager = relationship._get_manager(relationship._through)
    related_manager = relationship._get_manager(relationship._related_model)

    join_rows = through_manager.filter(**{f"{relationship._source_key}__in": local_values})
    target_ids: list[Any] = []
    grouped_target_ids: dict[Any, list[Any]] = {value: [] for value in local_values}
    for row in join_rows:
        source_id = getattr(row, relationship._source_key)
        target_id = getattr(row, relationship._target_key)
        grouped_target_ids.setdefault(source_id, []).append(target_id)
        if target_id not in target_ids:
            target_ids.append(target_id)

    related_rows = (
        related_manager.filter(**{f"{related_manager.key_field}__in": target_ids})
        if target_ids
        else []
    )
    related_by_key = {getattr(row, related_manager.key_field): row for row in related_rows}

    for record in records:
        local_value = getattr(record, local_manager.config.key_field)
        seen: set[Any] = set()
        resolved = []
        for target_id in grouped_target_ids.get(local_value, []):
            if target_id in seen:
                continue
            seen.add(target_id)
            related = related_by_key.get(target_id)
            if related is not None:
                resolved.append(related)
        object.__setattr__(record, _prefetch_cache_name(relationship_name), resolved)
