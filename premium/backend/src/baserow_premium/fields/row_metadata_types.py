from typing import Any, Dict, List

from rest_framework import serializers
from rest_framework.fields import Field

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler
from baserow.contrib.database.rows.registries import RowMetadataType

from .ai_field_metadata import AIGenerationStatus, AIMetadataKeys
from .models import AIField


class AIFieldMetadataType(RowMetadataType):
    """
    Row metadata type for AI fields.

    Returns metadata for all AI fields in a table, including generation status,
    timestamps, and error information. Metadata is stored in the field_metadata
    JSONB column and transformed to a readable format for the API.

    Example response structure:
    {
        "row_metadata": {
            "ai_field": {
                "456": {  // field_id
                    "status": "success",
                    "generation_started_at": 1698765432.123,
                    "generation_finished_at": 1698765435.456
                },
                "457": {
                    "status": "error",
                    "generation_started_at": 1698765432.123,
                    "generation_finished_at": 1698765435.456,
                    "error": {
                        "message": "API timeout",
                        "type": "TimeoutError"
                    }
                }
            }
        }
    }
    """

    type = "ai_field"

    def generate_metadata_for_rows(
        self, user, table, row_ids: List[int]
    ) -> Dict[int, Any]:
        """
        Generate AI field metadata for the specified rows.

        :param user: The user requesting the metadata
        :param table: The table containing the rows
        :param row_ids: List of row IDs to generate metadata for
        :return: Dictionary mapping row_id -> {field_id -> metadata}
        """
        # Get all AI fields for this table
        ai_fields = AIField.objects.filter(table=table)

        if not ai_fields.exists():
            return {}

        # Get the table model
        model = table.get_model()

        # Check if metadata column exists
        if not FieldMetadataHandler.is_metadata_enabled(model):
            return {}

        # Fetch all rows
        rows = model.objects.filter(id__in=row_ids)

        result = {}
        for row in rows:
            row_metadata = {}

            for ai_field in ai_fields:
                # Get metadata for this field
                field_metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

                if field_metadata:
                    # Transform short keys to readable format for API
                    readable_metadata = self._transform_metadata_for_api(field_metadata)
                    row_metadata[str(ai_field.id)] = readable_metadata

            if row_metadata:
                result[row.id] = row_metadata

        return result

    def _transform_metadata_for_api(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform internal short-key metadata to readable format for API consumers.

        Storage format: {"s": 2, "gsa": 1234.5, "gfa": 1235.0}
        API format: {"status": "success", "generation_started_at": 1234.5, ...}

        :param metadata: Internal metadata with short keys
        :return: Readable metadata for API
        """
        result = {}

        # Status
        if AIMetadataKeys.STATUS in metadata:
            status_value = metadata[AIMetadataKeys.STATUS]
            status_enum = AIGenerationStatus(status_value)
            # Convert enum to lowercase string (e.g., "GENERATING" -> "generating")
            result["status"] = status_enum.name.lower()

        # Timestamps
        if AIMetadataKeys.GENERATION_STARTED_AT in metadata:
            result["generation_started_at"] = metadata[AIMetadataKeys.GENERATION_STARTED_AT]

        if AIMetadataKeys.GENERATION_FINISHED_AT in metadata:
            result["generation_finished_at"] = metadata[AIMetadataKeys.GENERATION_FINISHED_AT]

        # Error details
        if AIMetadataKeys.ERROR in metadata:
            error_data = metadata[AIMetadataKeys.ERROR]
            result["error"] = {
                "message": error_data.get(AIMetadataKeys.ERROR_MESSAGE),
                "type": error_data.get(AIMetadataKeys.ERROR_TYPE),
            }

        return result

    def get_example_serializer_field(self) -> Field:
        """
        Return example serializer field for API documentation.

        The field represents a dictionary mapping field_id -> metadata.
        """
        return serializers.DictField(
            child=serializers.DictField(
                child=serializers.JSONField(),
                help_text="AI field metadata keyed by field ID",
            ),
            help_text=(
                "Metadata for all AI fields in this row. Each AI field's metadata "
                "includes status (pending/generating/success/error), timestamps, "
                "and error information if applicable."
            ),
            required=False,
        )
