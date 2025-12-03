import { BaseSearchType } from '@baserow/modules/core/search/types/base'

export class BuilderSearchType extends BaseSearchType {
  constructor() {
    super()
    this.type = 'builder'
    this.name = 'Builder'
    this.icon = 'baserow-icon-application'
    this.priority = 2
  }

  _getApplicationId(result) {
    const id = parseInt(result?.id)
    return isNaN(id) ? null : id
  }

  _getApplicationWithPages(result, context) {
    const appId = this._getApplicationId(result)
    if (!appId || !context?.store) {
      return null
    }
    const application = context.store.getters['application/get'](appId)
    if (!application) {
      return null
    }
    const pages = context.store.getters['page/getVisiblePages'](application)
    if (pages && pages.length > 0) {
      return { application, pages }
    }
    return null
  }

  buildUrl(result, context = null) {
    const data = this._getApplicationWithPages(result, context)
    if (!data) {
      return null
    }
    return {
      name: 'builder-page',
      params: { builderId: data.application.id, pageId: data.pages[0].id },
    }
  }

  isNavigable(result, context = null) {
    return this._getApplicationWithPages(result, context) !== null
  }
}
