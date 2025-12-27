import { registry } from "@web/core/registry"
import { Component, useState } from "@odoo/owl";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

export class RepairStatesWidget extends Component {
    static template = "product_connect.RepairStatesWidget"
    static props = {
        ...standardFieldProps,
    }

    setup() {
        this.state = useState({ repairStates: this.props.record.data[this.props.name] || [] })
    }

    async onIconClick(ev) {
        const repairStateId = ev.currentTarget.dataset.stateId;
        if (repairStateId === 'may_need_repair') {
            return
        }

        ev.stopPropagation();
        const motorId = this.props.record.resId;
        await this.env.model.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Repair Orders',
            res_model: 'repair.order',
            views: [[false, 'list'], [false, 'form']],
            domain: [['motor', '=', motorId]],
            target: 'current',
        });
    }
}

export const repairStatesWidget = {
    component: RepairStatesWidget,
}

registry.category("fields").add("repair_states_widget", repairStatesWidget)