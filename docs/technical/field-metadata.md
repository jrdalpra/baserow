# Field Metadata System

## Overview

The field metadata system provides a way to store and manage per-field, per-row metadata in Baserow tables. This metadata is stored separately from the actual field values and is used to track additional information about fields that doesn't belong in the primary data model.

**Primary use case**: Tracking AI field generation status (pending, generating, success, error) with timestamps and error details.

## Architecture

### Storage Layer

#### Database Schema

Metadata is stored in a JSONB column named `field_metadata` on each table:

```sql
ALTER TABLE database_table_123
ADD COLUMN field_metadata JSONB NOT NULL DEFAULT '{}';

CREATE INDEX database_table_123_field_metadata_gin
ON database_table_123 USING GIN (field_metadata);
```

**Structure**:
```json
{
  "456": {  // field_id as string
    "s": 1,  // status: 0=pending, 1=generating, 2=success, 3=error
    "gsa": 1762348609.808954,  // generation_started_at (unix timestamp)
    "gfa": 1762348635.456789   // generation_finished_at (unix timestamp)
  },
  "457": {
    "s": 3,  // error status
    "gsa": 1762348610.123456,
    "gfa": 1762348612.789012,
    "e": {  // error object (only present when status=error)
      "m": "API timeout",  // message
      "t": "TimeoutError"  // type
    }
  }
}
```

**Key design decisions**:
- Field IDs are stored as strings (JSON requirement)
- Short keys used for space efficiency
- JSONB allows efficient querying with GIN indexes
- Default empty object avoids NULL handling

#### Column Management

The `field_metadata` column is added on-demand via migration:

```python
from baserow.contrib.database.fields.metadata_handler import FieldMetadataHandler

# Check if enabled
if FieldMetadataHandler.is_metadata_enabled(model):
    # Column exists, safe to use

# Ensure column exists (for tests/migrations)
model = FieldMetadataHandler.ensure_metadata_column_exists(table)
```

**Table model tracking**: The `Table` model has a `field_metadata_column_added` boolean flag to track which tables have the column.

### Core Components

#### 1. FieldMetadataHandler

**Location**: `backend/src/baserow/contrib/database/fields/metadata_handler.py`

Generic handler providing CRUD operations for field metadata:

- `get_metadata(row, field_id)` - Read metadata for a specific field
- `set_metadata(model, row_id, field_id, metadata, merge=True)` - Write metadata atomically
- `bulk_set_metadata(model, updates)` - Update multiple rows efficiently
- `delete_field_metadata(model, field_id)` - Remove metadata when field is deleted
- `get_rows_by_metadata_status(model, field_id, status)` - Query rows by metadata value

**Key feature**: Uses PostgreSQL's `jsonb_set` function for atomic updates, avoiding race conditions.

See the file for complete implementation details and method signatures.

#### 2. Field-Specific Handlers

Field types can implement handlers with domain-specific logic.

**Example: AIFieldMetadataHandler**

**Location**: `premium/backend/src/baserow_premium/fields/ai_field_metadata.py`

Provides AI-specific methods:
- `set_generating(model, row_id, field_id)` - Mark as generating
- `set_success(model, row_id, field_id)` - Mark as successful
- `set_error(model, row_id, field_id, error_message, error_type)` - Mark as failed

See the file for implementation details including status enums, metadata keys, and timestamp preservation.

### API Integration

#### Row Metadata Registry

**Location**: `backend/src/baserow/contrib/database/rows/registries.py`

The `row_metadata_registry` provides a plugin system for exposing metadata via the API.

**Implementation example**: `premium/backend/src/baserow_premium/fields/row_metadata_types.py`

The `AIFieldMetadataType` class:
1. Extends `RowMetadataType` base class
2. Implements `generate_metadata_for_rows(user, table, row_ids)` - fetches metadata from database
3. Implements `_transform_metadata_for_api(metadata)` - converts short keys to readable format
4. Implements `get_example_serializer_field()` - provides API documentation

**Registration**: In app's `ready()` method (`premium/backend/src/baserow_premium/apps.py`):
```python
row_metadata_registry.register(AIFieldMetadataType())
```

#### API Usage

Metadata is opt-in via the `?include=row_metadata` query parameter:

**Grid view request**:
```
GET /api/database/views/grid/123/?include=row_metadata
```

**Response**:
```json
{
  "count": 10,
  "results": [
    {
      "id": 456,
      "field_789": "Generated text value"
    }
  ],
  "row_metadata": {
    "456": {
      "ai_field": {
        "789": {
          "status": "success",
          "generation_started_at": 1762348609.808954,
          "generation_finished_at": 1762348635.456789
        }
      },
      "row_comment_count": 3
    }
  }
}
```

**Supported endpoints**:
- Grid view: `GET /api/database/views/grid/{view_id}/`
- Gallery view: `GET /api/database/views/gallery/{view_id}/`
- Kanban view: `GET /api/database/views/kanban/{view_id}/` (premium)
- Calendar view: `GET /api/database/views/calendar/{view_id}/` (premium)
- Timeline view: `GET /api/database/views/timeline/{view_id}/` (premium)

All use `@allowed_includes("field_options", "row_metadata")` decorator.

### Real-time Updates

#### Websocket Messages

The system provides real-time metadata updates via websockets.

**New signal**: `rows_metadata_updated` in `backend/src/baserow/contrib/database/rows/signals.py`

**Implementation**: `backend/src/baserow/contrib/database/ws/rows/signals.py`

The signal handler:
1. Listens for `rows_metadata_updated` signal
2. Fetches latest metadata from database via `row_metadata_registry`
3. Broadcasts `rows_metadata_updated` websocket message with metadata
4. Uses `transaction.on_commit()` to ensure consistency

**Usage example**: `premium/backend/src/baserow_premium/fields/tasks.py`

Send the signal when metadata changes:
```python
from baserow.contrib.database.rows.signals import rows_metadata_updated

rows_metadata_updated.send(
    sender=self,
    table=table,
    row_ids=[row.id],
    user=user,
)
```

#### Websocket Message Flow

**Scenario: AI field generation**

1. **User triggers generation** (API call)
   ```
   POST /api/database/fields/789/generate-ai-values/
   ```
   - Returns `HTTP 202 ACCEPTED`
   - Celery task enqueued

2. **Task starts, metadata updated to "generating"**
   ```python
   AIFieldMetadataHandler.set_generating(model, row.id, field.id)
   rows_metadata_updated.send(...)
   ```

   **Websocket broadcast**:
   ```json
   {
     "type": "rows_metadata_updated",
     "table_id": 100,
     "row_ids": [456],
     "metadata": {
       "456": {
         "ai_field": {
           "789": {
             "status": "generating",
             "generation_started_at": 1762348609.808954
           }
         }
       }
     }
   }
   ```

3. **AI generates value** (5-30 seconds)

4. **Task completes successfully**
   ```python
   with transaction.atomic():
       AIFieldMetadataHandler.set_success(model, row.id, field.id)
       RowHandler().update_row_by_id(...)  # Triggers rows_updated signal
   ```

   **Websocket broadcast** (via existing `rows_updated` signal):
   ```json
   {
     "type": "rows_updated",
     "table_id": 100,
     "rows": [{"id": 456, "field_789": "Generated text..."}],
     "metadata": {
       "456": {
         "ai_field": {
           "789": {
             "status": "success",
             "generation_started_at": 1762348609.808954,
             "generation_finished_at": 1762348635.456789
           }
         }
       }
     },
     "updated_field_ids": [789]
   }
   ```

5. **On error**
   ```python
   AIFieldMetadataHandler.set_error(model, row.id, field.id, str(exc), type(exc).__name__)
   rows_metadata_updated.send(...)
   ```

   **Websocket broadcast**:
   ```json
   {
     "type": "rows_metadata_updated",
     "table_id": 100,
     "row_ids": [456],
     "metadata": {
       "456": {
         "ai_field": {
           "789": {
             "status": "error",
             "generation_started_at": 1762348609.808954,
             "generation_finished_at": 1762348612.789012,
             "error": {
               "message": "API timeout",
               "type": "TimeoutError"
             }
           }
         }
       }
     }
   }
   ```

#### Message Type Comparison

| Event | Signal | Includes Row Values | Includes Metadata | Use Case |
|-------|--------|---------------------|-------------------|----------|
| `rows_created` | `rows_created` | ✅ Yes | ✅ Yes | New row added |
| `rows_updated` | `rows_updated` | ✅ Yes | ✅ Yes | Row values changed |
| `rows_deleted` | `rows_deleted` | ✅ Yes | ❌ No | Row deleted |
| `rows_metadata_updated` | `rows_metadata_updated` | ❌ No | ✅ Yes | **Metadata changed without value change** |

**Key insight**: `rows_metadata_updated` is for metadata-only changes, avoiding unnecessary row value serialization and frontend re-renders.

## Implementation Example: AI Field Generation

### Complete Lifecycle

**Reference implementation**: `premium/backend/src/baserow_premium/fields/tasks.py`

The AI field generation task (`generate_ai_values_for_rows`) demonstrates the complete metadata lifecycle:

1. **Check metadata availability**: Verify table has metadata column using `FieldMetadataHandler.is_metadata_enabled()`

2. **Mark as generating**:
   - Call `AIFieldMetadataHandler.set_generating()`
   - Send `rows_metadata_updated` signal for real-time notification

3. **Generate AI value**: Call generative AI model

4. **Mark as success** (on completion):
   - Wrap in `transaction.atomic()` block
   - Call `AIFieldMetadataHandler.set_success()` BEFORE updating row
   - Call `RowHandler().update_row_by_id()` which triggers `rows_updated` signal

5. **Mark as error** (on exception):
   - Call `AIFieldMetadataHandler.set_error()` with error details
   - Send `rows_metadata_updated` signal for real-time notification

**Critical detail**: Success metadata must be set **before** `update_row_by_id()` within the same transaction. This ensures the `rows_updated` signal includes the correct metadata state.

## Use Cases

### Current: AI Field Generation Status

- Track when AI generation starts, completes, or fails
- Display loading spinners in UI
- Show error messages to users
- Support page refresh (metadata persists in database)
- Real-time collaboration (other users see generation status)

### Future Possibilities

The metadata system can be extended to support various use cases:

#### Validation State
Track field validation status (validating → valid/invalid) with error details and timestamps.

#### Computation Cache
Store computation status and cache keys for expensive field calculations, enabling smart cache invalidation.

#### Import/Sync Status
Track synchronization with external systems (syncing → synced/failed) including source information and last sync timestamps.

#### Data Quality Metrics
Store data quality scores, completeness metrics, or confidence levels for fields that aggregate or derive information.

Each use case would follow the same pattern as `AIFieldMetadataHandler`:
1. Define status enum and metadata keys
2. Create handler class with state management methods
3. Implement `RowMetadataType` for API exposure
4. Send `rows_metadata_updated` signals for real-time updates

## Design Patterns

### 1. Graceful Degradation

Always check if metadata is enabled before using:

```python
if FieldMetadataHandler.is_metadata_enabled(model):
    # Safe to use metadata
    AIFieldMetadataHandler.set_generating(model, row.id, field.id)
else:
    # Column doesn't exist yet, skip metadata
    pass
```

### 2. Short Keys for Storage

Use verbose names in code, short keys in storage:

```python
class MyMetadataKeys:
    STATUS = "s"           # Not "status"
    TIMESTAMP = "ts"       # Not "timestamp"
    ERROR_MESSAGE = "em"   # Not "error_message"

# In code (readable)
metadata = {
    MyMetadataKeys.STATUS: "processing",
    MyMetadataKeys.TIMESTAMP: timezone.now().timestamp(),
}

# In database (compact)
{"s": "processing", "ts": 1762348609.808954}
```

### 3. Atomic Transactions for Consistency

When updating both row values and metadata, use a transaction:

```python
with transaction.atomic():
    # Update metadata first
    FieldMetadataHandler.set_metadata(...)

    # Then update row (this triggers signals)
    RowHandler().update_row_by_id(...)

# Both committed together, signal fires with correct metadata
```

### 4. Preserve Existing Metadata

When updating status, preserve timestamps:

```python
# Read existing metadata
existing = FieldMetadataHandler.get_metadata(row, field_id) or {}

# Merge with new data
metadata = {
    **existing,  # Preserve old fields
    MyMetadataKeys.STATUS: "completed",
    MyMetadataKeys.FINISHED_AT: timezone.now().timestamp(),
}

FieldMetadataHandler.set_metadata(model, row_id, field_id, metadata, merge=False)
```

## Performance Considerations

### Database Queries

- **GIN indexes** on JSONB columns enable fast queries
- **Atomic updates** via `jsonb_set` avoid race conditions
- **Bulk operations** available for multi-row updates

### API Performance

- **Opt-in metadata**: Only loaded when `?include=row_metadata` is specified
- **Registry pattern**: Multiple metadata types can coexist efficiently
- **Single query**: All metadata types fetched in one pass

### Websocket Performance

- **Deferred broadcasting**: Uses `transaction.on_commit()` to ensure data consistency
- **Targeted updates**: Only affected rows notified
- **Lightweight messages**: Metadata-only updates skip row value serialization


## Known Limitations

The field metadata system is currently in its initial implementation phase. The following limitations exist:

### Not Yet Supported

1. **Undo/Redo**: Metadata changes are not tracked by the undo/redo system
   - Undoing a row update will not restore previous metadata
   - Metadata changes happen outside the action history tracking

2. **Import/Export**: Metadata is not included in table exports
   - CSV/JSON/XML exports only contain field values, not metadata
   - Importing data will not restore metadata from previous exports
   - Duplicating tables/rows will not copy metadata

3. **Snapshots**: Metadata is not included in table snapshots
   - Restoring a snapshot will not restore metadata states
   - Metadata is treated as ephemeral, not part of the data model

4. **Field Duplication**: When duplicating fields, metadata is not copied
   - New field instances start with empty metadata
   - Historical metadata from original field is not transferred

5. **Row History**: Metadata changes are not tracked in row history
   - Viewing historical row versions will not show metadata at that time
   - Only current metadata state is available

6. **Webhooks**: Metadata changes may not trigger all expected webhooks
   - The `rows_metadata_updated` signal is separate from `rows_updated`
   - Existing webhook filters may not capture metadata-only changes


### Design Considerations

- **Ephemeral nature**: Metadata is intentionally designed as supplementary information that tracks current state, not historical data

### When to Use Metadata vs. Regular Fields

**Use metadata for**:
- Temporary state (generation status, validation state)
- System-generated information (timestamps, error messages)
- UI-only information that doesn't need to be exported
- Information that changes frequently and doesn't need history

## Summary

The field metadata system provides:

1. **Flexible storage** via JSONB column
2. **Type-safe access** via handler classes
3. **API integration** via registry pattern
4. **Real-time updates** via websocket signals
5. **Efficient querying** via GIN indexes
6. **Atomic operations** via PostgreSQL functions
7. **Extensible design** for future metadata types

The system is currently used for AI field generation status tracking but can be extended to support validation states, computation caching, sync status, and other per-field, per-row metadata needs.
