import pytest
from baserow_premium.fields.ai_field_metadata import (
    AIFieldMetadataHandler,
    AIGenerationStatus,
    AIMetadataKeys,
)

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_set_generating(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = table.get_model()
    row = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

    assert metadata is not None
    assert metadata[AIMetadataKeys.STATUS] == AIGenerationStatus.GENERATING
    assert AIMetadataKeys.GENERATION_STARTED_AT in metadata


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_set_success(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = table.get_model()
    row = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    AIFieldMetadataHandler.set_success(model, row.id, ai_field.id)

    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

    assert metadata is not None
    assert metadata[AIMetadataKeys.STATUS] == AIGenerationStatus.SUCCESS
    assert AIMetadataKeys.GENERATION_STARTED_AT in metadata
    assert AIMetadataKeys.GENERATION_FINISHED_AT in metadata
    assert AIMetadataKeys.ERROR not in metadata


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_set_error(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = table.get_model()
    row = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    AIFieldMetadataHandler.set_error(
        model, row.id, ai_field.id, "Test error message", "ValueError"
    )

    row.refresh_from_db()
    metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

    assert metadata is not None
    assert metadata[AIMetadataKeys.STATUS] == AIGenerationStatus.ERROR
    assert AIMetadataKeys.GENERATION_STARTED_AT in metadata
    assert AIMetadataKeys.GENERATION_FINISHED_AT in metadata
    assert AIMetadataKeys.ERROR in metadata
    assert (
        metadata[AIMetadataKeys.ERROR][AIMetadataKeys.ERROR_MESSAGE]
        == "Test error message"
    )
    assert metadata[AIMetadataKeys.ERROR][AIMetadataKeys.ERROR_TYPE] == "ValueError"


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_handler_clear_metadata_for_rows(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = table.get_model()
    row1 = model.objects.create()
    row2 = model.objects.create()
    row3 = model.objects.create()

    AIFieldMetadataHandler.set_generating_for_rows(
        ai_field, [row1.id, row2.id, row3.id]
    )

    row1.refresh_from_db()
    row2.refresh_from_db()
    row3.refresh_from_db()
    assert FieldMetadataHandler.get_metadata(row1, ai_field.id) is not None
    assert FieldMetadataHandler.get_metadata(row2, ai_field.id) is not None
    assert FieldMetadataHandler.get_metadata(row3, ai_field.id) is not None

    AIFieldMetadataHandler.clear_metadata_for_rows(ai_field, [row2.id, row3.id])

    row1.refresh_from_db()
    row2.refresh_from_db()
    row3.refresh_from_db()

    assert FieldMetadataHandler.get_metadata(row1, ai_field.id) is not None
    assert (
        FieldMetadataHandler.get_metadata(row1, ai_field.id)[AIMetadataKeys.STATUS]
        == AIGenerationStatus.GENERATING
    )
    assert FieldMetadataHandler.get_metadata(row2, ai_field.id) is None
    assert FieldMetadataHandler.get_metadata(row3, ai_field.id) is None
