/** @odoo-module **/

import { PosPayment } from "@point_of_sale/app/models/pos_payment";
import { patch } from "@web/core/utils/patch";

patch(PosPayment.prototype, {
    setup(vals, options) {
        super.setup(...arguments);


        this.credit_note_ncf = vals?.credit_note_ncf ?? this.credit_note_ncf ?? "";
        this.credit_note_partner_id = vals?.credit_note_partner_id ?? this.credit_note_partner_id ?? false;
        this.credit_note_source_order_id = vals?.credit_note_source_order_id ?? this.credit_note_source_order_id ?? false;
        this.credit_note_ticket = vals?.credit_note_ticket ?? this.credit_note_ticket ?? "";

    },

  set_credit_note_data(data) {
        this.update({
            credit_note_ncf: data?.ncf || "",
            credit_note_partner_id: data?.partner_id || false,
            credit_note_source_order_id: data?.order_id || false,
            credit_note_ticket: data?.pos_reference || "",
            name: data?.pos_reference || data?.ncf || "",
        });
    },

});
