import { GraphRenderer } from "@web/views/graph/graph_renderer"
import { loadBundle } from "@web/core/assets"
import { onWillStart, onMounted, onWillUnmount, useRef } from "@odoo/owl"

export class MultigraphRenderer extends GraphRenderer {
    static template = "web.MultigraphRenderer"

    setup() {
        super.setup()
        this.canvasRef = useRef("canvas")
        this.chart = null
        this.chartjsLoaded = false

        onWillStart(async () => {
            try {
                await loadBundle("web.chartjs_lib")
                // Validate Chart.js is available
                if (typeof Chart !== 'undefined') {
                    this.chartjsLoaded = true
                } else {
                    console.error("Chart.js failed to load properly")
                }
            } catch (error) {
                console.error("Failed to load Chart.js bundle:", error)
            }
        })

        onMounted(() => this.renderChart())

        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy()
            }
        })
    }

    renderChart() {
        if (this.chart) {
            this.chart.destroy()
        }

        // Check if Chart.js is loaded and canvas is available
        if (!this.chartjsLoaded || typeof Chart === 'undefined') {
            console.error("Chart.js is not available - cannot render chart")
            return
        }

        if (!this.canvasRef.el) {
            console.warn("Canvas element not available")
            return
        }

        if (!this.model.data) {
            console.warn("No chart data available")
            return
        }

        try {
            const config = this.getChartConfig()
            if (!config) {
                console.error("Failed to get chart configuration")
                return
            }
            this.chart = new Chart(this.canvasRef.el, config)
        } catch (error) {
            console.error("Failed to create chart:", error)
        }
    }

    getChartConfig() {
        const { data } = this.model

        // Data validation is already handled in renderChart(),
        // so this should not be called with invalid data
        if (!data) {
            console.error("getChartConfig called without valid data - this should not happen")
            return null
        }

        // noinspection JSValidateTypes - Chart.js config structure
        return {
            type: "line",
            data: {
                labels: data.labels || [],
                datasets: data.datasets || [],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: true,
                        position: "top",
                    },
                    tooltip: {
                        mode: "index",
                        intersect: false,
                        callbacks: {
                            label: (context) => {
                                const dataset = context.dataset
                                const value = context.parsed.y
                                const formattedValue = this.model.getFormattedValue(value, dataset)
                                return `${dataset.label}: ${formattedValue}`
                            },
                        },
                    },
                },
                interaction: {
                    mode: "nearest",
                    axis: "x",
                    intersect: false,
                },
                scales: this._getScalesConfig(),
                onClick: (event, elements) => {
                    if (elements.length > 0) {
                        this.onGraphClick(event, elements)
                    }
                },
            },
        }
    }

    _getScalesConfig() {
        const scales = {
            x: {
                display: true,
                grid: {
                    display: true,
                    drawOnChartArea: true,
                },
            },
        }

        Object.entries(this.model.axisConfig || {}).forEach(([axisId, config]) => {
            scales[axisId] = {
                type: "linear",
                display: config.display,
                position: config.position,
                grid: {
                    drawOnChartArea: axisId === "y",
                },
                ticks: {
                    callback: (value) => {
                        const datasetsForAxis = this.model.data.datasets.filter(
                            ds => ds.yAxisID === axisId
                        )

                        if (datasetsForAxis.some(ds => ds.widget === "monetary")) {
                            return new Intl.NumberFormat("en-US", {
                                style: "currency",
                                currency: "USD",
                                maximumFractionDigits: 1
                            }).format(value)
                        }

                        return value.toLocaleString()
                    },
                },
            }
        })

        return scales
    }

    onGraphClick(event, elements) {
        const element = elements[0]
        if (!element) return

        const { index } = element
        const domains = this.model.data?.domains || []
        const domain = domains[index]

        if (domain && domain.length) {
            // Guard against undefined env (e.g., in test environments)
            if (this.env && this.env.services && this.env.services.action) {
                this.env.services.action.doAction({
                    type: "ir.actions.act_window",
                    name: "Details",
                    res_model: this.model.resModel,
                    views: [[false, "list"], [false, "form"]],
                    domain,
                    context: this.model.searchParams.context,
                })
            } else {
                console.log("Chart clicked - would open details view with domain:", domain)
            }
        }
    }

    // noinspection JSUnusedGlobalSymbols - Owl lifecycle method
    onWillUpdateProps(nextProps) {
        // Handle prop updates
        if (this.chart && this.props.model?.data !== nextProps.model?.data) {
            this.renderChart()
        }
    }
}
