from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_do_fiscal_journal = fields.Boolean(
        related='pos_invoice_journal_id.l10n_do_fiscal_journal'
    )
    pos_partner_id = fields.Many2one(
        comodel_name='res.partner',
        related='pos_config_id.pos_partner_id', 
        readonly=False
    )

    pos_default_fiscal_type_id = fields.Many2one(
        comodel_name='account.fiscal.type',
        related='pos_config_id.default_fiscal_type_id',
        string='Tipo de comprobante por default',
        readonly=False
    )

