/** @odoo-module **/

import { TicketScreen } from "@point_of_sale/app/screens/ticket_screen/ticket_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { useService } from "@web/core/utils/hooks";

patch(TicketScreen.prototype, {
    setup() {
        super.setup(...arguments);
        this.notification = useService("notification");
    },

    async onDoRefund() {
        const order = this.getSelectedOrder?.();
        if (!order) {
            this._state.ui.highlightHeaderNote = !this._state.ui.highlightHeaderNote;
            return;
        }

        if (this._doesOrderHaveSoleItem(order)) {
            if (!this._prepareAutoRefundOnOrder(order)) {
                return;
            }
        }

        if (this.pos.config.l10n_do_fiscal_journal) {
            const refundFiscalType = this.pos.get_fiscal_type_by_prefix?.("B04");
            const creditNotePaymentMethod =
                this.pos.get_credit_note_payment_method?.() ||
                (this.pos.payment_methods || []).find((pm) => pm.is_credit_note) ||
                false;

            if (!creditNotePaymentMethod) {
                this.notification.add(_t("There are no credit note payment method configured."), {
                    type: "danger",
                });
                return;
            }

            if (!refundFiscalType) {
                this.notification.add(
                    _t("The fiscal type credit note does not exist. Please activate or configure it."),
                    { type: "danger" }
                );
                return;
            }

            if (!order.ncf) {
                this.notification.add(_t("This order has no NCF"), { type: "danger" });
                return;
            }
        }

        return await super.onDoRefund(...arguments);
    },

    async closeTicketScreen() {
        const newOrder = this.pos.get_order?.();
        const origin = this.getSelectedOrder?.();

        if (
            newOrder &&
            this.pos.config.l10n_do_fiscal_journal &&
            newOrder._isRefundOrder?.() &&
            origin?.ncf
        ) {
            try {
                const refundFiscalType = this.pos.get_fiscal_type_by_prefix?.("B04");
                const creditNotePaymentMethod =
                    this.pos.get_credit_note_payment_method?.() ||
                    (this.pos.payment_methods || []).find((pm) => pm.is_credit_note) ||
                    false;

                if (!refundFiscalType) {
                    this.notification.add(
                        _t("The fiscal type credit note does not exist. Please activate or configure it."),
                        { type: "danger" }
                    );
                    return false;
                }
                if (!creditNotePaymentMethod) {
                    this.notification.add(_t("There are no credit note payment method configured."), {
                        type: "danger",
                    });
                    return false;
                }

                // Affects
                if (newOrder.set_ncf_origin_out) {
                    newOrder.set_ncf_origin_out(origin.ncf);
                } else {
                    newOrder.update?.({ ncf_origin_out: origin.ncf });
                }

                // Fiscal type B04
                if (newOrder.set_fiscal_type) {
                    newOrder.set_fiscal_type(refundFiscalType);
                } else {
                    newOrder.update?.({ fiscal_type_id: refundFiscalType.id });
                }

                // Regla 30 días: remover taxes (TODO: solo ITBIS)
                const orderDate = origin.date_order ? new Date(origin.date_order) : null;
                if (orderDate) {
                    const currentDate = new Date();
                    const diffDays = (currentDate - orderDate) / (1000 * 60 * 60 * 24);

                    if (diffDays > 30) {
                        const lines = newOrder.get_orderlines?.() || newOrder.orderlines || [];
                        for (const line of lines) {
                            if (line.set_taxes) {
                                line.set_taxes([]);
                            } else if (line.update) {
                                line.update({ tax_ids: [] });
                            } else {
                                line.tax_ids = [];
                            }
                        }
                    }
                }

                // Agregar línea de pago NC y avanzar a PaymentScreen
                newOrder.add_paymentline?.(creditNotePaymentMethod);

                if (this.pos.showScreen) {
                    this.pos.showScreen("PaymentScreen");
                } else if (this.showScreen) {
                    this.showScreen("PaymentScreen");
                }

                return true;
            } catch (error) {
                // fallback: limpiar orden refund si algo falla
                this.notification.add(_t("Error while preparing the refund order."), { type: "danger" });
                if (this.pos.add_new_order) {
                    this.pos.add_new_order();
                }
                if (this.pos.removeOrder && newOrder) {
                    this.pos.removeOrder(newOrder);
                }
                throw error;
            }
        }

        return await super.closeTicketScreen(...arguments);
    },

    _getSearchFields() {
        const fields = super._getSearchFields(...arguments);
        if (this.pos.config.l10n_do_fiscal_journal) {
            fields.NCF = {
                repr: (order) => order?.ncf || "",
                displayName: "NCF",
                modelField: "ncf",
            };
        }
        return fields;
    },
});
