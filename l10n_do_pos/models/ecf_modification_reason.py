from odoo import api, fields, models


class EcfModificationReason(models.Model):
    _name = "ecf.modification.reason"
    _description = "Razones predefinidas para Nota de Crédito"
    _order = "sequence, id"
    _inherit = ["pos.load.mixin"]

    name = fields.Char(string="Razón", required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    @api.model
    def _load_pos_data_fields(self, config_id):
        return [
            "id",
            "name",
            "sequence",
        ]

    @api.model
    def _load_pos_data_domain(self, data, config):
        return [("active", "=", True)]
