from odoo import models, fields, api, _


class PosSession(models.Model):
    _inherit = 'pos.session'


    def _load_pos_data_models(self, config_id):
        models_to_load = super()._load_pos_data_models(config_id)
        if "account.fiscal.type" not in models_to_load:
            models_to_load.append("account.fiscal.type")
        if "ecf.modification.reason" not in models_to_load:
            models_to_load.append("ecf.modification.reason")
        return models_to_load

    def _loader_params_res_partner(self):
        result = super()._loader_params_res_partner()
        result['search_params']['fields'].append('sale_fiscal_type_id')
        return result

    def _loader_params_account_tax(self):
        result = super()._loader_params_account_tax()
        result['search_params']['fields'].append('tax_group_id')
        return result

    # ========================================================================
    # CIERRE DE SESIÓN FISCAL
    # Cuando la sesión opera contra un diario fiscal (l10n_do_fiscal_journal),
    # las ventas se contabilizan vía FACTURAS + PAGOS reales (account.payment)
    # en lugar del combinado/split de receivables y cash moves que Odoo genera
    # por defecto al cerrar la sesión POS. Estos 3 overrides neutralizan ese
    # combinado para evitar dobles asientos contables.
    # Portado desde la versión 17 (l10n_do_pos-c7835de2).
    # ========================================================================

    def _create_invoice_receivable_lines(self, data):
        if self.config_id.l10n_do_fiscal_journal:
            data.update({
                'combine_invoice_receivable_lines': {},
                'split_invoice_receivable_lines': {},
            })
            return data
        return super()._create_invoice_receivable_lines(data)

    def _create_bank_payment_moves(self, data):
        if self.config_id.l10n_do_fiscal_journal:
            data.update({
                'payment_method_to_receivable_lines': {},
                'payment_to_receivable_lines': {},
                'online_payment_to_receivable_lines': {},
            })
            return data
        return super()._create_bank_payment_moves(data)

    def _create_cash_statement_lines_and_cash_move_lines(self, data):
        if self.config_id.l10n_do_fiscal_journal:
            AccountMoveLine = self.env['account.move.line']
            data.update({
                'split_cash_receivable_lines': AccountMoveLine,
                'split_cash_statement_lines': AccountMoveLine,
                'combine_cash_receivable_lines': AccountMoveLine,
                'combine_cash_statement_lines': AccountMoveLine,
            })
            return data
        return super()._create_cash_statement_lines_and_cash_move_lines(data)
