/** @odoo-module **/

import { PosStore } from "@point_of_sale/app/services/pos_store";
import { patch } from "@web/core/utils/patch";

function setDefaultPartnerIfNeededDO(pos, order) {
    if (!order) return;

    // No tocar devoluciones
    if (order._isRefundOrder?.()) return;

    if (order.partner_id || order.get_partner?.()) return;

    const def = pos.config?.pos_partner_id;
    const partnerId = def?.id || def;
    if (partnerId) {
        order.update({ partner_id: partnerId });
    }
}

function setDefaultFiscalTypeIfNeededDO(pos, order) {
    if (!order) return;
    if (!pos.config?.l10n_do_fiscal_journal) return;
    // No tocar devoluciones (B04 se setea desde TicketScreen)
    if (order._isRefundOrder?.()) return;
    const hasFiscalType = !!(order.fiscal_type_id || order.get_fiscal_type?.() || order.fiscal_type);
    if (hasFiscalType) return;
    const fiscalTypeId = pos.config?.default_fiscal_type_id;
    if (fiscalTypeId) {
        order.set_fiscal_type(fiscalTypeId);

        //configurando la orden como factura
        order.set_to_invoice(true)
    }
}

patch(PosStore.prototype, {

    get_fiscal_type_by_prefix(prefix) {
        return this.models["account.fiscal.type"].getBy("prefix", prefix);
    },
    get_credit_note_payment_method() {
        return (this.payment_methods || []).find((pm) => pm.is_credit_note) || false;
    },

    isCreditNoteMode() {
        if (!this.config?.l10n_do_fiscal_journal) return false;
        const order = this.get_order?.();
        const line = order?.selected_paymentline || null;
        return !!(line?.payment_method?.is_credit_note);
    },

    async get_credit_note(ncf) {
        return await this.env.services.orm.call("pos.order", "get_credit_note", [ncf]);
    },

    async get_credit_notes(partner_id) {
        return await this.env.services.orm.call("pos.order", "get_credit_notes", [partner_id]);
    },

    async get_fiscal_data(order) {
        const fiscalType = order?.get_fiscal_type?.() || order?.fiscal_type;
        if (!fiscalType) return false;

        const payments = (order.get_paymentlines?.() || []).map((pl) => ({
            payment_method_id: pl.payment_method?.id,
            returned_ncf: pl?.credit_note_ncf || false,
            returned_partner_id: pl?.credit_note_partner_id || false,
        }));

        return await this.env.services.orm.call("pos.order", "get_next_fiscal_sequence", [
            fiscalType.id,
            this.company.id,
            payments,
        ]);
    },

    add_new_order(...args) {
        const res = super.add_new_order(...args);
        const order = this.get_order();
        try { setDefaultPartnerIfNeededDO(this, order); } catch (e) { console.warn(e); }
        try { setDefaultFiscalTypeIfNeededDO(this, order); } catch (e) { console.warn(e); }
        return res;
    },



    //logica de asignacion de notas de credito
    async search_credit_note_vouchers(query) {
        return await this.env.services.orm.call("pos.order", "search_credit_note_vouchers", [query]);
    },

    async get_credit_note_voucher(orderId) {
        return await this.env.services.orm.call("pos.order", "get_credit_note_voucher", [orderId]);
    },
});
