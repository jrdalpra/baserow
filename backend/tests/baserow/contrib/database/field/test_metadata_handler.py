"""
Tests for the FieldMetadataHandler utility.
"""

import pytest
from django.db import connection

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler

@pytest.mark.row_metadata
@pytest.mark.django_db
def test_set_and_get_metadata(data_fixture):
    """Test setting and retrieving metadata for a field."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Set metadata
    metadata = {
        "status": "success",
        "generated_at": "2024-01-15T10:30:00Z",
        "version": 1,
    }
    FieldMetadataHandler.set_metadata(model, row.id, field.id, metadata)

    # Get metadata
    row.refresh_from_db()
    retrieved = FieldMetadataHandler.get_metadata(row, field.id)

    assert retrieved is not None
    assert retrieved["status"] == "success"
    assert retrieved["generated_at"] == "2024-01-15T10:30:00Z"
    assert retrieved["version"] == 1


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_metadata_merge_behavior(data_fixture):
    """Test that merge=True preserves existing metadata for other fields."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field1 = data_fixture.create_text_field(table=table)
    field2 = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Set metadata for field1
    FieldMetadataHandler.set_metadata(
        model, row.id, field1.id, {"status": "field1_status"}
    )

    # Set metadata for field2 (should not affect field1)
    FieldMetadataHandler.set_metadata(
        model, row.id, field2.id, {"status": "field2_status"}
    )

    # Check both fields have their metadata
    row.refresh_from_db()
    field1_meta = FieldMetadataHandler.get_metadata(row, field1.id)
    field2_meta = FieldMetadataHandler.get_metadata(row, field2.id)

    assert field1_meta["status"] == "field1_status"
    assert field2_meta["status"] == "field2_status"


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_bulk_set_metadata(data_fixture):
    """Test bulk setting metadata for multiple rows."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row1 = model.objects.create()
    row2 = model.objects.create()
    row3 = model.objects.create()

    # Bulk set metadata
    updates = [
        {"row_id": row1.id, "field_id": field.id, "metadata": {"status": "success"}},
        {"row_id": row2.id, "field_id": field.id, "metadata": {"status": "error"}},
        {"row_id": row3.id, "field_id": field.id, "metadata": {"status": "pending"}},
    ]
    FieldMetadataHandler.bulk_set_metadata(model, updates)

    # Verify
    row1.refresh_from_db()
    row2.refresh_from_db()
    row3.refresh_from_db()

    assert FieldMetadataHandler.get_metadata(row1, field.id)["status"] == "success"
    assert FieldMetadataHandler.get_metadata(row2, field.id)["status"] == "error"
    assert FieldMetadataHandler.get_metadata(row3, field.id)["status"] == "pending"


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_delete_field_metadata(data_fixture):
    """Test deleting metadata for a field across all rows."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row1 = model.objects.create()
    row2 = model.objects.create()

    # Set metadata for both rows
    FieldMetadataHandler.set_metadata(
        model, row1.id, field.id, {"status": "success"}
    )
    FieldMetadataHandler.set_metadata(
        model, row2.id, field.id, {"status": "success"}
    )

    # Delete field metadata
    FieldMetadataHandler.delete_field_metadata(model, field.id)

    # Verify metadata is gone
    row1.refresh_from_db()
    row2.refresh_from_db()

    assert FieldMetadataHandler.get_metadata(row1, field.id) is None
    assert FieldMetadataHandler.get_metadata(row2, field.id) is None


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_delete_field_metadata_preserves_other_keys(data_fixture):
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field1 = data_fixture.create_text_field(table=table)
    field2 = data_fixture.create_text_field(table=table)

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    FieldMetadataHandler.set_metadata(model, row.id, field1.id, {"a": 1})
    FieldMetadataHandler.set_metadata(model, row.id, field2.id, {"b": 2})

    FieldMetadataHandler.delete_field_metadata(model, field1.id)

    row.refresh_from_db()
    assert FieldMetadataHandler.get_metadata(row, field1.id) is None
    assert FieldMetadataHandler.get_metadata(row, field2.id) == {"b": 2}


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_clear_row_metadata(data_fixture):
    """Test clearing all metadata for a specific row."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field1 = data_fixture.create_text_field(table=table)
    field2 = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Set metadata for multiple fields
    FieldMetadataHandler.set_metadata(
        model, row.id, field1.id, {"status": "success"}
    )
    FieldMetadataHandler.set_metadata(
        model, row.id, field2.id, {"status": "error"}
    )

    # Clear all metadata for the row
    FieldMetadataHandler.clear_row_metadata(model, row.id)

    # Verify all metadata is gone
    row.refresh_from_db()
    assert FieldMetadataHandler.get_metadata(row, field1.id) is None
    assert FieldMetadataHandler.get_metadata(row, field2.id) is None

@pytest.mark.row_metadata
@pytest.mark.django_db
def test_get_rows_by_metadata_status(data_fixture):
    """Test querying rows by metadata status."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row_success = model.objects.create()
    row_error = model.objects.create()
    row_pending = model.objects.create()

    # Set different statuses
    FieldMetadataHandler.set_metadata(
        model, row_success.id, field.id, {"status": "success"}
    )
    FieldMetadataHandler.set_metadata(
        model, row_error.id, field.id, {"status": "error"}
    )
    FieldMetadataHandler.set_metadata(
        model, row_pending.id, field.id, {"status": "pending"}
    )

    # Query by status
    error_rows = FieldMetadataHandler.get_rows_by_metadata_status(
        model, field.id, "error"
    )

    assert error_rows.count() == 1
    assert error_rows.first().id == row_error.id


@pytest.mark.django_db
def test_get_rows_with_field_metadata(data_fixture):
    """Test getting rows that have metadata for a specific field."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row_with_meta = model.objects.create()
    row_without_meta = model.objects.create()

    # Only set metadata for one row
    FieldMetadataHandler.set_metadata(
        model, row_with_meta.id, field.id, {"status": "success"}
    )

    # Query rows with metadata
    rows_with_meta = FieldMetadataHandler.get_rows_with_field_metadata(model, field.id)

    assert rows_with_meta.count() == 1
    assert rows_with_meta.first().id == row_with_meta.id


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_graceful_degradation_without_column(data_fixture):
    """Test that handler gracefully handles tables without metadata column."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Do NOT add metadata column
    table.field_metadata_column_added = False
    table.save()

    model = table.get_model()
    row = model.objects.create()

    # These should not raise errors
    FieldMetadataHandler.set_metadata(
        model, row.id, field.id, {"status": "success"}
    )
    metadata = FieldMetadataHandler.get_metadata(row, field.id)
    assert metadata is None

    # Query methods should return empty querysets
    rows = FieldMetadataHandler.get_rows_by_metadata_status(model, field.id, "success")
    assert rows.count() == 0


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_metadata_atomicity(data_fixture):
    """Test that set_metadata is atomic using jsonb_set."""
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    field = data_fixture.create_text_field(table=table)

    # Ensure the table has the metadata column
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Set initial metadata
    FieldMetadataHandler.set_metadata(
        model, row.id, field.id, {"status": "pending", "attempt": 1}
    )

    # Update only part of the metadata
    FieldMetadataHandler.set_metadata(
        model, row.id, field.id, {"status": "success", "attempt": 2}
    )

    # Verify the update worked
    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, field.id)

    assert metadata["status"] == "success"
    assert metadata["attempt"] == 2


@pytest.mark.row_metadata
@pytest.mark.django_db
def test_remap_field_id_moves_metadata_and_removes_old_key(data_fixture):
    user = data_fixture.create_user()
    table = data_fixture.create_database_table(user=user)
    old_field = data_fixture.create_text_field(table=table)
    new_field = data_fixture.create_text_field(table=table)

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    FieldMetadataHandler.set_metadata(
        model, row.id, old_field.id, {"status": "ok", "v": 1}
    )

    FieldMetadataHandler.remap_field_id(old_field=old_field, new_field=new_field)

    row.refresh_from_db()
    assert FieldMetadataHandler.get_metadata(row, old_field.id) is None
    remapped = FieldMetadataHandler.get_metadata(row, new_field.id)
    assert remapped == {"status": "ok", "v": 1}
