import { BaseSearchType } from '@baserow/modules/core/search/types/base'

export class AutomationSearchType extends BaseSearchType {
  constructor() {
    super()
    this.type = 'automation'
    this.name = 'Automation'
    this.icon = 'baserow-icon-automation'
    this.priority = 4
  }

  _getApplicationId(result) {
    return result?.metadata?.application_id || result?.id
  }

  _getApplicationWithWorkflows(result, context) {
    const appId = this._getApplicationId(result)
    if (!appId || !context?.store) {
      return null
    }
    const automation = context.store.getters['application/get'](appId)
    if (automation && automation.workflows && automation.workflows.length > 0) {
      return automation
    }
    return null
  }

  buildUrl(result, context = null) {
    const automation = this._getApplicationWithWorkflows(result, context)
    if (!automation) {
      return null
    }

    const workflows = [...automation.workflows].sort(
      (a, b) => a.order - b.order
    )
    return {
      name: 'automation-workflow',
      params: { automationId: automation.id, workflowId: workflows[0].id },
    }
  }

  isNavigable(result, context = null) {
    return this._getApplicationWithWorkflows(result, context) !== null
  }
}
