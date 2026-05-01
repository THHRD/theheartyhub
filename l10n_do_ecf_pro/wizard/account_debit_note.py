from odoo import models, fields, api, _
from odoo.exceptions import UserError, AccessError

DESCRIPTION_DEBIT_CODE = [
    ("2", _("02 - Text Correction")),
    ("3", _("03 - Amount correction")),
    ("4", _("04 - NCF replacement issued in contingency")),
    ("5", _("05 - Reference Electronic Consumer Invoice")),
]

class AccountDebitNote(models.TransientModel):
    _inherit = "account.debit.note"

    @api.model
    def _get_l10n_do_debit_type_selection(self):
        selection = [
            ("percentage", _("Percentage")),
            ("fixed_amount", _("Amount")),
        ]
        return selection

    @api.model
    def _get_l10n_do_default_debit_type(self):
        return "percentage"

    @api.model
    def _get_l10n_do_debit_action_selection(self):

        return [
            ("draft_debit", _("Draft debit")),
            ("apply_debit", _("Apply debit")),
        ]

    l10n_do_debit_type = fields.Selection(
        selection=_get_l10n_do_debit_type_selection,
        default=_get_l10n_do_default_debit_type,
        string="Debit Type",
    )
    l10n_do_debit_action = fields.Selection(
        selection=_get_l10n_do_debit_action_selection,
        default="draft_debit",
        string="Action",
    )
    l10n_do_percentage = fields.Float(
        help="Debit Note based on origin invoice percentage",
        string="Percentage",
    )
    l10n_do_amount = fields.Float(
        help="Debit Note based fixed amount",
        string="Amount",
    )
    l10n_do_account_id = fields.Many2one(
        "account.account",
        string="Account",
        domain=[("deprecated", "=", False)],
    )
    # l10n_do_ecf_modification_code = fields.Selection(
    #     selection=lambda self: self.env[
    #         "account.move"
    #     ]._get_l10n_do_ecf_modification_code(),
    #     string="e-CF Modification Code",
    #     copy=False,
    # )
    l10n_do_ecf_modification_code = fields.Selection(DESCRIPTION_DEBIT_CODE,
        string="e-CF Modification Code",
        copy=False,
    )
    is_ecf_invoice = fields.Boolean(
        string="Is Electronic Invoice",
    )
    ref = fields.Char(
        string="Reference",
        help="Vendor reference used when creating a debit note on a vendor bill.",
    )
    fiscal_type_id = fields.Many2one(
        "account.fiscal.type",
        string="Fiscal Type",
        help="Tipo de comprobante fiscal a utilizar al crear la nota de débito.",
    )

    @api.model
    def default_get(self, fields_list):

        res = super(AccountDebitNote, self).default_get(fields_list)

        move_ids = (
            self.env["account.move"].browse(self.env.context["active_ids"])
            if self.env.context.get("active_model") == "account.move"
            else self.env["account.move"]
        )

        if not move_ids:
            raise UserError(_("No invoice found for this operation"))
        
      
        # Setting default account
        journal = move_ids[0].journal_id
        """
        res["l10n_do_account_id"] = journal.default_account_id.id
        #res["l10n_latam_use_documents"] = journal.l10n_latam_use_documents

        # Do not allow Debit Notes if Comprobante de Compra or Gastos Menores
        if move_ids[0].l10n_latam_document_type_id.l10n_do_ncf_type in (
            "informal",
            "minor",
            "e-informal",
            "e-minor",
        ):
            raise UserError(
                _("You cannot issue Credit/Debit Notes for %s document type")
                % move_ids_use_document.l10n_latam_document_type_id.name
            )

        if len(move_ids_use_document) > 1:
            raise UserError(
                _("You cannot create Debit Notes from multiple documents at a time.")
            )
        else:
            res["is_ecf_invoice"] = (
                move_ids_use_document and move_ids_use_document[0].is_ecf_invoice
            )
        """

        return res

    @api.onchange("move_ids")
    def _onchange_move_id(self):
        if (
            self.move_ids
            and self.move_ids[0].journal_id.l10n_do_fiscal_journal
        ):
            move_id = self.move_ids[0]
            move_type = "out_invoice" if move_id.is_sale_document() else "in_invoice"
            move = (
                self.env["account.move"]
                .with_context(internal_type="debit_note")
                .new(
                    {
                        "partner_id": move_id.partner_id.id,
                        "move_type": move_type,
                        "journal_id": move_id.journal_id.id,
                    }
                )
            )
            """
            domain_ids = (
                self.env["account.fiscal.type"]
                .search([('prefix','=','E33'),('type',,'out_invoice')])
                .ids
            )
            self.l10n_latam_document_type_id = domain_ids[0]
            return {
                "domain": {
                    "l10n_latam_document_type_id": [
                        (
                            "id",
                            "in",
                            domain_ids,
                        )
                    ]
                }
            }
            """
    
    def _get_defaul_type(self):
        """Devuelve el dominio basado en permisos del usuario."""
        fiscal = self.env['account.fiscal.type'].search([('prefix','=','E33'),('type','=','out_invoice')])
        for rec in  fiscal:
            return rec.id
       

    def _prepare_default_values(self, move):

        #res = super(AccountDebitNote, self)._prepare_default_values(move)
        
        default_values = super(AccountDebitNote, self)._prepare_default_values(move)
        default_values['ref'] = self.ref or None
        default_values['narration'] = self.reason
        default_values['origin_out'] = move.ref
        default_values['fiscal_type_id'] = self._get_defaul_type()

        return default_values


    def create_debit(self):

        """ Properly compute the latam document type of type debit note. """

       
        self = self.with_context(
            l10n_do_debit_type=self.l10n_do_debit_type,
            amount=self.l10n_do_amount,
            percentage=self.l10n_do_percentage,
            reason=self.reason,
        )

        # action = super(AccountDebitNote, self).create_debit()

        res = super().create_debit()
        #new_move_id = res.get('res_id')
        #if new_move_id:
        #    new_move = self.env['account.move'].browse(new_move_id)
        #    new_move._compute_l10n_latam_document_type()

        if self.l10n_do_debit_action == "apply_debit":
            # Post Debit Note
            move_id = self.env["account.move"].browse(res.get("res_id", False))
            move_id._post()

        return res