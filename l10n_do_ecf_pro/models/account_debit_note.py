# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _
from odoo.exceptions import UserError

class AccountDebitNote(models.TransientModel):
    """
    Add Debit Note wizard: when you want to correct an invoice with a positive amount.
    Opposite of a Credit Note, but different from a regular invoice as you need the link to the original invoice.
    In some cases, also used to cancel Credit Notes
    """
    _inherit = 'account.debit.note'
    _description = 'Add Debit Note wizard'

    origin_out = fields.Char("Afecta A")
    
    def _get_defaul_type(self):
        """Devuelve el dominio basado en permisos del usuario."""
        fiscal = self.env['account.fiscal.type'].search([('prefix','=','E33'),('type','=','out_invoice')])
        for rec in  fiscal:
            return rec.id

    def _prepare_default_values(self, move):
         default_values = super(AccountDebitNote, self)._prepare_default_values(move)
         default_values['ref'] = None
         default_values['narration'] = self.reason
         default_values['origin_out'] = move.ref
         default_values['fiscal_type_id'] = self._get_defaul_type()

         return default_values
