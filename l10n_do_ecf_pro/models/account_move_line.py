from odoo import models, fields

class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # l10n_do_itbis_amount = fields.Monetary(
    #     string="ITBIS Amount",
    #     store=True,
    #     readonly=True,
    #     currency_field="currency_id",
    # )
    
    ecf_decimal_precision  = fields.Integer(string="Price Decimal ECF",default = 2) # 5/5/2025 para los errores de la certificacion en lineas con 4 decimales
    ecf_currency_precision  = fields.Integer(string="Currency  Decimal ECF",default = 4) # 9/5/2025 para los errores de la certificacion en lineas con 4 decimales
    ecf_quantity_precision  = fields.Integer(string="Decimal ECF QTY",default = 2) # 5/5/2025 para los errores de la certificacion en lineas con 4 decimales
    ecf_tipo_ajuste  = fields.Selection([('D','D'),('R','R')],string="ECF Tipo Ajuste" ,default = 'D') # E32 6/5/2025 certificacion piden otros tipos de ajuste
    ecf_monto_descuento  = fields.Integer(string="Desc Pronto Pago",default = 0) #  E32 6/5/2025 piden un valor independiente del subtotal 
    fecha_elaboracion  = fields.Date(string="Fecha Elaboracion")
    fecha_vencimiento = fields.Date(string="Fecha Vencimiento")
    FechaElaboracion = fields.Date(string="Fecha Elaboración", copy=False)
    FechaVencimientoItem = fields.Date(string="Fecha Vencimiento", copy=False)

    def _get_price_total_and_subtotal(
        self,
        price_unit=None,
        quantity=None,
        discount=None,
        currency=None,
        product=None,
        partner=None,
        taxes=None,
        move_type=None,
    ):
        self.ensure_one()
        res = super(AccountMoveLine, self)._get_price_total_and_subtotal(
            price_unit=price_unit,
            quantity=quantity,
            discount=discount,
            currency=currency,
            product=product,
            partner=partner,
            taxes=taxes,
            move_type=move_type,
        )

        if self.move_id.is_ecf_invoice:

            # line_itbis_taxes = self.tax_ids.filtered(
            #     lambda t: t.tax_group_id == self.env.ref("l10n_do.group_itbis")
            # )
            line_itbis_taxes = self.tax_ids.filtered(
                lambda t: t.tax_group_id.name in ('ITBIS1','ITBIS2')
            )
            itbis_taxes_data = line_itbis_taxes.compute_all(
                price_unit=self.price_unit,
                quantity=self.quantity,
            )
            res["l10n_do_itbis_amount"] = sum(
                [t["amount"] for t in itbis_taxes_data["taxes"]]
            )
        return res
