/** @odoo-module **/

import {Component} from "@odoo/owl";
import {usePos} from "@point_of_sale/app/store/pos_hook";
import {useService} from "@web/core/utils/hooks";
import {makeAwaitable} from "@point_of_sale/app/store/make_awaitable_dialog";
import {SelectionPopup} from "@point_of_sale/app/utils/input_popups/selection_popup";
import {TextInputPopup} from "@point_of_sale/app/utils/input_popups/text_input_popup";
import {_t} from "@web/core/l10n/translation";

export class SetFiscalTypeButton extends Component {
    static template = "l10n_do_pos.SetFiscalTypeButton";
    static props = {}
    setup() {
        this.pos = usePos();
        this.dialog = useService("dialog");
        this.notification = useService("notification");
    }

    get currentOrder() {
        return this.pos.get_order();
    }

    get currentFiscalTypeName() {
        const order = this.currentOrder;
        const fiscalType = order?.get_fiscal_type?.() || order?.fiscal_type || false;
        return fiscalType ? fiscalType.name : _t("Select Fiscal Type");
    }

    _saleFiscalTypes() {
        const defaultSaleType = this.pos.models["account.fiscal.type"].filter((fiscaltype) =>
            fiscaltype.type === 'out_invoice');
        return (defaultSaleType);
    }


    _fiscalTypesForOrder(order) {
        const model = this.pos.models["account.fiscal.type"];
        if (!model) return [];

        if (order?._isRefundOrder?.()) {
            // Refund: solo out_refund (nota de crédito)
            return model.filter((ft) => ft.type === "out_refund");
        }
        // Venta normal
        return model.filter((ft) => ft.type === "out_invoice");
    }

    _findPartnerByVat(vat) {
        const value = (vat || "").trim();
        if (!value) return false;
        return this.pos.models["res.partner"].getBy("vat", value) || false;
    }



    async _ensurePartnerVat() {
        const order = this.currentOrder;
        if (!order) return false;

        while (true) {
            const vat = await makeAwaitable(this.dialog, TextInputPopup, {
                startingValue: "",
                title: _t("You need to select a customer with RNC or Cedula for this fiscal type."),
                placeholder: _t("RNC or Cedula"),
            });

            if (!vat) {
                // cancelado
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

            // Si no existe, permitir seleccionar/crear desde PartnerListScreen
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
    }

    async onClick() {
        const order = this.currentOrder;
        if (!order) return;

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

        if (!selected) return;

        const selectedFiscalType = selected.item || selected;
        if (!selectedFiscalType) return;

        const partner = order.get_partner?.();
        if (selectedFiscalType.requires_document && (!partner || !partner.vat)) {
            this.notification.add(_t("El contácto no tiene establecido el documento de identidad"), { type: "warning" });
            //const ok = await this._ensurePartnerVat();
            //if (!ok) return;
        }

        if (order.set_fiscal_type) {
            order.set_fiscal_type(selectedFiscalType);
        } else {
            this.notification.add(_t("Order method set_fiscal_type is not available."), { type: "danger" });
        }

        //configurar como factura
        order.set_to_invoice(true);
    }
}
