import { BaseSearchType } from '@baserow/modules/core/search/types/base'

export class DatabaseSearchType extends BaseSearchType {
  constructor() {
    super()
    this.type = 'database'
    this.name = 'Database'
    this.icon = 'iconoir-db'
    this.priority = 1
  }

  _getApplicationId(result) {
    return result?.metadata?.database_id || result?.id
  }

  _getApplicationWithTables(result, context) {
    const databaseId = this._getApplicationId(result)
    if (!databaseId || !context?.store) {
      return null
    }
    const application = context.store.getters['application/get'](databaseId)
    if (application && application.tables && application.tables.length > 0) {
      return application
    }
    return null
  }

  buildUrl(result, context = null) {
    const application = this._getApplicationWithTables(result, context)
    if (!application) {
      return null
    }

    const databaseId = this._getApplicationId(result)
    const tables = [...application.tables].sort((a, b) => a.order - b.order)

    return {
      name: 'database-table',
      params: { databaseId, tableId: tables[0].id },
    }
  }

  isNavigable(result, context = null) {
    return this._getApplicationWithTables(result, context) !== null
  }
}

export class DatabaseTableSearchType extends BaseSearchType {
  constructor() {
    super()
    this.type = 'database_table'
    this.name = 'Tables'
    this.icon = 'iconoir-table'
    this.priority = 2
  }

  buildUrl(result, context = null) {
    if (
      !result.metadata ||
      !result.metadata.database_id ||
      !result.metadata.table_id
    ) {
      return null
    }

    return {
      name: 'database-table',
      params: {
        databaseId: result.metadata.database_id,
        tableId: result.metadata.table_id,
      },
    }
  }
}

export class DatabaseFieldSearchType extends BaseSearchType {
  constructor() {
    super()
    this.type = 'database_field'
    this.name = 'Fields'
    this.icon = 'iconoir-input-field'
    this.priority = 6
  }

  buildUrl(result, context = null) {
    if (
      !result.metadata ||
      !result.metadata.database_id ||
      !result.metadata.table_id
    ) {
      return null
    }

    return {
      name: 'database-table',
      params: {
        databaseId: result.metadata.database_id,
        tableId: result.metadata.table_id,
      },
    }
  }
}

export class DatabaseRowSearchType extends BaseSearchType {
  constructor() {
    super()
    this.type = 'database_row'
    this.name = 'Rows'
    this.icon = 'iconoir-list'
    this.priority = 7
  }

  buildUrl(result, context = null) {
    if (
      !result.metadata ||
      !result.metadata.database_id ||
      !result.metadata.table_id ||
      !result.metadata.row_id
    ) {
      return null
    }

    return {
      name: 'database-table-row',
      params: {
        databaseId: result.metadata.database_id,
        tableId: result.metadata.table_id,
        rowId: result.metadata.row_id,
      },
    }
  }
}
