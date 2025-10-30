from enum import IntEnum
from typing import TYPE_CHECKING, Optional

from django.utils import timezone

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler

if TYPE_CHECKING:
    from baserow.contrib.database.table.models import GeneratedTableModel


class AIGenerationStatus(IntEnum):
    """
    Status values for AI field generation.

    Values are stored as integers in the metadata to save space.
    """

    PENDING = 0  # Waiting for generation
    GENERATING = 1  # Currently generating
    SUCCESS = 2  # Successfully generated
    ERROR = 3  # Generation failed


class AIMetadataKeys:
    """
    Defines metadata keys with short storage names for space efficiency.

    Usage in code:
        metadata = {
            AIMetadataKeys.STATUS: AIGenerationStatus.SUCCESS,
            AIMetadataKeys.GENERATION_STARTED_AT: timestamp,
        }

    Storage format (short keys):
        {"s": 2, "gsa": 1698765432.123}
    """

    # Status (single letter for most frequently used)
    STATUS = "s"

    # Timestamps (shortened abbreviations)
    GENERATION_STARTED_AT = "gsa"
    GENERATION_FINISHED_AT = "gfa"

    # Error information (nested under "e")
    ERROR = "e"
    ERROR_MESSAGE = "m"
    ERROR_TYPE = "t"


class AIFieldMetadataHandler:
    """
    Metadata handler for AI fields.

    Tracks AI generation lifecycle:
    - generation_started_at: When generation started
    - generation_finished_at: When generation completed
    - status: Current status (AIGenerationStatus enum value)
    - error: Error details (only present if status=ERROR)

    This handler provides utility methods for managing AI field metadata
    during the generation process.
    """

    @classmethod
    def set_generating(
        cls,
        model: type["GeneratedTableModel"],
        row_id: int,
        field_id: int,
    ):
        """
        Mark an AI field as currently generating.

        This should be called when AI generation starts.

        :param model: The generated table model
        :param row_id: The row ID
        :param field_id: The AI field ID
        """
        metadata = {
            AIMetadataKeys.STATUS: AIGenerationStatus.GENERATING,
            AIMetadataKeys.GENERATION_STARTED_AT: timezone.now().timestamp(),
        }
        FieldMetadataHandler.set_metadata(model, row_id, field_id, metadata)

    @classmethod
    def set_success(
        cls,
        model: type["GeneratedTableModel"],
        row_id: int,
        field_id: int,
    ):
        """
        Mark an AI field as successfully generated.

        :param model: The generated table model
        :param row_id: The row ID
        :param field_id: The AI field ID
        """
        # Get existing metadata to preserve generation_started_at
        row = model.objects.get(id=row_id)
        existing = FieldMetadataHandler.get_metadata(row, field_id) or {}

        metadata = {
            **existing,  # Preserve existing fields (like generation_started_at)
            AIMetadataKeys.STATUS: AIGenerationStatus.SUCCESS,
            AIMetadataKeys.GENERATION_FINISHED_AT: timezone.now().timestamp(),
        }
        FieldMetadataHandler.set_metadata(
            model, row_id, field_id, metadata, merge=False
        )

    @classmethod
    def set_error(
        cls,
        model: type["GeneratedTableModel"],
        row_id: int,
        field_id: int,
        error_message: str,
        error_type: str,
    ):
        """
        Mark an AI field as failed with an error.

        :param model: The generated table model
        :param row_id: The row ID
        :param field_id: The AI field ID
        :param error_message: Error message from the exception
        :param error_type: Type/class name of the error
        """
        # Get existing metadata to preserve generation_started_at
        row = model.objects.get(id=row_id)
        existing = FieldMetadataHandler.get_metadata(row, field_id) or {}

        metadata = {
            **existing,  # Preserve existing fields (like generation_started_at)
            AIMetadataKeys.STATUS: AIGenerationStatus.ERROR,
            AIMetadataKeys.GENERATION_FINISHED_AT: timezone.now().timestamp(),
            AIMetadataKeys.ERROR: {
                AIMetadataKeys.ERROR_MESSAGE: error_message,
                AIMetadataKeys.ERROR_TYPE: error_type,
            },
        }
        FieldMetadataHandler.set_metadata(
            model, row_id, field_id, metadata, merge=False
        )
