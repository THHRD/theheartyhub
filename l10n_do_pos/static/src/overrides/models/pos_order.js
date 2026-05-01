/** @odoo-module **/

import { PosOrder } from "@point_of_sale/app/models/pos_order";
import { patch } from "@web/core/utils/patch";

patch(PosOrder.prototype, {
    setup(vals, options) {
        super.setup(...arguments);

        // Valores fiscales (si viene desde backend, respeta vals)
        this.ncf = vals?.ncf ?? this.ncf ?? "";
        this.ncf_origin_out = vals?.ncf_origin_out ?? this.ncf_origin_out ?? "";
        this.ncf_expiration_date = vals?.ncf_expiration_date ?? this.ncf_expiration_date ?? false;
        this.fiscal_type_id = vals?.fiscal_type_id ?? this.fiscal_type_id ?? false;
        this.fiscal_sequence_id = vals?.fiscal_sequence_id ?? this.fiscal_sequence_id ?? false;

        this.l10n_do_ecf_modification_code =
            vals?.l10n_do_ecf_modification_code ?? this.l10n_do_ecf_modification_code ?? "3";
        this.ecf_modification_reason =
            vals?.ecf_modification_reason ?? this.ecf_modification_reason ?? "";

        this.ecf_modification_reason_id =
            vals?.ecf_modification_reason_id ?? this.ecf_modification_reason_id ?? false;

        //reembolso
        this.is_credit_note_voucher =
            vals?.is_credit_note_voucher ?? this.is_credit_note_voucher ?? false;
        this.credit_note_amount_total =
            vals?.credit_note_amount_total ?? this.credit_note_amount_total ?? 0;
        this.credit_note_amount_used =
            vals?.credit_note_amount_used ?? this.credit_note_amount_used ?? 0;
        this.credit_note_amount_available =
            vals?.credit_note_amount_available ?? this.credit_note_amount_available ?? 0;
        this.credit_note_redeemed =
            vals?.credit_note_redeemed ?? this.credit_note_redeemed ?? false;
    },

    set_ncf(ncf) {
        this.update({ ncf: ncf || "" });
    },

    get_ncf() {
        return this.ncf || "";
    },

    set_ncf_origin_out(ncf_origin_out) {
        this.update({ ncf_origin_out: ncf_origin_out || "" });
    },

    set_fiscal_sequence_id(fiscal_sequence_id) {
        this.update({ fiscal_sequence_id: fiscal_sequence_id || false });
    },

    set_fiscal_type(fiscal_type) {
        this.assert_editable?.();
        this.fiscal_type = fiscal_type || false;

        this.update({
            fiscal_type_id: fiscal_type ? fiscal_type.id : false,
        });

        if (fiscal_type?.fiscal_position_id) {
            const fpId = fiscal_type.fiscal_position_id[0];
            const fp = (this.pos.fiscal_positions || []).find((x) => x.id === fpId) || false;
            if (fp) {
                this.set_fiscal_position?.(fp);
                for (const line of this.get_orderlines?.() || []) {
                    line.set_quantity?.(line.quantity);
                }
            }
        }
    },

    get_fiscal_type() {
        return this.fiscal_type || false;
    },

    set_partner(partner) {
        super.set_partner(partner);
        if (partner?.sale_fiscal_type_id) {
            this.set_fiscal_type(partner.sale_fiscal_type_id);
        }
    },

    export_for_printing() {
        const res = super.export_for_printing(...arguments);
        res.fiscal_type = this.get_fiscal_type();
        res.ncf = this.get_ncf();
        res.partner = this.get_partner?.();
        return res;
    },


    set_credit_note_voucher_data(data = {}) {
        this.update({
            is_credit_note_voucher: !!data.is_credit_note_voucher,
            credit_note_amount_total: Math.abs(data.credit_note_amount_total || 0),
            credit_note_amount_used: Math.abs(data.credit_note_amount_used || 0),
            credit_note_amount_available: Math.abs(data.credit_note_amount_available || 0),
            credit_note_redeemed: !!data.credit_note_redeemed,
        });
    },

    set_ecf_modification_reason_data(data = {}) {
    this.update({
        l10n_do_ecf_modification_code: data.code || "3",
        ecf_modification_reason: data.reason || "",
        ecf_modification_reason_id: data.reason_id || false,
    });
}

});
