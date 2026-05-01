/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

const E34_FISCAL_TYPE_ID = 51;

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
    },

    async closeTicketScreen() {
        const newOrder = this.pos.get_order?.();
        const origin = this.getSelectedOrder?.();

        if (newOrder && newOrder._isRefundOrder?.() && this.pos.config?.l10n_do_fiscal_journal) {
            const originPartner = origin?.get_partner?.() || origin?.partner_id;
            if (originPartner) {
                newOrder.set_partner?.(originPartner);
            }

            if (origin?.ncf) {
                newOrder.set_ncf_origin_out?.(origin.ncf) || newOrder.update?.({ ncf_origin_out: origin.ncf });
            } else {
                this.notification.add(_t("La orden original no tiene NCF para referenciar."), { type: "danger" });
                return false;
            }

            const e34 = this.pos.models["account.fiscal.type"]?.getBy("id", E34_FISCAL_TYPE_ID);
            if (!e34) {
                this.notification.add(_t("No se encontró el tipo fiscal E34 (ID 51)."), { type: "danger" });
                return false;
            }
            newOrder.set_fiscal_type?.(e34);

            newOrder.set_to_invoice?.(true);

            const voucherAmount = Math.abs(newOrder.get_total_with_tax?.() || 0);

            newOrder.set_credit_note_voucher_data?.({
                is_credit_note_voucher: true,
                credit_note_amount_total: voucherAmount,
                credit_note_amount_used: 0,
                credit_note_amount_available: voucherAmount,
                credit_note_redeemed: false,
            });

            return await super.closeTicketScreen(...arguments);
        }

        return await super.closeTicketScreen(...arguments);
    }


});