from collections import defaultdict
from typing import Any, Dict, List, Optional

from django.db import models
from django.db.models import Case, F, Func, JSONField, Value, When

from baserow.contrib.database.table.constants import FIELD_METADATA_COLUMN_NAME
from baserow.contrib.database.table.models import GeneratedTableModel


class JSONBRemoveKey(Func):
    """Custom Func for PostgreSQL JSONB - operator (remove key)."""

    function = ""
    arity = 2
    arg_joiner = " - "
    output_field = models.JSONField()

    def as_sql(self, compiler, connection, **extra_context):
        # Ensure the operator is infix by using arg_joiner
        return super().as_sql(
            compiler,
            connection,
            template="%(expressions)s",
            arg_joiner=self.arg_joiner,
            **extra_context,
        )


class FieldMetadataHandler:
    """
    Centralized handler for managing field metadata stored in the
    field_metadata JSONB column.

    This handler ensures consistent access patterns and provides
    utilities for updating metadata efficiently using PostgreSQL's
    native JSONB functions for atomic operations.
    """

    METADATA_COLUMN = FIELD_METADATA_COLUMN_NAME

    @classmethod
    def is_metadata_enabled(cls, model: type[GeneratedTableModel]) -> bool:
        """
        Check if the metadata column is available on the model.

        This provides a consistent way to check if metadata operations
        can be performed on a model.

        :param model: The generated table model class
        :return: True if metadata column exists, False otherwise

        Example:
            >>> if FieldMetadataHandler.is_metadata_enabled(model):
            >>>     FieldMetadataHandler.set_metadata(...)
        """

        return hasattr(model, cls.METADATA_COLUMN)

    @staticmethod
    def get_metadata_column() -> models.JSONField:
        """
        Returns the field definition for the metadata column.
        Used when adding the column to a table dynamically.
        """

        return models.JSONField(
            null=False,
            blank=True,
            default=dict,
            db_default={},
            help_text="Stores metadata for all fields in this row.",
        )

    @classmethod
    def get_metadata(
        cls, row: GeneratedTableModel, field_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific field in a row.

        :param row: The row instance to get metadata from
        :param field_id: The field ID to get metadata for
        :return: Dictionary with metadata, or None if no metadata exists

        Example:
            >>> metadata = FieldMetadataHandler.get_metadata(row, 123)
            >>> if metadata:
            >>>     print(metadata.get('status'))  # "success"
        """

        if not cls.is_metadata_enabled(row.__class__):
            return None

        field_metadata = getattr(row, cls.METADATA_COLUMN, {})
        if not field_metadata:
            return None

        return field_metadata.get(str(field_id))

    @classmethod
    def set_metadata(
        cls,
        model: type[GeneratedTableModel],
        row_id: int,
        field_id: int,
        metadata: Dict[str, Any],
        merge: bool = True,
    ):
        """
        Set metadata for a specific field in a row using atomic PostgreSQL operations.

        This method uses PostgreSQL's jsonb_set function to update only the specific
        field's metadata, avoiding race conditions from read-modify-write patterns.

        :param model: The generated table model class
        :param row_id: The row ID to update
        :param field_id: The field ID to set metadata for
        :param metadata: The metadata dictionary to set
        :param merge: If True, merge with existing metadata. If False,
            replace completely. Defaults to True.

        Example:
            >>> FieldMetadataHandler.set_metadata(
            ...     model=table.get_model(),
            ...     row_id=123,
            ...     field_id=456,
            ...     metadata={
            ...         "status": "success",
            ...         "generated_at": "2024-01-15T10:30:00Z"
            ...     }
            ...     merge=True,
            ... )
        """

        if not cls.is_metadata_enabled(model):
            return

        field_id_str = str(field_id)

        if merge:
            # Use PostgreSQL jsonb_set to atomically update only this field's metadata
            # This avoids race conditions from concurrent updates to different fields
            model.objects.filter(id=row_id).update(
                **{
                    cls.METADATA_COLUMN: Func(
                        Func(
                            F(cls.METADATA_COLUMN),
                            Value("{}"),
                            function="COALESCE",
                            output_field=models.JSONField(),
                        ),
                        Value([field_id_str]),  # Path in JSONB
                        Value(
                            metadata, output_field=models.JSONField()
                        ),  # Value to set
                        Value(True),  # create_missing = true
                        function="jsonb_set",
                        output_field=models.JSONField(),
                    )
                }
            )
        else:
            # Full replace (less common, used when you want to overwrite everything)
            row = model.objects.get(id=row_id)
            field_metadata = getattr(row, cls.METADATA_COLUMN, {})
            field_metadata[field_id_str] = metadata
            setattr(row, cls.METADATA_COLUMN, field_metadata)
            row.save(update_fields=[cls.METADATA_COLUMN])

    @classmethod
    def bulk_set_metadata(
        cls,
        model: type[GeneratedTableModel],
        updates: List[Dict[str, Any]],
    ):
        """
        Bulk update metadata for multiple rows and fields efficiently using a
        single UPDATE statement with PostgreSQL's jsonb_set function.

        This method updates all rows in a single database query, which is much
        more efficient than fetching rows and using bulk_update.

        :param model: The generated table model class
        :param updates: List of dicts with keys: row_id, field_id, metadata

        Example:
            >>> FieldMetadataHandler.bulk_set_metadata(
            ...     model=table.get_model(),
            ...     updates=[
            ...         {
            ...             "row_id": 1,
            ...             "field_id": 123,
            ...             "metadata": {"status": "success"}
            ...         },
            ...         {
            ...             "row_id": 2,
            ...             "field_id": 123,
            ...             "metadata": {"status": "error"}
            ...         },
            ...     ]
            ... )
        """

        if not cls.is_metadata_enabled(model):
            return

        if not updates:
            return

        # Group updates by row_id for efficient processing
        updates_by_row = defaultdict(dict)
        for update in updates:
            row_id = update["row_id"]
            field_id = str(update["field_id"])
            updates_by_row[row_id][field_id] = update["metadata"]

        # Build a single UPDATE query that updates all rows at once
        # For each row, we need to update multiple field_ids in the JSONB column
        # Start with all target row IDs
        row_ids = list(updates_by_row.keys())

        # Build CASE statement for each row
        # For each row, we merge all field updates into the existing JSONB
        whens = []
        for row_id, field_updates in updates_by_row.items():
            # Convert field updates to JSONB merge operation
            # We use jsonb_set multiple times, once per field
            jsonb_expr = F(cls.METADATA_COLUMN)

            for field_id, metadata in field_updates.items():
                # Use COALESCE to handle NULL field_metadata
                jsonb_expr = Func(
                    Func(
                        jsonb_expr,
                        Value("{}"),
                        function="COALESCE",
                        output_field=JSONField(),
                    ),
                    Value([field_id]),
                    Value(metadata, output_field=JSONField()),
                    Value(True),  # create_missing = true
                    function="jsonb_set",
                    output_field=JSONField(),
                )

            whens.append(When(id=row_id, then=jsonb_expr))

        # Execute single UPDATE with CASE for all rows
        if whens:
            model.objects.filter(id__in=row_ids).update(
                **{cls.METADATA_COLUMN: Case(*whens, default=F(cls.METADATA_COLUMN))}
            )

    @classmethod
    def delete_field_metadata(cls, model: type[GeneratedTableModel], field_id: int):
        """
        Remove metadata for a specific field across all rows.
        This should be called when a field is deleted.

        Uses PostgreSQL's - operator to remove a key from JSONB atomically.

        :param model: The generated table model class
        :param field_id: The field ID to remove metadata for

        Example:
            >>> # When deleting field 123
            >>> FieldMetadataHandler.delete_field_metadata(
            ...     model=table.get_model(),
            ...     field_id=123
            ... )
        """

        if not cls.is_metadata_enabled(model):
            return

        field_id_str = str(field_id)

        # Use custom JSONBRemoveKey to properly handle JSONB - operator
        model.objects.filter(
            **{f"{cls.METADATA_COLUMN}__has_key": field_id_str}
        ).update(
            **{
                cls.METADATA_COLUMN: JSONBRemoveKey(
                    F(cls.METADATA_COLUMN), Value(field_id_str)
                )
            }
        )

    @classmethod
    def clear_row_metadata(cls, model: type[GeneratedTableModel], row_id: int):
        """
        Clear all metadata for a specific row.

        :param model: The generated table model class
        :param row_id: The row ID to clear metadata for

        Example:
            >>> FieldMetadataHandler.clear_row_metadata(
            ...     model=table.get_model(),
            ...     row_id=123
            ... )
        """

        if not cls.is_metadata_enabled(model):
            return

        model.objects.filter(id=row_id).update(**{cls.METADATA_COLUMN: {}})

    @classmethod
    def get_rows_by_metadata_status(
        cls,
        model: type[GeneratedTableModel],
        field_id: int,
        status: str,
    ):
        """
        Query rows by metadata status for a specific field.

        :param model: The generated table model class
        :param field_id: The field ID to query
        :param status: The status value to filter by
        :return: QuerySet of rows matching the status

        Example:
            >>> # Get all rows where AI field 123 has status "error"
            >>> error_rows = FieldMetadataHandler.get_rows_by_metadata_status(
            ...     model=table.get_model(),
            ...     field_id=123,
            ...     status="error"
            ... )
        """

        if not cls.is_metadata_enabled(model):
            return model.objects.none()

        field_id_str = str(field_id)

        return model.objects.filter(
            **{f"{cls.METADATA_COLUMN}__{field_id_str}__status": status}
        )

    @classmethod
    def get_rows_with_field_metadata(
        cls,
        model: type[GeneratedTableModel],
        field_id: int,
    ):
        """
        Get all rows that have metadata for a specific field.

        :param model: The generated table model class
        :param field_id: The field ID to query
        :return: QuerySet of rows with metadata for this field

        Example:
            >>> rows_with_metadata = FieldMetadataHandler.get_rows_with_field_metadata(
            ...     model=table.get_model(),
            ...     field_id=123
            ... )
        """

        if not cls.is_metadata_enabled(model):
            return model.objects.none()

        field_id_str = str(field_id)

        # Use JSONB ? operator to check if key exists
        return model.objects.filter(**{f"{cls.METADATA_COLUMN}__has_key": field_id_str})

    @classmethod
    def on_field_updated(cls, field, field_type_changed: bool):
        """
        Handle field updates by clearing metadata if the field type changed.

        When a field's type changes, any existing metadata becomes invalid
        and should be cleared. This method encapsulates the logic for checking
        if the type changed, if metadata is enabled, and clearing it if needed.

        :param field: The field that was updated
        :param field_type_changed: Whether the field type changed

        Example:
            >>> # After updating field 123
            >>> FieldMetadataHandler.on_field_updated(field, field_type_changed=True)
        """

        if not field_type_changed:
            return

        model = field.table.get_model(field_ids=[], add_dependencies=False)
        if cls.is_metadata_enabled(model):
            cls.delete_field_metadata(model, field.id)
