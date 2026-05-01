/** @odoo-module **/

import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { sprintf } from "@web/core/utils/strings";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { SelectionPopup } from "@point_of_sale/app/components/popups/selection_popup/selection_popup";
import { TextInputPopup } from "@point_of_sale/app/components/popups/text_input_popup/text_input_popup";
import { enhancedButtons } from "@point_of_sale/app/components/numpad/numpad";

async function ensureCreditNoteReason({ order, dialog, notification, pos }) {
    if (!order?._isRefundOrder?.()) {
        return true;
    }

    const currentCode = order.l10n_do_ecf_modification_code || "3";
    const currentReason = (order.ecf_modification_reason || "").trim();

    if (currentReason) {
        return true;
    }

    const codeList = [
        { id: "1", label: _t("01 - Anulación total"), item: "1", isSelected: currentCode === "1" },
        { id: "2", label: _t("02 - Corrección de texto"), item: "2", isSelected: currentCode === "2" },
        { id: "3", label: _t("03 - Corrección de monto"), item: "3", isSelected: currentCode === "3" },
        { id: "4", label: _t("04 - Reemplazo de NCF emitido en contingencia"), item: "4", isSelected: currentCode === "4" },
        { id: "5", label: _t("05 - Referencia de factura electrónica de consumo"), item: "5", isSelected: currentCode === "5" },
    ];

    const selectedCode = await makeAwaitable(dialog, SelectionPopup, {
        title: _t("Código motivo Nota de Crédito"),
        list: codeList,
    });

    if (!selectedCode) {
        notification.add(_t("Debe seleccionar un código de motivo para la Nota de Crédito."), {
            type: "warning",
        });
        return false;
    }

    const selectedCodeValue = selectedCode.item || selectedCode;

    const presetReasons = (pos.models["ecf.modification.reason"]?.getAll?.() || []).map((reason) => ({
        id: reason.id,
        label: reason.name,
        item: reason,
        isSelected: false,
    }));

    presetReasons.push({
        id: "other",
        label: _t("Otro"),
        item: {
            id: false,
            name: _t("Otro"),
            is_other: true,
        },
        isSelected: false,
    });

    const selectedReason = await makeAwaitable(dialog, SelectionPopup, {
        title: _t("Razón Nota de Crédito"),
        list: presetReasons,
    });

    if (!selectedReason) {
        notification.add(_t("Debe seleccionar una razón para la Nota de Crédito."), {
            type: "warning",
        });
        return false;
    }

    const reasonItem = selectedReason.item || selectedReason;
    let reasonText = "";
    let reasonId = false;

    if (reasonItem.is_other) {
        const customReason = await makeAwaitable(dialog, TextInputPopup, {
            title: _t("Ingrese la razón Nota de Crédito"),
            placeholder: _t("Razón"),
            startingValue: "",
        });

        if (!customReason || !String(customReason).trim()) {
            notification.add(_t("Debe ingresar la razón de la Nota de Crédito."), {
                type: "warning",
            });
            return false;
        }

        reasonText = String(customReason).trim();
    } else {
        reasonId = reasonItem.id;
        reasonText = reasonItem.name;
    }

    if (order.set_ecf_modification_reason_data) {
        order.set_ecf_modification_reason_data({
            code: selectedCodeValue,
            reason: reasonText,
            reason_id: reasonId,
        });
    } else {
        order.update({
            l10n_do_ecf_modification_code: selectedCodeValue,
            ecf_modification_reason: reasonText,
            ecf_modification_reason_id: reasonId,
        });
    }

    return true;
}

patch(PaymentScreen.prototype, {
    get currentFiscalTypeName() {
        const order = this.currentOrder;
        const fiscalType = order?.get_fiscal_type?.() || order?.fiscal_type || false;
        return fiscalType ? fiscalType.name : _t("Select Fiscal Type");
    },

    _fiscalTypesForOrder(order) {
        const model = this.pos.models["account.fiscal.type"];
        if (!model) {
            return [];
        }
        if (order?._isRefundOrder?.()) {
            return model.filter((ft) => ft.type === "out_refund");
        }
        return model.filter((ft) => ft.type === "out_invoice");
    },

    _findPartnerByVat(vat) {
        const value = (vat || "").trim();
        if (!value) {
            return false;
        }
        return this.pos.models["res.partner"]?.getBy("vat", value) || false;
    },

    async _ensurePartnerVat() {
        const order = this.currentOrder;
        if (!order) {
            return false;
        }
        while (true) {
            const vat = await makeAwaitable(this.dialog, TextInputPopup, {
                startingValue: "",
                title: _t("You need to select a customer with RNC or Cedula for this fiscal type."),
                placeholder: _t("RNC or Cedula"),
            });
            if (!vat) {
                return false;
            }
            const value = String(vat).trim();
            const isValidLength = value.length === 9 || value.length === 11;
            const isNumeric = !Number.isNaN(Number(value));
            if (!isValidLength || !isNumeric) {
                this.notification.add(
                    _t("Please ensure the RNC has exactly 9 digits or the Cedula has 11 digits."),
                    { type: "danger" }
                );
                continue;
            }
            const partnerFound = this._findPartnerByVat(value);
            if (partnerFound) {
                order.set_partner(partnerFound);
                return true;
            }
            if (!this.pos.showTempScreen) {
                this.notification.add(_t("Partner screen is not available in this POS configuration."), {
                    type: "danger",
                });
                return false;
            }
            const { confirmed, payload: newPartner } = await this.pos.showTempScreen("PartnerListScreen", {
                partner: order.get_partner?.(),
            });
            if (confirmed && newPartner) {
                order.set_partner(newPartner);
                if (order.updatePricelist) {
                    order.updatePricelist(newPartner);
                }
                return true;
            }
            return false;
        }
    },

    async onClickSetFiscalType() {
        const order = this.currentOrder;
        if (!order) {
            return;
        }
        const currentFiscalType = order.get_fiscal_type?.() || order.fiscal_type || false;
        const types = this._fiscalTypesForOrder(order);
        const fiscalPosList = types.map((ft) => ({
            id: ft.id,
            label: ft.name,
            isSelected: currentFiscalType ? ft.id === currentFiscalType.id : false,
            item: ft,
        }));
        if (!fiscalPosList.length) {
            this.notification.add(_t("No fiscal types available for POS."), { type: "warning" });
            return;
        }
        const selected = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Select Fiscal Type"),
            list: fiscalPosList,
        });
        if (!selected) {
            return;
        }
        const selectedFiscalType = selected.item || selected;
        if (!selectedFiscalType) {
            return;
        }
        const partner = order.get_partner?.();
        if (selectedFiscalType.requires_document && (!partner || !partner.vat)) {
            this.notification.add(_t("El contácto no tiene establecido el documento de identidad"), {
                type: "warning",
            });
        }
        if (order.set_fiscal_type) {
            order.set_fiscal_type(selectedFiscalType);
        } else {
            this.notification.add(_t("Order method set_fiscal_type is not available."), { type: "danger" });
        }
        order.set_to_invoice(true);
    },

    async _isOrderValid(isForceValidate) {
        const ok = await super._isOrderValid(isForceValidate);
        if (!ok) return false;

        const order = this.currentOrder;
        const client = order?.get_partner?.();
        const total = order?.get_total_with_tax?.() ?? 0;
        const fiscalType = order?.get_fiscal_type?.() || order?.fiscal_type || false;

        if (total === 0) {
            this.notification.add(_t("You cannot make sales in 0, please add a product with value"), {
                type: "warning",
            });
            return false;
        }

        if (this.pos.config.l10n_do_fiscal_journal) {
            const methodsOk = await this.analyze_payment_methods();
            if (!methodsOk) return false;

            if (!fiscalType) {
                this.notification.add(_t("Please select a fiscal type"), { type: "warning" });
                return false;
            }

            if (fiscalType.requires_document && !client) {
                this.notification.add(
                    sprintf(_t("For invoice fiscal type %s its necessary customer, please select customer"), fiscalType.name),
                    { type: "warning" }
                );
                return false;
            }

            if (fiscalType.requires_document && !client?.vat) {
                this.notification.add(
                    sprintf(_t("For invoice fiscal type %s it is necessary for the customer have RNC or Cedula"), fiscalType.name),
                    { type: "warning" }
                );
                return false;
            }

            if (fiscalType.requires_document && !(client.vat.length === 9 || client.vat.length === 11)) {
                this.notification.add(
                    sprintf(_t("For invoice fiscal type %s it is necessary for the customer have correct RNC or Cedula without dashes or spaces"), fiscalType.name),
                    { type: "warning" }
                );
                return false;
            }

            if (total >= 250000.0 && (!client || !client.vat)) {
                this.notification.add(_t("For this sale it is necessary for the customer have ID"), { type: "warning" });
                return false;
            }

            if (fiscalType?.prefix === "B14") {
                let hasTaxes = false;
                const lines = order?.get_orderlines?.() || [];
                for (const line of lines) {
                    const taxes = line?._getProductTaxesAfterFiscalPosition?.() || line?.get_taxes?.() || [];
                    for (const tax of taxes) {
                        const tgName = Array.isArray(tax?.tax_group_id) ? tax.tax_group_id[1] : tax?.tax_group_id?.name;
                        if ((tgName === "ITBIS" && tax.amount !== 0) || tgName === "ISC") {
                            hasTaxes = true;
                            break;
                        }
                    }
                    if (hasTaxes) break;
                }
                if (hasTaxes) {
                    this.notification.add(
                        sprintf(_t("You cannot pay order of Fiscal Type %s with ITBIS/ISC. Please select correct fiscal position for remove ITBIS and ISC"), fiscalType.name),
                        { type: "warning" }
                    );
                    return false;
                }
            }
        }

        const okReason = await ensureCreditNoteReason({
            order: this.currentOrder,
            dialog: this.dialog,
            notification: this.notification,
            pos: this.pos,
        });
        if (!okReason) return false;

        return true;
    },

    async _finalizeValidation() {
        const order = this.currentOrder;
        if (this.pos.config.l10n_do_fiscal_journal && !order?.ncf) {
            const fiscalType = order?.get_fiscal_type?.() || order?.fiscal_type || false;
            if (!fiscalType) {
                this.notification.add(_t("Please select a fiscal type"), { type: "warning" });
                return;
            }
        }
        return await super._finalizeValidation();
    },

    async _selectCreditNoteVoucher() {
        const query = await makeAwaitable(this.dialog, TextInputPopup, {
            startingValue: "",
            title: _t("Escanee o ingrese el ticket o NCF de la Nota de Crédito"),
            placeholder: _t("Ticket o NCF"),
        });
        if (!query) {
            return false;
        }
        const vouchers = await this.pos.search_credit_note_vouchers(query);
        if (!vouchers.length) {
            this.notification.add(_t("No se encontró una nota de crédito disponible."), { type: "warning" });
            return false;
        }
        if (vouchers.length === 1) {
            return vouchers[0].item || vouchers[0];
        }
        const selected = await makeAwaitable(this.dialog, SelectionPopup, {
            title: _t("Seleccione la Nota de Crédito"),
            list: vouchers,
        });
        if (!selected) {
            return false;
        }
        return selected.item || selected;
    },

    async addNewPaymentLine(ev) {
        const paymentMethod = ev?.detail || ev;
        const order = this.currentOrder;
        if (!this.pos.config.l10n_do_fiscal_journal || !paymentMethod?.is_credit_note) {
            return await super.addNewPaymentLine(...arguments);
        }
        if (order._isRefundOrder?.()) {
            return await super.addNewPaymentLine(...arguments);
        }
        const voucher = await this._selectCreditNoteVoucher();
        if (!voucher) {
            return false;
        }
        const sourceOrderId = voucher.credit_note_source_order_id || voucher.order_id || voucher.id || false;
        const paymentLines = order.get_paymentlines?.() || [];
        for (const line of paymentLines) {
            if (line.payment_method_id?.is_credit_note && line.credit_note_source_order_id === sourceOrderId) {
                this.notification.add(_t("Esta nota de crédito ya fue agregada en la orden."), { type: "warning" });
                return false;
            }
        }
        if ((voucher.available_amount || 0) <= 0) {
            this.notification.add(_t("La nota de crédito ya no tiene saldo disponible."), { type: "warning" });
            return false;
        }
        const partner = voucher.partner_id ? this.pos.models["res.partner"].getBy("id", voucher.partner_id) : false;
        if (!order.get_partner?.() && partner) {
            order.set_partner?.(partner);
        }
        const amountDueBefore = Math.abs(order.get_due?.() ?? 0);
        const amountToApply = Math.min(Math.abs(voucher.available_amount || 0), amountDueBefore);
        const newLine = order.add_paymentline?.(paymentMethod);
        if (!newLine) {
            return false;
        }
        newLine.set_credit_note_data?.({ ...voucher, credit_note_source_order_id: sourceOrderId });
        newLine.set_amount?.(amountToApply);
        return true;
    },

    updateSelectedPaymentline(amount = false) {
        if (this._isCreditNoteAmountLocked()) {
            const currentAmount = this.selectedPaymentLine?.amount || 0;
            this.numberBuffer.set(String(currentAmount));
            return;
        }
        return super.updateSelectedPaymentline(...arguments);
    },

    getNumpadButtons() {
        const colorClassMap = {
            [this.env.services.localization.decimalPoint]: "o_colorlist_item_numpad_color_6",
            Backspace: "o_colorlist_item_numpad_color_1",
            "+10": "o_colorlist_item_numpad_color_10",
            "+20": "o_colorlist_item_numpad_color_10",
            "+50": "o_colorlist_item_numpad_color_10",
            "-": "o_colorlist_item_numpad_color_3",
        };
        const buttons = enhancedButtons().map((button) => ({
            ...button,
            class: colorClassMap[button.value] || "",
        }));
        if (!this._isCreditNoteAmountLocked()) {
            return buttons;
        }
        return buttons.map((btn) => ({ ...btn, disabled: true }));
    },

    _isCreditNoteAmountLocked() {
        const line = this.selectedPaymentLine;
        return !!(this.pos.config.l10n_do_fiscal_journal && line && line.payment_method_id?.is_credit_note);
    },

    async analyze_payment_methods() {
        const order = this.currentOrder;
        const total = order?.get_total_with_tax?.() ?? 0;
        let totalInBank = 0;
        let hasCash = false;
        const paymentLines = order?.get_paymentlines?.() || [];
        for (const pl of paymentLines) {
            if (pl.payment_method?.type === "bank") {
                totalInBank = +Number(pl.amount);
            }
            if (pl.payment_method?.type === "cash") {
                hasCash = true;
            }
            if (pl.payment_method?.is_credit_note && !order._isRefundOrder?.()) {
                if (!pl.credit_note_source_order_id) {
                    this.notification.add(
                        _t("Hay un error en la nota de crédito aplicada. Elimine la línea y agréguela nuevamente."),
                        { type: "warning" }
                    );
                    return false;
                }
                const voucher = await this.pos.get_credit_note_voucher(pl.credit_note_source_order_id);
                if ((voucher.available_amount || 0) <= 0) {
                    this.notification.add(_t("La nota de crédito ya no tiene saldo disponible."), { type: "warning" });
                    return false;
                }
                if (Math.abs(pl.amount || 0) > Math.abs(voucher.available_amount || 0)) {
                    this.notification.add(_t("El monto aplicado excede el saldo disponible de la nota de crédito."), { type: "warning" });
                    return false;
                }
            }
        }
        if (Math.abs(Math.round(Math.abs(total) * 100) / 100) < Math.round(Math.abs(totalInBank) * 100) / 100) {
            this.notification.add(_t("Card payments cannot exceed the total order"), { type: "warning" });
            return false;
        }
        if (Math.round(Math.abs(totalInBank) * 100) / 100 === Math.round(Math.abs(total) * 100) / 100 && hasCash) {
            this.notification.add(
                _t("The total payment with the card is sufficient to pay the order, please eliminate the payment in cash or reduce the amount to be paid by card"),
                { type: "warning" }
            );
            return false;
        }
        return true;
    },

    shouldDownloadInvoice() {
        return false;
    },
});
