import { registry } from '@web/core/registry'
import { CharField, charField } from '@web/views/fields/char/char_field'
import { useService } from '@web/core/utils/hooks'

export class SearchMpnOnlineWidget extends CharField {
    static template = 'product_connect.SearchMpnOnlineWidget'
    static props = {
        ...CharField.props,
        searchEngines: { type: String, optional: true },
        firstMpn: { type: Boolean, optional: true },
    }

    setup() {
        super.setup()
        this.notification = useService('notification')
        this.searchEnginesMap = {
            ebay: "https://www.ebay.com/sch/i.html?_nkw=",
            google: "https://www.google.com/search?q=",
            google_images: "https://www.google.com/search?tbm=isch&q=",
            amazon: "https://www.amazon.com/s?k=",
            crowley: "https://www.crowleymarine.com/search?q=",
        }
    }

    searchOnline() {
        const mpns = this.props.record.data[this.props.name]
        if (!mpns) {
            this.notification.add('No MPN entered', {
                type: 'warning',
                sticky: false,
            })
            return
        }

        const mpnArray = this.parseMpns(mpns)
        const searchEngines = this.getSearchEngines()
        this.openSearchWindows(mpnArray, searchEngines)
    }

    parseMpns(mpns) {
        const mpnArray = mpns.split(/[,\s]+/).filter(Boolean)
            .map(mpn => mpn.trim())
            .filter(mpn => mpn.length > 0)

        if (this.props.firstMpn && mpnArray.length > 0) {
            return [mpnArray[0]]
        } else {
            return mpnArray
        }
    }

    getSearchEngines() {
        const engines = this.props.searchEngines || Object.keys(this.searchEnginesMap)
        return typeof engines === "string" ? engines.split(/[,\s]+/).filter(Boolean) : engines
    }

    openSearchWindows(mpns, engines) {
        const delay = 100
        const searches = this.generateSearches(mpns, engines)

        searches.forEach((url, index) => {
            setTimeout(() => window.open(url, "_blank"), delay * index)
        })
    }

    generateSearches(mpns, engines) {
        return mpns.flatMap(mpn =>
            engines.map(engine => {
                const baseUrl = this.searchEnginesMap[engine]
                return baseUrl ? `${baseUrl}${mpn}` : null
            })
        ).filter((url) => url !== null)
    }
}

// noinspection JSUnusedGlobalSymbols
export const searchMpnOnline = {
    ...charField,
    component: SearchMpnOnlineWidget,
    displayName: "Search MPN Online",
    supportedTypes: ["char"],
    extractProps: ({ options: { search_engines, first_mpn } }) => {
        return {
            searchEngines: search_engines || "",
            firstMpn: first_mpn || false,
        }
    },
}

registry.category('fields').add('search_mpn_online', searchMpnOnline)
