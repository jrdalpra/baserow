import { notifyIf } from '@baserow/modules/core/utils/error'

import FieldService from '@baserow_premium/services/field'

const AI_FIELD_STATUS = {
  GENERATING: 'g',
  ERROR: 'e',
}

export default {
  computed: {
    generating() {
      if (!this.storePrefix) {
        return false
      }

      const hasPendingOps = this.$store.getters[
        this.storePrefix + 'view/grid/hasPendingFieldOps'
      ](this.field.id, this.$parent.row.id)

      if (hasPendingOps) {
        return true
      }

      const metadata = this.$parent?.row?._.metadata

      if (metadata && metadata.ai_field) {
        const fieldStatus = metadata.ai_field[this.field.id]
        return fieldStatus === AI_FIELD_STATUS.GENERATING
      }

      return false
    },
    generationError() {
      const metadata = this.$parent?.row?._.metadata
      if (metadata && metadata.ai_field) {
        const fieldStatus = metadata.ai_field[this.field.id]
        if (fieldStatus === AI_FIELD_STATUS.ERROR) {
          return {
            message: this.$t('gridViewFieldAI.generationFailed'),
          }
        }
      }
      return null
    },
    metadataStatusIndicator() {
      const metadata = this.$parent?.row?._.metadata
      if (metadata && metadata.ai_field) {
        const fieldStatus = metadata.ai_field[this.field.id]
        if (fieldStatus === AI_FIELD_STATUS.ERROR) {
          return {
            icon: 'iconoir-warning-triangle',
            color: 'var(--color-warning)',
            message: this.$t('gridViewFieldAI.generationFailed'),
          }
        }
      }
      return null
    },
    modelAvailable() {
      const workspace = this.$store.getters['workspace/get'](this.workspaceId)
      if (!workspace) return false

      const aIModels =
        workspace.generative_ai_models_enabled[
          this.field.ai_generative_ai_type
        ] || []
      return (
        this.$registry.get('field', this.field.type).isEnabled(workspace) &&
        aIModels.includes(this.field.ai_generative_ai_model)
      )
    },
    isDeactivated() {
      return this.$registry
        .get('field', this.field.type)
        .isDeactivated(this.workspaceId)
    },
    deactivatedClickComponent() {
      return this.$registry
        .get('field', this.field.type)
        .getDeactivatedClickModal(this.workspaceId)
    },
    workspace() {
      return this.$store.getters['workspace/get'](this.workspaceId)
    },
  },
  methods: {
    isGenerating(parent, props) {
      if (!props.storePrefix) {
        return false
      }

      const hasPendingOps = parent.$store.getters[
        props.storePrefix + 'view/grid/hasPendingFieldOps'
      ](props.field.id, parent.row.id)

      if (hasPendingOps) {
        return true
      }

      const metadata = parent.row?._.metadata

      if (metadata && metadata.ai_field) {
        const fieldStatus = metadata.ai_field[props.field.id]
        return fieldStatus === AI_FIELD_STATUS.GENERATING
      }

      return false
    },
    isModelAvailable(parent, props) {
      const workspace = parent.$store.getters['workspace/get'](
        props.workspaceId
      )
      if (!workspace) return false

      const aIModels =
        workspace.generative_ai_models_enabled[
          props.field.ai_generative_ai_type
        ] || []
      return (
        parent.$registry.get('field', props.field.type).isEnabled(workspace) &&
        aIModels.includes(props.field.ai_generative_ai_model)
      )
    },
    async generate() {
      if (this.isDeactivated) {
        this.$refs.clickModal.show()
        return
      }

      const rowId = this.$parent.row.id
      const row = this.$parent.row

      const previousMetadata =
        row?._.metadata?.ai_field?.[this.field.id] || null

      this.$store.commit(this.storePrefix + 'view/grid/UPDATE_ROW_METADATA', {
        row,
        metadata: {
          ai_field: {
            [this.field.id]: AI_FIELD_STATUS.GENERATING,
          },
        },
      })

      this.$store.dispatch(
        this.storePrefix + 'view/grid/setPendingFieldOperations',
        { fieldId: this.field.id, rowIds: [rowId], value: true }
      )

      try {
        await FieldService(this.$client).generateAIFieldValues(this.field.id, [
          rowId,
        ])
      } catch (error) {
        notifyIf(error, 'field')

        // Rollback metadata to previous state on error
        // If there was no previous metadata, clear it entirely
        this.$store.commit(this.storePrefix + 'view/grid/UPDATE_ROW_METADATA', {
          row,
          metadata: {
            ai_field: {
              [this.field.id]: previousMetadata || null,
            },
          },
        })

        this.$store.dispatch(
          this.storePrefix + 'view/grid/setPendingFieldOperations',
          { fieldId: this.field.id, rowIds: [rowId], value: false }
        )
      }
    },
  },
}
