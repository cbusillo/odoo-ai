import { Component, onMounted, onWillUpdateProps, useState } from '@odoo/owl'
import { useService } from '@web/core/utils/hooks'
import { registry } from '@web/core/registry'
import { groupBy, sortBy } from '@web/core/utils/arrays'
import { ResettableBadgeSelectionField } from './resettable_badge_selection_widget.js'
import { FloatField } from '@web/views/fields/float/float_field'
import { CharField } from '@web/views/fields/char/char_field'
import { BinaryField } from '@web/views/fields/binary/binary_field'
import { PdfViewerField } from '@web/views/fields/pdf_viewer/pdf_viewer_field'

/**
 * @typedef {Object} ConditionalTest
 * @property {string} data.conditional_test
 * @property {string} data.action_type
 * @property {string} data.hidden_tests
 /**
 * @typedef {Object} MotorTestRecord
 * @property {string} data.result_type
 * @property {Array<ConditionalTest>} data.conditional_tests
 * @property {number} data.section_sequence
 * @property {Array<int>} data.strokes
 * @property {Array<int>} data.manufacturers
 * @property {Array<int>} data.configurations
 */
/**
 * @typedef {Object} MotorPartRecord
 * @property {boolean} data.is_missing
 */
export class MotorTestWidget extends Component {
    static template = "marine_motors.MotorTestWidget"
    // noinspection JSUnusedGlobalSymbols
    static components = {
        ResettableBadgeSelectionField,
        FloatField,
        CharField,
        BinaryField,
        PdfViewerField,
    }
    static props = {
        id: String,
        name: String,
        record: Object,
        readonly: Boolean,
    }

    async setup() {
        this.motorTestsBySection = useState({ sections: [] })
        this.selectionFieldDomains = useState({})
        this.conditionsById = {}
        this.allTests = []
        this.notification = useService('notification')
        this.orm = useService('orm')

        onMounted(() => {
            this.loadMotorTests()
        })

        onWillUpdateProps((nextProps) => {
            if (nextProps.record !== this.props.record) {
                this.loadMotorTests(nextProps)
            }
        })
    }

    async onFieldChanged() {
        await this.props.record.save()
        await this.loadMotorTests()
    }

    async loadMotorTests(props = this.props) {
        const { name, record } = props
        this.allTests = record.data[name].records
        const missingParts = record.data.parts.records.filter(
            (part) => part.data.is_missing,
        )

        const conditionIds = this.allTests.flatMap(
            (record) => record.data.conditions.currentIds,
        )

        try {
            const conditions = await this.orm.searchRead(
                'motor.test.template.condition',
                [['id', 'in', conditionIds]],
                ['action_type', 'condition_value', 'conditional_operator', 'template', 'conditional_test'],
            )

            this.conditionsById = Object.fromEntries(
                conditions.map((condition) => [
                    condition.id,
                    condition,
                ]),
            )

            const sortedTests = this.sortMotorTests(this.allTests)
            this.motorTestsBySection.sections = this.groupMotorTestsBySection(
                sortedTests,
                missingParts,
            )
        } catch (error) {
            this.notification.add('Error loading motor tests: ' + error.message, {
                title: 'Error',
                type: 'danger',
                sticky: true,
            })
        }
    }

    sortMotorTests(motorTests) {
        return sortBy(motorTests, (test) =>
            (test.data.section_sequence || 0) * 1000 + (test.data.sequence || 0)
        );
    }

    groupMotorTestsBySection(motorTests, missingParts) {
        const groupedTests = groupBy(motorTests, (test) => this.getSectionLabel(test))

        return Object.entries(groupedTests).reduce((acc, [section, tests]) => {
            const filteredTests = tests.filter((test) => {
                const resultType = test.data.result_type
                const result = test.data[`${test.data.result_type}_result`]
                const isApplicable = this.evaluateTestApplicability(test, missingParts)
                if (!isApplicable) {
                    return false
                }

                const showConditions = test.data.conditions.records.filter(
                    (condition) => condition.data.action_type === 'show',
                )
                return showConditions.every((condition) =>
                    this.evaluateCondition(result, resultType, condition),
                )
            })

            const conditionalTests = filteredTests.flatMap((test) => {
                const resultType = test.data.result_type
                const result = test.data[`${test.data.result_type}_result`]

                return test.data.conditions.records.filter(
                    (conditionalTest) =>
                        conditionalTest.data &&
                        Object.keys(conditionalTest.data).length > 0 &&
                        this.evaluateCondition(result, resultType, conditionalTest),
                )
            })

            acc[section] = this.sortMotorTests([
                ...filteredTests,
                ...conditionalTests,
            ])

            for (const test of acc[section]) {
                this.setSelectionFieldDomain(test)
            }

            return acc
        }, {})
    }

    getSectionLabel(test) {
        const section = test.data.section
        if (!section) {
            return 'Unassigned'
        }
        if (Array.isArray(section)) {
            return section[1] || 'Unassigned'
        }
        if (typeof section === 'object') {
            if (section.display_name) {
                return section.display_name
            }
            if (section.name) {
                return section.name
            }
            if (section.data && section.data.display_name) {
                return section.data.display_name
            }
            if (section.data && section.data.name) {
                return section.data.name
            }
        }
        return String(section)
    }

    evaluateTestApplicability(test, missingParts) {
        const hiddenByParts = missingParts.some((part) =>
            part.data.hidden_tests.currentIds.includes(test.data.template[0]),
        )
        if (hiddenByParts) {
            return false
        }
        const motorStrokeId = this.props.record.data.stroke[0]
        const testStrokes = test.data.strokes.records.map((record) => record.resId)
        const motorManufacturerId = this.props.record.data.manufacturer[0]
        const testManufacturers = test.data.manufacturers.records.map(record => record.resId)
        const motorConfigurationId = this.props.record.data.configuration[0]
        const testConfigurations = test.data.configurations.records.map(record => record.resId)

        if (testStrokes.length > 0 && !testStrokes.includes(motorStrokeId)) {
            return false
        }

        if (testManufacturers.length > 0 && !testManufacturers.includes(motorManufacturerId)) {
            return false
        }

        if (testConfigurations.length > 0 && !testConfigurations.includes(motorConfigurationId)) {
            return false
        }

        const hideConditions = test.data.conditional_tests.records.map(
            (condition) => {
                const conditionRecord = Object.values(this.conditionsById).find(
                    (c) => c.id === condition.resId,
                )
                if (conditionRecord && conditionRecord.action_type === 'hide') {
                    return conditionRecord
                }
                return null
            }).filter(Boolean)

        const hideConditionsMet = hideConditions.some((condition) =>
            this.evaluateTemplateTestCondition(condition)
        )

        if (hideConditionsMet) {
            return false
        }

        const showConditions = test.data.conditional_tests.records.map(
            (condition) => {
                const conditionRecord = this.conditionsById[condition.resId]
                if (conditionRecord && conditionRecord.action_type === 'show') {
                    return conditionRecord
                }
                return null
            }).filter(Boolean)

        const showConditionsMet = showConditions.some((condition) =>
            this.evaluateTemplateTestCondition(condition)
        )

        if (showConditions.length > 0) {
            return showConditionsMet
        }
        return true
    }

    evaluateTemplateTestCondition(condition) {
        const templateTest = this.allTests.find(
            (t) => t.data.template[0] === condition.template[0],
        )
        if (templateTest) {
            const resultType = templateTest.data.result_type
            const result = resultType === 'selection' ?
                templateTest.data[`${resultType}_result_value`] : templateTest.data[`${resultType}_result`]
            return this.evaluateCondition(result, resultType, condition)
        }
        return false
    }

    evaluateCondition(result, resultType, condition) {
        if (!result) return false

        const conditionRecord = Object.values(this.conditionsById)
            .find(c => c.id === condition.id)

        const { condition_value: conditionValue, conditional_operator: operator } = conditionRecord

        if (!conditionValue) return false

        const compareEquality = (val1, val2, caseInsensitive = true) => {
            if (caseInsensitive) {
                val1 = val1.toLowerCase()
                val2 = val2.toLowerCase()
            }
            switch (operator) {
                case '=':
                    return val1 === val2
                case '!=':
                    return val1 !== val2
                default:
                    this.notification.add('Invalid operator: ' + operator, {
                        title: 'Error',
                        type: 'danger',
                        sticky: true,
                    })
                    return false
            }
        }

        const compareNumeric = (val1, val2) => {
            val1 = parseFloat(val1)
            val2 = parseFloat(val2)

            switch (operator) {
                case '=':
                    return val1 === val2
                case '!=':
                    return val1 !== val2
                case '>':
                    return val1 > val2
                case '<':
                    return val1 < val2
                case '>=':
                    return val1 >= val2
                case '<=':
                    return val1 <= val2
                default:
                    throw new Error('Invalid operator: ' + operator)
            }
        }

        switch (resultType) {
            case 'selection':
                return compareEquality(result, conditionValue)
            case 'yes_no':
                return compareEquality(result, conditionValue)
            case 'text':
                return compareEquality(result, conditionValue)
            case 'numeric':
                return compareNumeric(result, conditionValue)
        }
        return false
    }

    setSelectionFieldDomain({
                                data: { result_type: resultType, selection_options: selectionOptions },
                                id,
                            }) {
        if (resultType === 'selection') {
            this.selectionFieldDomains[id] = [
                ['id', 'in', selectionOptions.currentIds],
            ]
        }
    }

    // noinspection JSUnusedGlobalSymbols
    getSelectionFieldDomain(testId) {
        return this.selectionFieldDomains[testId] || []
    }
}


export const motorTestWidget = {
    component: MotorTestWidget,
}

registry.category('fields').add('motor_test_widget', motorTestWidget)
