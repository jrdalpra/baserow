import pytest
from baserow_premium.fields.ai_field_metadata import (
    AIFieldMetadataHandler,
    AIGenerationStatus,
)

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler
from baserow.contrib.database.rows.registries import row_metadata_registry


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_registered(premium_data_fixture):
    metadata_type = row_metadata_registry.get("ai_field")
    assert metadata_type is not None
    assert metadata_type.type == "ai_field"


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_no_ai_fields(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    metadata_type = row_metadata_registry.get("ai_field")
    result = metadata_type.generate_metadata_for_rows(user, table, [row.id])

    assert result == {}


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_no_metadata_column(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")
    model = table.get_model()
    row = model.objects.create()

    metadata_type = row_metadata_registry.get("ai_field")
    result = metadata_type.generate_metadata_for_rows(user, table, [row.id])

    assert result == {}


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_single_field(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row.id, ai_field.id)

    metadata_type = row_metadata_registry.get("ai_field")
    result = metadata_type.generate_metadata_for_rows(user, table, [row.id])

    assert row.id in result
    assert str(ai_field.id) in result[row.id]

    field_metadata = result[row.id][str(ai_field.id)]
    assert field_metadata["status"] == "generating"
    assert "generation_started_at" in field_metadata
    assert "error" not in field_metadata


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_multiple_fields(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field1 = premium_data_fixture.create_ai_field(table=table, name="AI 1")
    ai_field2 = premium_data_fixture.create_ai_field(table=table, name="AI 2")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row.id, ai_field1.id)
    AIFieldMetadataHandler.set_generating(model, row.id, ai_field2.id)
    AIFieldMetadataHandler.set_success(model, row.id, ai_field2.id)

    metadata_type = row_metadata_registry.get("ai_field")
    result = metadata_type.generate_metadata_for_rows(user, table, [row.id])

    assert row.id in result
    assert str(ai_field1.id) in result[row.id]
    assert str(ai_field2.id) in result[row.id]

    field1_metadata = result[row.id][str(ai_field1.id)]
    assert field1_metadata["status"] == "generating"
    assert "generation_started_at" in field1_metadata

    field2_metadata = result[row.id][str(ai_field2.id)]
    assert field2_metadata["status"] == "success"
    assert "generation_started_at" in field2_metadata
    assert "generation_finished_at" in field2_metadata


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_multiple_rows(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row1 = model.objects.create()
    row2 = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row1.id, ai_field.id)
    AIFieldMetadataHandler.set_error(
        model, row2.id, ai_field.id, "Test error", "ValueError"
    )

    metadata_type = row_metadata_registry.get("ai_field")
    result = metadata_type.generate_metadata_for_rows(user, table, [row1.id, row2.id])

    assert row1.id in result
    assert row2.id in result

    assert result[row1.id][str(ai_field.id)]["status"] == "generating"

    row2_metadata = result[row2.id][str(ai_field.id)]
    assert row2_metadata["status"] == "error"
    assert "error" in row2_metadata
    assert row2_metadata["error"]["message"] == "Test error"
    assert row2_metadata["error"]["type"] == "ValueError"


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_status_transformation(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)

    metadata_type = row_metadata_registry.get("ai_field")

    statuses = [
        (AIGenerationStatus.PENDING, "pending"),
        (AIGenerationStatus.GENERATING, "generating"),
        (AIGenerationStatus.SUCCESS, "success"),
        (AIGenerationStatus.ERROR, "error"),
    ]

    for status_enum, expected_string in statuses:
        row = model.objects.create()

        FieldMetadataHandler.set_metadata(
            model, row.id, ai_field.id, {"s": status_enum}
        )

        result = metadata_type.generate_metadata_for_rows(user, table, [row.id])

        assert result[row.id][str(ai_field.id)]["status"] == expected_string


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_no_metadata_for_field(premium_data_fixture):
    user = premium_data_fixture.create_user()
    table = premium_data_fixture.create_database_table(user=user)
    ai_field = premium_data_fixture.create_ai_field(table=table, name="AI")

    model = FieldMetadataHandler.ensure_metadata_column_exists(table)
    row_with_metadata = model.objects.create()
    row_without_metadata = model.objects.create()

    AIFieldMetadataHandler.set_generating(model, row_with_metadata.id, ai_field.id)

    metadata_type = row_metadata_registry.get("ai_field")
    result = metadata_type.generate_metadata_for_rows(
        user, table, [row_with_metadata.id, row_without_metadata.id]
    )

    assert row_with_metadata.id in result
    assert row_without_metadata.id not in result


@pytest.mark.django_db
@pytest.mark.field_ai
def test_ai_field_metadata_type_serializer_field(premium_data_fixture):
    metadata_type = row_metadata_registry.get("ai_field")
    serializer_field = metadata_type.get_example_serializer_field()

    assert serializer_field is not None
    assert hasattr(serializer_field, "help_text")
    assert "AI field" in serializer_field.help_text
