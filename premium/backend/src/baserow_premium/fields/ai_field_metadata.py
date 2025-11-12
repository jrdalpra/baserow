from enum import IntEnum
from typing import TYPE_CHECKING

from django.contrib.auth.models import AbstractUser
from django.utils import timezone

from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler

if TYPE_CHECKING:
    from baserow_premium.fields.models import AIField

    from baserow.contrib.database.table.models import GeneratedTableModel


class AIGenerationStatus(IntEnum):
    """
    Status values for AI field generation.

    Values are stored as integers in the metadata to save space.
    """

    PENDING = 0
    GENERATING = 1
    SUCCESS = 2
    ERROR = 3


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

    STATUS = "s"

    GENERATION_STARTED_AT = "gsa"
    GENERATION_FINISHED_AT = "gfa"

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

        row = model.objects.get(id=row_id)
        existing = FieldMetadataHandler.get_metadata(row, field_id) or {}

        metadata = {
            **existing,
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

    @classmethod
    def set_generating_for_rows(
        cls,
        ai_field: "AIField",
        row_ids: list[int],
    ):
        """
        Set generating status for multiple rows in the database using a single
        UPDATE statement.

        :param ai_field: The AI field
        :param row_ids: List of row IDs being generated
        :return: True if metadata was set, False if metadata is disabled
        """

        model = ai_field.table.get_model()

        if not FieldMetadataHandler.is_metadata_enabled(model):
            return False

        timestamp = timezone.now().timestamp()
        updates = [
            {
                "row_id": row_id,
                "field_id": ai_field.id,
                "metadata": {
                    AIMetadataKeys.STATUS: AIGenerationStatus.GENERATING,
                    AIMetadataKeys.GENERATION_STARTED_AT: timestamp,
                },
            }
            for row_id in row_ids
        ]
        FieldMetadataHandler.bulk_set_metadata(model, updates)

        return True

    @classmethod
    def broadcast_generation_started(
        cls,
        ai_field: "AIField",
        row_ids: list[int],
        user: AbstractUser,
    ):
        """
        Broadcast metadata update to all connected clients when generation starts.

        This should be called AFTER setting metadata in the database and BEFORE
        dispatching the generation task. This ensures other users/windows see
        the generating status immediately.

        :param ai_field: The AI field
        :param row_ids: List of row IDs being generated
        :param user: The user who triggered the generation
        """

        from baserow.contrib.database.rows.registries import row_metadata_registry
        from baserow.ws.registries import page_registry

        table = ai_field.table
        table_page_type = page_registry.get("table")
        table_page_type.broadcast(
            {
                "type": "rows_metadata_updated",
                "table_id": table.id,
                "row_ids": row_ids,
                "metadata": row_metadata_registry.generate_and_merge_metadata_for_rows(
                    user, table, row_ids
                ),
            },
            getattr(user, "web_socket_id", None),
            table_id=table.id,
        )
