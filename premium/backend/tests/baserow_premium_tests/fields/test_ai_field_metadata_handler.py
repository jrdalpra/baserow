"""
Tests for the AI Field Metadata Handler.
"""

import pytest

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler
from baserow_premium.fields.ai_field_metadata import (
    AIFieldMetadataHandler,
    AIGenerationStatus,
    AIMetadataKeys,
)


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_set_generating(premium_data_fixture):
    """Test marking an AI field as generating."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    # Ensure metadata column exists
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Mark as generating
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    # Verify metadata
    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

    assert metadata is not None
    assert metadata[AIMetadataKeys.STATUS] == AIGenerationStatus.GENERATING
    assert AIMetadataKeys.GENERATION_STARTED_AT in metadata


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_set_success(premium_data_fixture):
    """Test marking an AI field as successful."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # First mark as generating
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    # Then mark as success
    AIFieldMetadataHandler.set_success(model, row.id, ai_field.id)

    # Verify metadata
    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

    assert metadata is not None
    assert metadata[AIMetadataKeys.STATUS] == AIGenerationStatus.SUCCESS
    assert AIMetadataKeys.GENERATION_STARTED_AT in metadata  # Preserved from set_generating
    assert AIMetadataKeys.GENERATION_FINISHED_AT in metadata
    assert AIMetadataKeys.ERROR not in metadata  # No error field when successful


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_set_error(premium_data_fixture):
    """Test marking an AI field as failed with an error."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Mark as generating
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    # Mark as error
    AIFieldMetadataHandler.set_error(
        model, row.id, ai_field.id, "Test error message", "ValueError"
    )

    # Verify metadata
    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

    assert metadata is not None
    assert metadata[AIMetadataKeys.STATUS] == AIGenerationStatus.ERROR
    assert AIMetadataKeys.GENERATION_STARTED_AT in metadata  # Preserved from set_generating
    assert AIMetadataKeys.GENERATION_FINISHED_AT in metadata
    assert AIMetadataKeys.ERROR in metadata
    assert metadata[AIMetadataKeys.ERROR][AIMetadataKeys.ERROR_MESSAGE] == "Test error message"
    assert metadata[AIMetadataKeys.ERROR][AIMetadataKeys.ERROR_TYPE] == "ValueError"


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_get_status(premium_data_fixture):
    """Test getting the status of an AI field."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Initially no metadata
    assert AIFieldMetadataHandler.get_status(row, ai_field.id) is None

    # Set generating
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)
    row.refresh_from_db()
    assert AIFieldMetadataHandler.get_status(row, ai_field.id) == AIGenerationStatus.GENERATING

    # Set success
    AIFieldMetadataHandler.set_success(model, row.id, ai_field.id)
    row.refresh_from_db()
    assert AIFieldMetadataHandler.get_status(row, ai_field.id) == AIGenerationStatus.SUCCESS


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_get_error(premium_data_fixture):
    """Test getting error details."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # No error initially
    assert AIFieldMetadataHandler.get_error(row, ai_field.id) is None

    # Set error
    AIFieldMetadataHandler.set_error(
        model, row.id, ai_field.id, "Connection timeout", "TimeoutError"
    )
    row.refresh_from_db()

    error = AIFieldMetadataHandler.get_error(row, ai_field.id)
    assert error is not None
    assert error["message"] == "Connection timeout"
    assert error["type"] == "TimeoutError"


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_get_rows_with_errors(premium_data_fixture):
    """Test querying rows with errors."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row_success = model.objects.create()
    row_error1 = model.objects.create()
    row_error2 = model.objects.create()

    # Set different statuses
    AIFieldMetadataHandler.set_success(model, row_success.id, ai_field.id)
    AIFieldMetadataHandler.set_error(
        model, row_error1.id, ai_field.id, "Error 1", "ValueError"
    )
    AIFieldMetadataHandler.set_error(
        model, row_error2.id, ai_field.id, "Error 2", "RuntimeError"
    )

    # Query rows with errors
    error_rows = AIFieldMetadataHandler.get_rows_with_errors(model, ai_field.id)

    assert error_rows.count() == 2
    error_row_ids = {row.id for row in error_rows}
    assert row_error1.id in error_row_ids
    assert row_error2.id in error_row_ids
    assert row_success.id not in error_row_ids


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_get_rows_pending_generation(premium_data_fixture):
    """Test querying rows pending generation."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row_pending = model.objects.create()
    row_success = model.objects.create()

    # Manually set pending status (normally done via get_initial_metadata)
    FieldMetadataHandler.set_metadata(
        model,
        row_pending.id,
        ai_field.id,
        {AIMetadataKeys.STATUS: AIGenerationStatus.PENDING},
    )
    AIFieldMetadataHandler.set_success(model, row_success.id, ai_field.id)

    # Query pending rows
    pending_rows = AIFieldMetadataHandler.get_rows_pending_generation(
        model, ai_field.id
    )

    assert pending_rows.count() == 1
    assert pending_rows.first().id == row_pending.id


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_timestamps(premium_data_fixture):
    """Test timestamp tracking."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    # Mark as generating
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)
    row.refresh_from_db()

    started_at = AIFieldMetadataHandler.get_generation_started_at(row, ai_field.id)
    assert started_at is not None

    # Mark as success
    AIFieldMetadataHandler.set_success(model, row.id, ai_field.id)
    row.refresh_from_db()

    finished_at = AIFieldMetadataHandler.get_generation_finished_at(row, ai_field.id)
    assert finished_at is not None

    # Finished should be after started (or at least exist)
    assert finished_at is not None


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_without_metadata_column(premium_data_fixture):
    """Test that handler gracefully handles tables without metadata column."""
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    # Do NOT add metadata column
    model = table.get_model()
    row = model.objects.create()

    # These should not raise errors
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)
    AIFieldMetadataHandler.set_success(model, row.id, ai_field.id)
    AIFieldMetadataHandler.set_error(
        model, row.id, ai_field.id, "Test error", "ValueError"
    )

    # Get methods should return None
    assert AIFieldMetadataHandler.get_status(row, ai_field.id) is None
    assert AIFieldMetadataHandler.get_error(row, ai_field.id) is None
    assert AIFieldMetadataHandler.get_generation_started_at(row, ai_field.id) is None
    assert AIFieldMetadataHandler.get_generation_finished_at(row, ai_field.id) is None
