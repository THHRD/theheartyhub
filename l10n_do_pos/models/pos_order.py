import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.osv.expression import AND

_logger = logging.getLogger(__name__)


class PosOrder(models.Model):
    _inherit = 'pos.order'

    ncf = fields.Char(
        string='NCF',
        copy=False,
    )
    ncf_origin_out = fields.Char(
        string='Affects',
        copy=False,
    )
    ncf_expiration_date = fields.Date(
        string='NCF expiration date',
    )
    fiscal_type_id = fields.Many2one(
        string='Fiscal type',
        comodel_name='account.fiscal.type',
    )
    fiscal_sequence_id = fields.Many2one(
        string='Fiscal Sequence',
        comodel_name='account.fiscal.sequence',
        copy=False,
    )
    is_used_in_order = fields.Boolean(
        default=False
    )

    # factura electronica
    l10n_do_electronic_stamp = fields.Char(string="Electronic Stamp")
    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", copy=False)
    l10n_do_ecf_sign_date = fields.Datetime(string="e-CF Sign Date", copy=False)

    # devolucion nota de credito
    l10n_do_ecf_modification_code = fields.Selection(
        selection=lambda self: self.env["account.move"]._get_l10n_do_ecf_modification_code(),
        string="Codigo Motivo Nota Credito",
        copy=False,
        default="3",
    )
    ecf_modification_reason = fields.Char(string="Razon Nota Credito")

    ecf_modification_reason_id = fields.Many2one(
        "ecf.modification.reason",
        string="Razon predefinida Nota Credito",
        copy=False,
    )

    # campos auxiliares para la aplicacion de la nota de credito
    is_credit_note_voucher = fields.Boolean(
        string="Es Voucher de Nota de Credito",
        copy=False,
        default=False,
    )
    credit_note_amount_total = fields.Monetary(
        string="Credito Total",
        currency_field="currency_id",
        copy=False,
        default=0.0,
    )
    credit_note_amount_used = fields.Monetary(
        string="Credito Utilizado",
        currency_field="currency_id",
        copy=False,
        default=0.0,
    )
    credit_note_amount_available = fields.Monetary(
        string="Credito Disponible",
        currency_field="currency_id",
        copy=False,
        default=0.0,
    )
    credit_note_redeemed = fields.Boolean(
        string="Canjeada",
        copy=False,
        default=False,
    )

    def get_next_fiscal_sequence(self, fiscal_type_id, company_id, payments):
        """
        search active fiscal sequence dependent with fiscal type
        :return: {ncf, ncf_expiration_date, fiscal_sequence_id}
        """
        fiscal_type = self.env['account.fiscal.type'].search([
            ('id', '=', fiscal_type_id)
        ])

        if not fiscal_type:
            raise UserError(_('Fiscal type not found'))

        for payment in payments:
            if payment.get('returned_ncf', False):
                cn_invoice = self.env['account.move'].search([
                    ('ref', '=', payment['returned_ncf']),
                    ('move_type', '=', 'out_refund'),
                    ('is_l10n_do_fiscal_invoice', '=', True),
                ])
                if cn_invoice.amount_residual != cn_invoice.amount_total:
                    raise UserError(
                        _('This credit note (%s) has been used') % payment['returned_ncf']
                    )

        fiscal_sequence = self.env['account.fiscal.sequence'].search([
            ('fiscal_type_id', '=', fiscal_type.id),
            ('state', '=', 'active'),
            ('company_id', '=', company_id)
        ], limit=1)

        if not fiscal_sequence:
            raise UserError(
                _("There is no current active NCF of %(t1)s, please create a new fiscal sequence of type %(t2)s.") % {
                    't1': fiscal_type.name,
                    't2': fiscal_type.name,
                }
            )

        return {
            'ncf': fiscal_sequence.get_fiscal_number(),
            'fiscal_sequence_id': fiscal_sequence.id,
            'ncf_expiration_date': fiscal_sequence.expiration_date,
        }

    def get_credit_note(self, ncf):
        credit_note = self.env['account.move'].search([
            ('ref', '=', ncf),
            ('move_type', '=', 'out_refund'),
            ('is_l10n_do_fiscal_invoice', '=', True),
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'posted')
        ], limit=1)

        if not credit_note:
            raise UserError(_('Credit note not found'))

        return {
            'partner_id': credit_note.partner_id.id,
            'residual_amount': credit_note.amount_residual,
            'ncf': credit_note.ref,
        }

    def get_credit_notes(self, partner_id):
        credit_notes = self.env['account.move'].search([
            ('partner_id', '=', partner_id),
            ('move_type', '=', 'out_refund'),
            ('is_l10n_do_fiscal_invoice', '=', True),
            ('amount_residual', '>', 0.0),
            ('company_id', '=', self.env.company.id),
            ('state', '=', 'posted')
        ])

        if not credit_notes:
            raise UserError(_('This customer does not have credit notes'))

        return [{
            'id': credit_note.id,
            'label': "%s - %s %s" % (credit_note.ref, credit_note.currency_id.name, credit_note.amount_residual),
            'item': {
                'partner_id': credit_note.partner_id.id,
                'residual_amount': credit_note.amount_residual,
                'ncf': credit_note.ref,
            },
        } for credit_note in credit_notes]

    @api.model
    def search_paid_order_ids(self, config_id, domain, limit, offset):
        pos_config = self.env['pos.config'].browse(config_id)
        if pos_config.invoice_journal_id.l10n_do_fiscal_journal:
            config_ids = self.env['pos.config'].search([
                ('invoice_journal_id.l10n_do_fiscal_journal', '=', True),
            ]).ids

            domain += ['&', ('config_id', 'in', config_ids), ('ncf', 'not like', '%B04%')]

        result = super(PosOrder, self).search_paid_order_ids(config_id, domain, limit, offset)
        return result

    def _prepare_invoice_vals(self):
        vals = super()._prepare_invoice_vals()

        config = self.session_id.config_id
        if config.invoice_journal_id.l10n_do_fiscal_journal:
            # IMPORTANTE: pasar el NCF ya generado por el POS como `ref` del
            # move. Si se dejara vacio, el hook _post() de l10n_do_ncf
            # llamaria a fiscal_sequence.get_fiscal_number() UNA SEGUNDA VEZ
            # y la secuencia avanzaria de 2 en 2 (POS + move).
            vals["ref"] = self.ncf or False
            vals.update({
                "origin_out": self.ncf_origin_out or False,
                "fiscal_type_id": self.fiscal_type_id.id or False,
                "fiscal_sequence_id": self.fiscal_sequence_id.id or False,
                "ncf_expiration_date": self.ncf_expiration_date or False,
            })

            # Solo en out_refund manda motivo/razon
            if vals.get("move_type") == "out_refund":
                vals.update({
                    "l10n_do_ecf_modification_code": self.l10n_do_ecf_modification_code or "3",
                    "ecf_modification_reason": (self.ecf_modification_reason or "").strip() or False,
                })

        return vals

    def _generate_pos_order_invoice(self):
        # Evita PDF/email desde POS
        self = self.with_context(generate_pdf=False)

        # NOTA: super()._generate_pos_order_invoice() ya llama internamente
        # a `order_payments._create_payment_moves(is_session_closed)` (ver
        # addons/point_of_sale/models/pos_order.py:1174). Por lo tanto los
        # account.payment se crean automaticamente via nuestro override de
        # pos.payment._create_payment_moves — no hace falta llamarlo de nuevo
        # aqui.
        moves = super()._generate_pos_order_invoice()

        for order in self:
            move = order.account_move
            if move:
                order._sync_do_fields_from_move(move)

        return moves

    def sync_data_from_order(self):
        for order in self:
            move = order.account_move
            order._sync_do_fields_from_move(move)

    def _sync_do_fields_from_move(self, move):
        self.ensure_one()
        vals = {}

        if getattr(move, "ref", False):
            vals["ncf"] = move.ref

        if hasattr(move, "ncf_expiration_date") and move.ncf_expiration_date:
            vals["ncf_expiration_date"] = move.ncf_expiration_date

        if hasattr(move, "origin_out") and move.origin_out:
            vals["ncf_origin_out"] = move.origin_out

        if hasattr(move, "fiscal_type_id") and move.fiscal_type_id:
            vals["fiscal_type_id"] = move.fiscal_type_id.id

        if hasattr(move, "fiscal_sequence_id") and move.fiscal_sequence_id:
            vals["fiscal_sequence_id"] = move.fiscal_sequence_id.id

        # FACTURA ELECTRONICA
        if hasattr(move, "l10n_do_electronic_stamp") and move.l10n_do_electronic_stamp:
            vals["l10n_do_electronic_stamp"] = move.l10n_do_electronic_stamp

        if hasattr(move, "l10n_do_ecf_security_code") and move.l10n_do_ecf_security_code:
            vals["l10n_do_ecf_security_code"] = move.l10n_do_ecf_security_code

        if hasattr(move, "l10n_do_ecf_sign_date") and move.l10n_do_ecf_sign_date:
            vals["l10n_do_ecf_sign_date"] = move.l10n_do_ecf_sign_date

        if vals:
            self.write(vals)
        return vals

    # ======================================================================
    # LOGICA DE NOTAS DE CREDITO COMO METODO DE PAGO
    # ======================================================================

    @api.model
    def _extract_synced_order_ids(self, result):
        order_ids = []

        if isinstance(result, list):
            if result and isinstance(result[0], int):
                order_ids = result
            elif result and isinstance(result[0], dict):
                order_ids = [item.get("id") for item in result if item.get("id")]

        elif isinstance(result, dict):
            if result.get("pos.order") and isinstance(result["pos.order"], list):
                order_ids = [item.get("id") for item in result["pos.order"] if item.get("id")]

            elif result.get("pos_order_ids"):
                order_ids = result["pos_order_ids"]

            elif result.get("order_ids"):
                order_ids = result["order_ids"]

            elif result.get("orders") and isinstance(result["orders"], list):
                order_ids = [item.get("id") for item in result["orders"] if item.get("id")]

        return order_ids

    def _recompute_credit_note_voucher_state(self):
        Payment = self.env["pos.payment"].sudo()

        for order in self:
            issue_payments = order.payment_ids.filtered(lambda p: p.payment_method_id.is_credit_note)
            total_amount = sum(abs(amount) for amount in issue_payments.mapped("amount"))

            used_payments = Payment.search([
                ("credit_note_source_order_id", "=", order.id),
                ("pos_order_id", "!=", order.id),
            ])
            used_amount = sum(abs(amount) for amount in used_payments.mapped("amount"))

            is_voucher = bool(total_amount and order.amount_total < 0)
            available_amount = max(total_amount - used_amount, 0.0)

            order.write({
                "is_credit_note_voucher": is_voucher,
                "credit_note_amount_total": total_amount if is_voucher else 0.0,
                "credit_note_amount_used": used_amount if is_voucher else 0.0,
                "credit_note_amount_available": available_amount if is_voucher else 0.0,
                "credit_note_redeemed": bool(is_voucher and available_amount <= 0.0),
            })

    @api.model
    def search_credit_note_vouchers(self, query):
        query = (query or "").strip()
        if not query:
            raise UserError(_("Debe ingresar el ticket o el NCF de la nota de credito."))
        domain = [
            ("is_credit_note_voucher", "=", True),
            ("credit_note_redeemed", "=", False),
            ("credit_note_amount_available", ">", 0.0),
            ("company_id", "=", self.env.company.id),
            ("state", "in", ("paid", "invoiced")),
            "|",
            ("pos_reference", "ilike", query),
            ("ncf", "ilike", query),
        ]
        orders = self.search(domain, order="id desc", limit=20)

        if not orders:
            raise UserError(_("No se encontro una nota de credito disponible con ese ticket o NCF."))

        return [{
            "id": order.id,
            "label": "%s%s%s - Disponible: %s %s" % (
                order.pos_reference or "",
                " / " if order.pos_reference and order.ncf else "",
                order.ncf or "",
                order.currency_id.name,
                order.credit_note_amount_available,
            ),
            "item": order._get_credit_note_voucher_payload(),
        } for order in orders]

    @api.model
    def get_credit_note_voucher(self, order_id):
        order = self.browse(order_id).exists()
        if not order:
            raise UserError(_("La nota de credito no existe."))

        order._recompute_credit_note_voucher_state()

        if not order.is_credit_note_voucher or order.credit_note_amount_available <= 0.0:
            raise UserError(_("La nota de credito ya no tiene saldo disponible."))

        return order._get_credit_note_voucher_payload()

    def _get_credit_note_voucher_payload(self):
        self.ensure_one()
        return {
            "order_id": self.id,
            "partner_id": self.partner_id.id,
            "pos_reference": self.pos_reference,
            "ncf": self.ncf,
            "total_amount": self.credit_note_amount_total,
            "used_amount": self.credit_note_amount_used,
            "available_amount": self.credit_note_amount_available,
            "is_redeemed": self.credit_note_redeemed,
        }

    def _recompute_credit_note_voucher_usage(self):
        Payment = self.env["pos.payment"].sudo()

        for order in self:
            total_amount = abs(order.credit_note_amount_total or 0.0)

            if not total_amount and order.is_credit_note_voucher:
                total_amount = abs(order.amount_total or 0.0)

            used_payments = Payment.search([
                ("credit_note_source_order_id", "=", order.id),
                ("pos_order_id", "!=", order.id),
                ("payment_method_id.is_credit_note", "=", True),
                ("pos_order_id.state", "in", ("paid", "invoiced", "done")),
            ])

            used_amount = sum(abs(payment.amount) for payment in used_payments)

            if used_payments:
                available_amount = 0.0
                redeemed = True
            else:
                available_amount = total_amount
                redeemed = False

            order.write({
                "credit_note_amount_total": total_amount,
                "credit_note_amount_used": used_amount,
                "credit_note_amount_available": available_amount,
                "credit_note_redeemed": redeemed,
            })

    # ======================================================================
    # sync_from_ui: forzar la generacion de factura fiscal para ordenes POS
    # ======================================================================

    @api.model
    def sync_from_ui(self, orders):
        result = super().sync_from_ui(orders)

        try:
            synced_order_ids = self._extract_synced_order_ids(result)
        except Exception:
            _logger.exception("No se pudieron extraer IDs sincronizados del resultado de sync_from_ui")
            return result

        if not synced_order_ids:
            return result

        synced_orders = self.browse(synced_order_ids).exists()

        # --------------------------------------------------------------
        # FORZAR GENERACION DE FACTURA PARA ORDENES FISCALES
        # Toda orden enviada por un POS fiscal debe contabilizarse como
        # account.move + account.payment reales, no como el combinado de
        # receivables que genera el cierre estandar.
        # Los errores se LOGUEAN pero NO se propagan para no romper la
        # respuesta que el cliente POS espera (pos.order.line, etc).
        # --------------------------------------------------------------
        for order in synced_orders:
            try:
                config = order.config_id
                if not config.invoice_journal_id.l10n_do_fiscal_journal:
                    continue
                if order.state == "invoiced" or order.account_move:
                    continue
                if not order.amount_total:
                    continue

                # Asegurar partner_id
                if not order.partner_id:
                    if not config.pos_partner_id:
                        _logger.warning(
                            "POS fiscal %s sin cliente por defecto - no se factura %s",
                            config.display_name, order.display_name,
                        )
                        continue
                    order.write({"partner_id": config.pos_partner_id.id})

                # Asegurar fiscal_type_id
                if not order.fiscal_type_id:
                    if not config.default_fiscal_type_id:
                        _logger.warning(
                            "POS fiscal %s sin default_fiscal_type_id - no se factura %s",
                            config.display_name, order.display_name,
                        )
                        continue
                    order.write({"fiscal_type_id": config.default_fiscal_type_id.id})

                # Asegurar NCF: si el frontend no lo asigno, generarlo aqui
                if not order.ncf:
                    try:
                        payments = [{
                            "payment_method_id": p.payment_method_id.id,
                            "returned_ncf": p.credit_note_ncf or False,
                            "returned_partner_id": p.credit_note_partner_id.id if p.credit_note_partner_id else False,
                        } for p in order.payment_ids]
                        seq = order.get_next_fiscal_sequence(
                            order.fiscal_type_id.id,
                            order.company_id.id or self.env.company.id,
                            payments,
                        )
                        order.write({
                            "ncf": seq.get("ncf"),
                            "fiscal_sequence_id": seq.get("fiscal_sequence_id"),
                            "ncf_expiration_date": seq.get("ncf_expiration_date"),
                        })
                    except Exception:
                        _logger.exception(
                            "No se pudo asignar NCF a orden %s (fiscal_type=%s)",
                            order.display_name, order.fiscal_type_id.display_name,
                        )
                        continue

                if not order.ncf:
                    _logger.warning(
                        "Orden %s sigue sin NCF - se omite facturacion",
                        order.display_name,
                    )
                    continue

                # Marcar para facturar y generar el move
                if not order.to_invoice:
                    order.write({"to_invoice": True})

                order._generate_pos_order_invoice()
            except Exception:
                _logger.exception(
                    "Error generando factura fiscal para orden %s (NCF=%s)",
                    order.display_name, order.ncf,
                )

        # Recomputar estado de vouchers de nota de credito (best effort)
        try:
            voucher_orders = synced_orders.filtered(lambda o: o.is_credit_note_voucher)
            source_orders = synced_orders.payment_ids.filtered(
                lambda p: p.payment_method_id.is_credit_note and p.credit_note_source_order_id
            ).mapped("credit_note_source_order_id")
            (voucher_orders | source_orders)._recompute_credit_note_voucher_usage()
        except Exception:
            _logger.exception("Error recomputando estado de vouchers de nota de credito")

        return result
