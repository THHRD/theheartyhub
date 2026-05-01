from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = "res.partner"

    ecf_contact_name  = fields.Char(string='Persona Contacto ECF')
