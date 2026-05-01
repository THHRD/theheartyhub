from odoo import fields, models, api, _
from .sign import XMLSignature
import base64


class Company(models.Model):
	_inherit = "res.company"

	cert = fields.Binary(string="Certificate", copy=False)
	cert_password = fields.Char(string="Certificate password", copy=False)

	cert_subject_name = fields.Char(string="Datos certificado", readonly=True)
	cert_date_ini = fields.Date(string="Expedido", copy=False, readonly=True)
	cert_date_end = fields.Date(string="Expira", copy=False, readonly=True)
	cert_owner_name = fields.Char(string="Propietario", copy=False, readonly=True)
	cert_issuer_name = fields.Char(string="Nombre Emisor", copy=False, readonly=True)

	cert_response_verify = fields.Text(string="Response")

	l10n_do_ecf_ambiente = fields.Selection([
		('TesteCF', 'TesteCF - Ambiente de pre-certificación'),
		('CerteCF', 'CerteCF - Ambiente de certificación'),
		('eCF', 'eCF - Ambiente de producción')
	], string='Ambiente', copy=False)

	def action_verifiy(self):
		try:
			from digital_certificate.cert import Certificate
		except ImportError:
			self.cert_response_verify = (
				"Falta el paquete Python 'digital_certificate'. "
				"Instalar con: pip install python-digital-certificate"
			)
			return
		try:
			key = base64.b64decode(self.cert)
			_cert = Certificate(
					pfx_file=key,
					password=bytes(self.cert_password, 'utf-8'))

			_cert.read_pfx_file()

			if _cert.cert:
				self.cert_owner_name = _cert.common_name()
				self.cert_issuer_name = _cert.issuer()
				self.cert_subject_name = _cert.subject()
				self.cert_date_ini = _cert.not_valid_before()
				self.cert_date_end = _cert.not_valid_after()

			sign = XMLSignature(self.cert, self.cert_password, self.l10n_do_ecf_ambiente)
			kernel = sign._get_token_semilla()
			self.cert_response_verify = kernel
		except Exception as e:
			self.cert_owner_name = None
			self.cert_issuer_name = None
			self.cert_subject_name = None
			self.cert_date_ini = None
			self.cert_date_end = None
			self.cert_response_verify = str(e)
