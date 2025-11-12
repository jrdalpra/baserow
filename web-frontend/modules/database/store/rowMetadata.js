import { GRID_VIEW_BUFFER_REQUEST_SIZE } from '@baserow/modules/database/constants'

/**
 * Row Metadata Store
 *
 * Manages field metadata for rows, particularly for tracking AI field generation
 * status and other field-level metadata that's stored separately from field values.
 *
 * Metadata structure in state:
 * {
 *   [tableId]: {
 *     [rowId]: {
 *       ai_field: {
 *         [fieldId]: {
 *           status: 'pending' | 'generating' | 'success' | 'error',
 *           generation_started_at: number,
 *           generation_finished_at: number,
 *           error: { message: string, type: string }
 *         }
 *       },
 *       // ... other metadata types can be added here
 *     }
 *   }
 * }
 */

const MAX_ROWS_PER_TABLE = GRID_VIEW_BUFFER_REQUEST_SIZE * 5

export const state = () => ({
  // Metadata indexed by tableId -> rowId -> metadata type -> fieldId -> metadata
  metadata: {},
  loadedTables: new Set(),
  // Track access order for LRU cache: tableId -> [rowId1, rowId2, ...]
  // Most recently accessed rows are at the end
  accessOrder: {},
})

export const mutations = {
  /**
   * Update access order for LRU cache and prune old entries if needed
   * @param {Object} state - Vuex state
   * @param {number} tableId - Table ID
   * @param {Array<number>} rowIds - Row IDs being accessed
   */
  _updateAccessOrder(state, { tableId, rowIds }) {
    if (!state.accessOrder[tableId]) {
      state.accessOrder[tableId] = []
    }

    const order = state.accessOrder[tableId]
    const rowIdStrings = rowIds.map(String)

    // Remove these row IDs from their current positions
    state.accessOrder[tableId] = order.filter(
      (id) => !rowIdStrings.includes(id)
    )

    // Add them to the end (most recently used)
    state.accessOrder[tableId].push(...rowIdStrings)

    // If we exceed the limit, remove oldest entries
    if (state.accessOrder[tableId].length > MAX_ROWS_PER_TABLE) {
      const toRemoveCount =
        state.accessOrder[tableId].length - MAX_ROWS_PER_TABLE
      const rowsToRemove = state.accessOrder[tableId].splice(0, toRemoveCount)

      // Remove metadata for evicted rows
      if (state.metadata[tableId]) {
        rowsToRemove.forEach((rowId) => {
          delete state.metadata[tableId][rowId]
        })
      }
    }
  },

  /**
   * Set metadata for multiple rows in a table
   * @param {Object} state - Vuex state
   * @param {number} tableId - Table ID
   * @param {Object} metadata - Metadata object keyed by rowId
   */
  SET_ROW_METADATA(state, { tableId, metadata }) {
    if (!state.metadata[tableId]) {
      state.metadata[tableId] = {}
    }

    const rowIds = Object.keys(metadata).map(Number)

    Object.entries(metadata).forEach(([rowId, rowMetadata]) => {
      if (!state.metadata[tableId][rowId]) {
        state.metadata[tableId][rowId] = {}
      }

      // Deep merge metadata for each row
      Object.entries(rowMetadata).forEach(([metadataType, typeData]) => {
        if (!state.metadata[tableId][rowId][metadataType]) {
          state.metadata[tableId][rowId][metadataType] = {}
        }
        Object.assign(state.metadata[tableId][rowId][metadataType], typeData)
      })
    })

    // Update LRU access order and prune if needed
    this.commit('rowMetadata/_updateAccessOrder', { tableId, rowIds })

    // Force reactivity
    state.metadata = { ...state.metadata }
  },

  /**
   * Update metadata for a specific field in a row
   * @param {Object} state - Vuex state
   * @param {number} tableId - Table ID
   * @param {number} rowId - Row ID
   * @param {string} metadataType - Type of metadata (e.g., 'ai_field')
   * @param {number} fieldId - Field ID
   * @param {Object} metadata - Metadata object
   */
  UPDATE_FIELD_METADATA(
    state,
    { tableId, rowId, metadataType, fieldId, metadata }
  ) {
    if (!state.metadata[tableId]) {
      state.metadata[tableId] = {}
    }
    if (!state.metadata[tableId][rowId]) {
      state.metadata[tableId][rowId] = {}
    }
    if (!state.metadata[tableId][rowId][metadataType]) {
      state.metadata[tableId][rowId][metadataType] = {}
    }

    state.metadata[tableId][rowId][metadataType][fieldId] = metadata

    // Update LRU access order for this single row
    this.commit('rowMetadata/_updateAccessOrder', { tableId, rowIds: [rowId] })

    state.metadata = { ...state.metadata }
  },

  /**
   * Clear all metadata for a specific table
   * @param {Object} state - Vuex state
   * @param {number} tableId - Table ID
   */
  CLEAR_TABLE_METADATA(state, { tableId }) {
    delete state.metadata[tableId]
    delete state.accessOrder[tableId]
    state.loadedTables.delete(tableId)

    state.metadata = { ...state.metadata }
  },

  /**
   * Clear metadata for specific rows in a table
   * @param {Object} state - Vuex state
   * @param {number} tableId - Table ID
   * @param {Array<number>} rowIds - Array of row IDs to clear
   */
  CLEAR_ROWS_METADATA(state, { tableId, rowIds }) {
    if (!state.metadata[tableId]) {
      return
    }

    const rowIdStrings = rowIds.map(String)

    rowIds.forEach((rowId) => {
      delete state.metadata[tableId][rowId]
    })

    // Remove from access order tracking
    if (state.accessOrder[tableId]) {
      state.accessOrder[tableId] = state.accessOrder[tableId].filter(
        (id) => !rowIdStrings.includes(id)
      )
    }

    state.metadata = { ...state.metadata }
  },

  /**
   * Mark a table as having loaded metadata
   * @param {Object} state - Vuex state
   * @param {number} tableId - Table ID
   */
  MARK_TABLE_LOADED(state, { tableId }) {
    state.loadedTables.add(tableId)
  },
}

export const actions = {
  /**
   * Handle websocket metadata update
   * Called when rows_metadata_updated websocket message is received
   * @param {Object} context - Vuex context
   * @param {number} tableId - Table ID
   * @param {Array<number>} rowIds - Array of row IDs that were updated
   * @param {Object} metadata - Metadata object keyed by rowId
   */
  handleWebsocketUpdate({ commit }, { tableId, rowIds, metadata }) {
    commit('SET_ROW_METADATA', { tableId, metadata })
  },

  /**
   * Update metadata from rows_created or rows_updated websocket messages
   * These messages can optionally include metadata
   * @param {Object} context - Vuex context
   * @param {number} tableId - Table ID
   * @param {Object} metadata - Metadata object keyed by rowId
   */
  handleRowsUpdate({ commit }, { tableId, metadata }) {
    if (metadata && Object.keys(metadata).length > 0) {
      commit('SET_ROW_METADATA', { tableId, metadata })
    }
  },

  /**
   * Clear metadata when rows are deleted
   * @param {Object} context - Vuex context
   * @param {number} tableId - Table ID
   * @param {Array<number>} rowIds - Array of deleted row IDs
   */
  handleRowsDeleted({ commit }, { tableId, rowIds }) {
    commit('CLEAR_ROWS_METADATA', { tableId, rowIds })
  },

  /**
   * Clear all metadata for a table (e.g., when navigating away)
   * @param {Object} context - Vuex context
   * @param {number} tableId - Table ID
   */
  clearTable({ commit }, { tableId }) {
    commit('CLEAR_TABLE_METADATA', { tableId })
  },

  /**
   * Set AI field metadata to generating state
   * This is typically called optimistically when user triggers generation
   * @param {Object} context - Vuex context
   * @param {number} tableId - Table ID
   * @param {number} rowId - Row ID
   * @param {number} fieldId - Field ID
   */
  setAIFieldGenerating({ commit }, { tableId, rowId, fieldId }) {
    commit('UPDATE_FIELD_METADATA', {
      tableId,
      rowId,
      metadataType: 'ai_field',
      fieldId,
      metadata: {
        status: 'generating',
        generation_started_at: Date.now() / 1000, // Unix timestamp
      },
    })
  },
}

export const getters = {
  /**
   * Get all metadata for a specific row
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId) and returns metadata
   */
  getRowMetadata: (state) => (tableId, rowId) => {
    return state.metadata[tableId]?.[rowId] || {}
  },

  /**
   * Get metadata for a specific field in a row
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId, metadataType, fieldId) and returns field metadata
   */
  getFieldMetadata: (state) => (tableId, rowId, metadataType, fieldId) => {
    return state.metadata[tableId]?.[rowId]?.[metadataType]?.[fieldId] || null
  },

  /**
   * Get AI field metadata for a specific field
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId, fieldId) and returns AI field metadata
   */
  getAIFieldMetadata: (state) => (tableId, rowId, fieldId) => {
    return state.metadata[tableId]?.[rowId]?.ai_field?.[fieldId] || null
  },

  /**
   * Get AI field status
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId, fieldId) and returns status string or null
   */
  getAIFieldStatus: (state) => (tableId, rowId, fieldId) => {
    return state.metadata[tableId]?.[rowId]?.ai_field?.[fieldId]?.status || null
  },

  /**
   * Check if an AI field is currently generating
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId, fieldId) and returns boolean
   */
  isAIFieldGenerating: (state) => (tableId, rowId, fieldId) => {
    const status = state.metadata[tableId]?.[rowId]?.ai_field?.[fieldId]?.status
    return status === 'generating'
  },

  /**
   * Check if an AI field has an error
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId, fieldId) and returns boolean
   */
  hasAIFieldError: (state) => (tableId, rowId, fieldId) => {
    const status = state.metadata[tableId]?.[rowId]?.ai_field?.[fieldId]?.status
    return status === 'error'
  },

  /**
   * Get AI field error details
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId, rowId, fieldId) and returns error object or null
   */
  getAIFieldError: (state) => (tableId, rowId, fieldId) => {
    return state.metadata[tableId]?.[rowId]?.ai_field?.[fieldId]?.error || null
  },

  /**
   * Check if a table has loaded metadata
   * @param {Object} state - Vuex state
   * @returns {Function} Function that takes (tableId) and returns boolean
   */
  isTableLoaded: (state) => (tableId) => {
    return state.loadedTables.has(tableId)
  },
}

export default {
  namespaced: true,
  state,
  getters,
  actions,
  mutations,
}
