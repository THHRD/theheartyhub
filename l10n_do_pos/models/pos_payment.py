import logging
from odoo import api, fields, models, _
from odoo.tools import float_is_zero
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PosPayment(models.Model):
    _inherit = 'pos.payment'

    credit_note_ncf = fields.Char(string="NCF Nota de Crédito")
    credit_note_partner_id = fields.Many2one("res.partner", string="Cliente Nota de Crédito")
    credit_note_source_order_id = fields.Many2one("pos.order", string="Orden origen Nota de Crédito")
    credit_note_ticket = fields.Char(string="Ticket Nota de Crédito")

    # ========================================================================
    # CREACIÓN DE account.payment REALES PARA DIARIOS FISCALES
    # Portado desde v17 (l10n_do_pos-c7835de2 / models/pos_payment.py).
    # Cuando el POS opera contra un diario fiscal, cada pago debe convertirse
    # en un account.payment contabilizado (no en un statement line agregado
    # por la sesión al cierre). Este override:
    #   - Crea 1 account.payment por cada pago bancario / tarjeta.
    #   - Agrupa todos los pagos en efectivo en un único account.payment.
    #   - Enlaza los pagos con Nota de Crédito a la factura rectificativa
    #     correspondiente (out_refund con NCF B04) para que cuadre el saldo.
    # Si el diario NO es fiscal, delega al comportamiento estándar.
    # ========================================================================

    def _get_payment_values(self, payment):
        amount = sum(payment.mapped('amount')) if len(payment) > 1 else payment.amount
        payment = payment[0] if len(payment) > 1 else payment
        payment_method = payment.payment_method_id
        payment_session = payment.session_id

        # NOTA: en Odoo 19 account.payment ya NO tiene el campo `ref`.
        # Lo reemplaza `memo`. Pasar `ref` provoca:
        #   ValueError: Invalid field 'ref' in 'account.payment'
        return {
            'amount': amount,
            'payment_type': 'inbound' if amount >= 0 else 'outbound',
            'date': payment.payment_date,
            'partner_id': payment.partner_id.id if payment.partner_id else False,
            'currency_id': payment.currency_id.id,
            'pos_session_id': payment_session.id,
            'memo': _('%s POS payments from %s') % (payment_method.name, payment_session.name),
            'pos_payment_method_id': payment_method.id,
            'journal_id': payment_method.journal_id.id,
        }

    def _create_payment_moves(self, is_reverse=False):
        if not self:
            return super()._create_payment_moves(is_reverse)

        config = self.mapped('session_id.config_id')[:1]
        if not config.l10n_do_fiscal_journal:
            return super()._create_payment_moves(is_reverse)

        result = self.env['account.move']

        # 1) Pagos bancarios / tarjeta (no efectivo y no nota de crédito)
        non_cash_non_cn = self.filtered(
            lambda p: not p.payment_method_id.is_cash_count
            and not p.payment_method_id.is_credit_note
        )
        for payment in non_cash_non_cn:
            order = payment.pos_order_id
            payment_method = payment.payment_method_id

            if payment_method.type == 'pay_later' or float_is_zero(
                payment.amount, precision_rounding=order.currency_id.rounding
            ):
                continue

            account_payment = self.env['account.payment'].create(
                self._get_payment_values(payment)
            )
            account_payment.action_post()
            account_payment.move_id.write({
                'pos_payment_ids': payment.ids,
            })
            payment.write({'account_move_id': account_payment.move_id.id})
            result |= account_payment.move_id

        # 2) Pagos en efectivo agrupados
        pos_payment_cash = self.filtered(
            lambda p: p.payment_method_id.is_cash_count
            and not p.payment_method_id.is_credit_note
        )
        if pos_payment_cash:
            account_payment_cash = self.env['account.payment'].create(
                self._get_payment_values(pos_payment_cash)
            )
            account_payment_cash.action_post()
            account_payment_cash.move_id.write({
                'pos_payment_ids': pos_payment_cash.ids,
            })
            pos_payment_cash.write({
                'account_move_id': account_payment_cash.move_id.id
            })
            result |= account_payment_cash.move_id

        # 3) Pagos con Nota de Crédito → enlazar a la factura rectificativa
        for credit_note in self.filtered(
            lambda p: p.payment_method_id.is_credit_note and (p.name or p.credit_note_ncf)
        ):
            ncf_ref = credit_note.credit_note_ncf or credit_note.name
            account_move_credit_note = self.env['account.move'].search([
                ('partner_id', '=', credit_note.partner_id.id),
                ('ref', '=', ncf_ref),
                ('move_type', '=', 'out_refund'),
                ('is_l10n_do_fiscal_invoice', '=', True),
                ('company_id', '=', self.env.company.id),
                ('state', '=', 'posted'),
            ], limit=1)

            if account_move_credit_note and credit_note.amount > 0:
                account_move_credit_note.write({
                    'pos_payment_ids': credit_note.ids,
                })
                credit_note.write({
                    'account_move_id': account_move_credit_note.id
                })
                result |= account_move_credit_note

        return result
