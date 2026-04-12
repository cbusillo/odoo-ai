import { DateTimeField } from '@web/views/fields/datetime/datetime_field';
import { registry } from '@web/core/registry';

class DateOnlyWidget extends DateTimeField {
    static template = "product_widgets.DateOnlyField"

    setup() {
        super.setup();
        this.dateOnly = ""

        const createdDateTime = this.props.record.data[this.props.name];

        if (!createdDateTime) {
            return
        }

        this.dateOnly = createdDateTime.toFormat('MM-dd-yyyy')

    }
}

export const dateOnlyField = {
    component: DateOnlyWidget,
}
registry.category('fields').add('date_only', dateOnlyField);
