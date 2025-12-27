import { Component, onMounted, useState } from "@odoo/owl"
import { registry } from "@web/core/registry"

export class TestingBanner extends Component {
    static props = {}
    static template = "product_connect.TestingBanner"

    get bannerClasses() {
        const baseClasses = "testing-banner text-center font-bold"

        const environmentClasses = {
            dev: "environment-dev",
            testing: "environment-testing",
            localhost: "environment-localhost",
            other: "environment-other"
        }

        return `${baseClasses} ${environmentClasses[this.state.environment] || environmentClasses.other}`
    }

    get bannerText() {
        const environmentLabels = {
            dev: "Development Environment",
            testing: "Testing Environment",
            localhost: "Local Development",
            other: "Non-Production Environment"
        }

        return environmentLabels[this.state.environment] || environmentLabels.other
    }

    setup() {
        this.state = useState({
            isTestEnvironment: false,
            hostname: "",
            environment: "other"
        })

        onMounted(() => {
            const hostname = window.location.hostname
            this.state.hostname = hostname
            this.state.isTestEnvironment = hostname !== "odoo.outboardpartswarehouse.com"

            if (hostname.includes('dev.')) {
                this.state.environment = 'dev'
            } else if (hostname.includes('testing.')) {
                this.state.environment = 'testing'
            } else if (hostname.includes('localhost')) {
                this.state.environment = 'localhost'
            } else if (hostname !== 'odoo.outboardpartswarehouse.com') {
                this.state.environment = 'other'
            }
        })
    }
}

export const testingBanner = {
    Component: TestingBanner,
}

registry.category("main_components").add("testing_banner", testingBanner)