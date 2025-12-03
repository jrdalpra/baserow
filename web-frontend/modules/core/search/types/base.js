export class BaseSearchType {
  constructor() {
    this.type = null
    this.name = null
    this.icon = 'iconoir-search'
    this.priority = 10
  }

  /**
   * Builds the URL for navigating to this search result.
   * Must be implemented by subclasses.
   * @param {Object} result - The search result object
   * @param {Object} context - Context containing store reference
   * @returns {string|Object|null} URL string, route object, or null if not navigable
   */
  buildUrl(result, context = null) {
    throw new Error('buildUrl must be implemented by subclass')
  }

  getIcon() {
    return this.icon
  }

  getName() {
    return this.name
  }

  getType() {
    return this.type
  }

  getPriority() {
    return this.priority
  }

  /**
   * Formats the result for display in the search modal.
   * Override in subclasses to provide custom formatting.
   * @param {Object} result - The search result object
   * @param {Object} context - Context (e.g., searchTerm for highlighting)
   * @returns {Object} Object with title, subtitle, and descriptionSegments
   */
  formatResultDisplay(result, context = null) {
    return {
      title: result.title,
      subtitle: result.subtitle,
      descriptionSegments: [],
    }
  }

  /**
   * Returns true if the result can be navigated to (has a valid URL).
   * Override in subclasses to provide custom logic.
   * @param {Object} result - The search result object
   * @param {Object} context - Context containing store reference
   * @returns {boolean}
   */
  isNavigable(result, context = null) {
    return true
  }

  /**
   * Gets the application ID from a result.
   * Override in subclasses for custom ID extraction logic.
   * @param {Object} result - The search result object
   * @returns {number|null}
   */
  _getApplicationId(result) {
    const id = parseInt(result?.id)
    return isNaN(id) ? null : id
  }

  /**
   * Attempts to focus/select the application in the sidebar as a fallback action.
   * @param {Object} result - The search result object
   * @param {Object} context - Context containing store reference
   * @returns {boolean} True if the action was taken, false otherwise
   */
  focusInSidebar(result, context = null) {
    const appId = this._getApplicationId(result)
    if (!appId || !context?.store) {
      return false
    }
    const application = context.store.getters['application/get'](appId)
    if (application) {
      context.store.dispatch('application/select', application)
      return true
    }
    return false
  }

  /**
   * Returns the i18n key suffix for the label to display when item is not navigable.
   * Returns null if no label should be shown.
   * @param {Object} result - The search result object
   * @param {Object} context - Context containing store reference
   * @returns {string|null}
   */
  getEmptyLabel(result, context = null) {
    return this.isNavigable(result, context) ? null : 'empty'
  }
}
