
from odoo import models, api, fields, _
from odoo.exceptions import UserError


class AccountMoveCancel(models.TransientModel):
    """
    This wizard will cancel the all the selected invoices.
    If in the journal, the option allow cancelling entry is not selected then
    it will give warning message.
    """

    _name = "account.move.cancel"
    _description = "Cancel the Selected Invoice"

    annulation_type = fields.Selection([
            ("01", "01 - Pre-printed Invoice Deterioration"),
            ("02", "02 - Printing Errors (Pre-printed Invoice)"),
            ("03", "03 - Defective Printing"),
            ("04", "04 - Information Correction"),
            ("05", "05 - Product Change"),
            ("06", "06 - Product Return"),
            ("07", "07 - Product Omission"),
            ("08", "08 - NCF Sequence Errors"),
            ("09", "09 - Due to Operations Cessation"),
            ("10", "10 - Loss or Theft of Checkbooks"),
        ],
        required=True,
        default=lambda self: self._context.get('annulation_type', '04'))

    def invoice_cancel(self):
        context = dict(self._context or {})
        active_ids = context.get('active_ids', []) or []
        
        for record in self.env['account.move'].browse(active_ids):
            if record.state == 'cancel' or record.payment_state in ('paid', 'in_payment'): 
                raise UserError(
                    _("Selected invoice(s) cannot be cancelled as they are "
                      "already in 'Cancelled' or 'Paid' state."))
            record.annulation_type = self.annulation_type
            record.with_context(skip_cancel_wizard=True).button_cancel()

        return {'type': 'ir.actions.act_window_close'}
