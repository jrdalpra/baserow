from typing import Any, Dict, List

from django.utils import timezone

from rest_framework import serializers
from rest_framework.fields import Field

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler
from baserow.contrib.database.rows.registries import RowMetadataType

from .ai_field_metadata import AIGenerationStatus, AIMetadataKeys
from .models import AIField


class AIFieldMetadataType(RowMetadataType):
    """
    Row metadata type for AI fields.

    Returns metadata for all AI fields in a table, showing status as a single
    letter for error/generating states. Metadata is stored in the field_metadata
    JSONB column and transformed to a simplified format for the API.

    Example response structure:
    {
        "row_metadata": {
            "ai_field": {
                "456": "g",  // field_id: status letter (g = generating)
                "457": "e"   // field_id: status letter (e = error)
            }
        }
    }

    Status letters:
    - "g": generating
    - "e": error (only shown for a limited time after error occurs)

    Success and pending states are not included in the response.
    """

    type = "ai_field"
    # Time in seconds after which error status is no longer shown (1 hour)
    ERROR_EXPIRATION_SECONDS = 3600

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

        ai_fields = AIField.objects.filter(table=table)

        if not ai_fields.exists():
            return {}

        model = table.get_model()

        if not FieldMetadataHandler.is_metadata_enabled(model):
            return {}

        rows = model.objects.filter(id__in=row_ids).only(
            "id", FieldMetadataHandler.METADATA_COLUMN
        )

        result = {}
        for row in rows:
            row_metadata = {}

            for ai_field in ai_fields:
                field_metadata = FieldMetadataHandler.get_metadata(row, ai_field.id)

                if field_metadata:
                    status_letter = self._transform_metadata_for_api(field_metadata)
                    # Only add to result if there's a status letter to show
                    if status_letter:
                        row_metadata[str(ai_field.id)] = status_letter

            if row_metadata:
                result[row.id] = row_metadata

        return result

    def _transform_metadata_for_api(self, metadata: Dict[str, Any]) -> str:
        """
        Transform internal short-key metadata to a single status letter for API.

        Only returns a status letter for generating or error states.
        Error state is only returned if it occurred within ERROR_EXPIRATION_SECONDS.

        Storage format: {"s": 1, "gsa": 1234.5}
        API format: "g" (single letter)

        :param metadata: Internal metadata with short keys
        :return: Single letter status ("g" for generating, "e" for error) or None
        """

        if AIMetadataKeys.STATUS not in metadata:
            return None

        status_value = metadata[AIMetadataKeys.STATUS]
        status_enum = AIGenerationStatus(status_value)

        # Only return status for generating or error states
        if status_enum == AIGenerationStatus.GENERATING:
            return "g"
        elif status_enum == AIGenerationStatus.ERROR:
            generation_finished_at = metadata.get(AIMetadataKeys.GENERATION_FINISHED_AT)
            if generation_finished_at:
                current_time = timezone.now().timestamp()
                time_since_error = current_time - generation_finished_at

                if time_since_error <= self.ERROR_EXPIRATION_SECONDS:
                    return "e"

            # Error has expired or no timestamp, don't show it
            return None

        # Success or pending states are not shown
        return None

    def get_example_serializer_field(self) -> Field:
        """
        Return example serializer field for API documentation.

        The field represents a dictionary mapping field_id -> single status letter.
        """

        return serializers.DictField(
            child=serializers.CharField(),
            help_text=(
                "AI field status indicators keyed by field ID. "
                "Values are single letters: 'g' (generating), 'e' (error). "
                "Only fields with generating or recent error status are included. "
                "Errors expire after 1 hour."
            ),
            required=False,
        )
