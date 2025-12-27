import { GraphModel } from "@web/views/graph/graph_model"

export class MultigraphModel extends GraphModel {
    constructor(env = {}, params = {}, services = undefined) {
        const fallbackOrm = {
            // Minimal stub to satisfy constructor paths that require an orm
            webReadGroup: async () => ({ groups: [] }),
        }
        const mergedEnv = {
            ...env,
            services: {
                // Ensure an ORM service always exists to avoid constructor crashes
                orm: (services && services.orm) || (env && env.services && env.services.orm) || fallbackOrm,
                ...(env?.services || {}),
                ...(services || {}),
            },
        }

        // Call parent with normalized signature (env, params, services)
        // Some Odoo models expect exactly 3 constructor args
        super(mergedEnv, params, mergedEnv.services)

        // Ensure orm is present for direct calls in our methods/tests
        if (!this.orm && mergedEnv.services && mergedEnv.services.orm) {
            this.orm = mergedEnv.services.orm
        }
    }

    setup(params) {
        // Store custom measure configuration before parent processing
        this.customMeasures = params.measures || []
        this.customMeasureConfig = {}

        // Process custom measures and store configuration
        if (Array.isArray(params.measures)) {
            params.measures.forEach(measure => {
                this.customMeasureConfig[measure.fieldName] = {
                    axis: measure.axis,
                    widget: measure.widget,
                    label: measure.label,
                    type: measure.type
                }
            })

            // Convert measures array to field names for parent class
            params.measures = params.measures.map(m => m.fieldName)
            params.measureFields = params.measures
        }

        // Ensure all fields have string property to prevent f1.string errors
        if (params.fields) {
            Object.keys(params.fields).forEach(fieldName => {
                if (!params.fields[fieldName].string) {
                    params.fields[fieldName].string = fieldName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
                }
            })
        }

        super.setup(params)
        // Ensure a default mode is present for tests and renderer expectations
        this.metaData = this.metaData || {}
        this.metaData.mode = this.metaData.mode || "line"
        // Preserve the rich measure objects if provided; otherwise fall back to parent metadata
        this.measures = Array.isArray(this.customMeasures) && this.customMeasures.length
            ? this.customMeasures
            : (this.metaData.measures || [])
        this.axisConfig = this.metaData.axisConfig || params.axisConfig || {}
        this.resModel = this.metaData.resModel
        this.data = {
            datasets: [],
            labels: [],
            domains: []
        }
    }

    async load(searchParams) {
        // If searchParams doesn't have groupBy but context has graph_groupbys, use it
        if ((!searchParams.groupBy || searchParams.groupBy.length === 0) &&
            searchParams.context && searchParams.context.graph_groupbys) {
            searchParams = {
                ...searchParams,
                groupBy: searchParams.context.graph_groupbys
            }
        }

        return await this._loadData(searchParams)
    }

    async _loadData(searchParams) {
        this.searchParams = searchParams || {}
        let { context, domain, groupBy, orderBy } = this.searchParams

        context = context || {}
        domain = Array.isArray(domain) ? domain : []
        groupBy = Array.isArray(groupBy) ? groupBy : []
        orderBy = Array.isArray(orderBy) ? orderBy : []

        // If no groupBy is specified but we have graph_groupbys in context, use that
        if (groupBy.length === 0 && Array.isArray(context.graph_groupbys) && context.graph_groupbys.length > 0) {
            groupBy = context.graph_groupbys
        }

        // Keep the original groupBy with intervals for webReadGroup
        const measureFieldNames = (this.measures || []).map(m => m.fieldName)
        const fieldNamesOnly = groupBy.map(gb => {
            if (typeof gb === 'string' && gb.includes(':')) {
                return gb.split(':')[0]
            }
            return gb
        })

        const readGroupFields = [...new Set([...fieldNamesOnly, ...measureFieldNames])]

        const options = {
            orderby: orderBy.length ? orderBy : false,
            lazy: groupBy.length === 1,
            context,
        }

        // Keep the effective groupBy in searchParams for downstream processing
        this.searchParams.groupBy = groupBy

        const data = await this.orm.webReadGroup(
            this.metaData.resModel,
            domain,
            readGroupFields,
            groupBy,
            options
        )

        this.data = this._processData(data, fieldNamesOnly)
        // Keep a stable alias expected by some renderer/test helpers
        this.dataPoints = this.data
        return this.data
    }

    _processData(data, groupBy) {
        const processedData = {
            datasets: [],
            labels: [],
            domains: [],
        }

        if (!data.groups || !data.groups.length) {
            return processedData
        }

        processedData.labels = data.groups.map(group => {
            // Check if we have a groupBy with interval
            const gb = Array.isArray(this.searchParams?.groupBy) ? this.searchParams.groupBy : []
            if (gb.length && gb[0]) {
                const groupByField = gb[0]

                // For fields with intervals, Odoo returns the field with interval suffix as key
                if (typeof groupByField === 'string' && groupByField.includes(':') && group[groupByField] !== undefined) {
                    // The value is already formatted by Odoo
                    return group[groupByField] || "Undefined"
                }

                // For regular fields (no interval)
                const fieldName = groupBy[0]
                const value = group[fieldName]
                return this._formatGroupByValue(fieldName, value)
            }
            return "Total"
        })
        processedData.domains = data.groups.map(group => group.__domain || [])

        this.measures.forEach((measure, index) => {
            const values = data.groups.map(group => group[measure.fieldName] || 0)

            processedData.datasets.push({
                label: measure.label,
                data: values,
                yAxisID: measure.axis,
                backgroundColor: this._getColor(index, "background"),
                borderColor: this._getColor(index, "border"),
                borderWidth: 2,
                type: "line",
                tension: 0.1,
                fieldName: measure.fieldName,
                widget: measure.widget,
            })
        })

        return processedData
    }

    _getColor(index, type = "background") {
        const colors = [
            { bg: "rgba(31, 119, 180, 0.7)", border: "rgb(31, 119, 180)" },
            { bg: "rgba(255, 127, 14, 0.7)", border: "rgb(255, 127, 14)" },
            { bg: "rgba(44, 160, 44, 0.7)", border: "rgb(44, 160, 44)" },
            { bg: "rgba(214, 39, 40, 0.7)", border: "rgb(214, 39, 40)" },
            { bg: "rgba(148, 103, 189, 0.7)", border: "rgb(148, 103, 189)" },
        ]

        const colorSet = colors[index % colors.length]
        return type === "background" ? colorSet.bg : colorSet.border
    }

    _formatGroupByValue(fieldName, value) {
        const field = (this.metaData && this.metaData.fields && this.metaData.fields[fieldName]) || null

        if (!value || value === false) {
            return "Undefined"
        }

        if (field && (field.type === "date" || field.type === "datetime")) {
            const date = new Date(value)
            return date.toLocaleDateString()
        }

        if (Array.isArray(value)) {
            return value[1] || value[0] || "Undefined"
        }

        return "" + value
    }

    getFormattedValue(value, dataset) {
        if (dataset.widget === "monetary") {
            return new Intl.NumberFormat("en-US", {
                style: "currency",
                currency: "USD",
            }).format(value)
        }

        if (Number.isInteger(value)) {
            return value.toLocaleString()
        }

        return value.toFixed(2)
    }

    hasData() {
        return this.data && this.data.datasets && this.data.datasets.length > 0 &&
            this.data.datasets.some(ds => ds.data && ds.data.length > 0)
    }

    _buildMetaData(params = {}) {
        // Build metadata for tests - ensure all fields have string property
        const fields = { ...this.metaData.fields }
        Object.keys(fields).forEach(fieldName => {
            if (!fields[fieldName].string) {
                fields[fieldName].string = fieldName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
            }
        })

        return {
            ...this.metaData,
            fields,
            axisConfig: this.axisConfig
        }
    }

    _computeCustomReportMeasures() {
        // Compute report measures with custom configuration
        const reportMeasures = {}

        if (this.metaData && this.metaData.measures) {
            this.metaData.measures.forEach(fieldName => {
                const customConfig = this.customMeasureConfig[fieldName] || {}
                const field = this.metaData.fields[fieldName] || {}

                reportMeasures[fieldName] = {
                    fieldName,
                    axis: customConfig.axis || 'y',
                    widget: customConfig.widget || field.widget || null,
                    label: customConfig.label || field.string || fieldName,
                    type: customConfig.type || field.type
                }
            })
        }

        return reportMeasures
    }
}
