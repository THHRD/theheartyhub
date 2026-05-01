from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError, AccessError
from datetime import datetime as dt
import qrcode
from io import BytesIO
import base64
import xml.etree.ElementTree as ET
from datetime import datetime,timedelta, timezone
import os
import xmlschema
from .sign import XMLSignature
from .sign_company import ecf_rnc, ecf_expiracion
import pytz
from werkzeug import urls
from urllib.parse import urlencode, quote,quote_plus
from lxml import etree
import logging

_logger = logging.getLogger(__name__)
"""
CICLO ECF (Origen -> Destino) (* Opcional)
1.-Emisor   (eCF)                  -> DGII
2.-DGII     (trackid)              -> Emisor
3.-Emisor   (eCF)                  -> Receptor
4.-Receptor (Acuse de Recibo)      -> Emisor*
5.-Receptor (Aprobacion Comercial) -> Emison*
6.-Recepton (Aprobacion Comercial) -> DGII*
"""
"""OBTENER LOS TOTALES Y RESUMEN IMPUESTOS,
Se deben crear los siguientes grupos de Impuestos:
ITBIS1 = 18% ITbis
ITBIS2 = 16% de Itbis
ITBIS3 = 0% de Itbis (Gravados per el cliente no paga ITBIS)
RITBIS = Retencion de Itbis
EXENTO = Exento
ISR    = Retencion de Impuestos Sobre la Renta
XXX-ISCE = Impuesto adicional selectivo Especifico (donde xxx es codigo DGII ejemplo 006-ISCE) 
XXX-ISCA = Impuesto adicional selectivo Advalorem
XXX-ISCO = Impuesto selectivo al consumo, Otros
"""
class AccountMove(models.Model):
    _inherit = "account.move"

    # l10n_do_account
    l10n_do_ecf_edi_file = fields.Binary("ECF XML File", copy=False, readonly=True)
    l10n_do_ecf_edi_file_name = fields.Char("ECF XML File Name", copy=False, readonly=True)
    l10n_do_ecf_sign_date = fields.Datetime(string="e-CF Sign Date", copy=False)
    l10n_do_ecf_security_code = fields.Char(string="e-CF Security Code", copy=False)
    is_ecf_invoice = fields.Boolean(compute="_compute_is_ecf_invoice",store=True)  #(compute="_compute_split_sequence", store=True)
    l10n_do_sequence_prefix = fields.Char(related="fiscal_type_id.prefix") #compute="_compute_split_sequence", store=True)
    l10n_do_electronic_stamp = fields.Char(string="Electronic Stamp", compute="_compute_l10n_do_electronic_stamp")
    # l10n_do_electronic_stamp = fields.Char(string="Electronic Stamp", store=True)

    l10n_do_ecf_trackid = fields.Char(string="e-CF Trackid firma", copy=False)
    l10n_do_ecf_qr_image = fields.Binary("QR Code", compute='_compute_l10n_do_electronic_stamp')
    l10n_do_ecf_response = fields.Char(string="Repuesta validación DGII", tracking=True, copy=False)
    l10n_do_fc_edi_file = fields.Binary("FC XML File", copy=False, readonly=True)
    l10n_do_ecf_status = fields.Selection([
                                     ('0', '0-No encontrado'),
                                     ('1', '1-Aceptado'),
                                     ('2', '2-Rechazado'),
                                     ('3', '3-En Proceso'), 
                                     ('4', '4-Aceptado Condicional'),
                                     ('5', '5-Error interno ODOO')
                                     ], copy=False)
    l10n_do_ecf_ambiente = fields.Selection([
        ('TesteCF', 'TesteCF - pre-certificación'),
        ('CerteCF', 'CerteCF - certificación'),
        ('eCF', 'eCF - producción')
    ], string='Ambiente', copy=False,
    default=lambda self: self.env.user.company_id.l10n_do_ecf_ambiente)
    l10n_do_ecf_xml_validation = fields.Char(string="validación Formato XML", tracking=True, copy=False)

    #CAMPOS EXTRAS DGII ECF INFORMACIONES ADICIONALES
    fecha_entrega = fields.Date(string="Fecha Entrega", copy=False)
    fecha_orden_compra = fields.Date(string="Fecha Orden Compra", copy=False)
    fecha_embarque = fields.Date(string="Fecha Embarque", copy=False)
    numero_embarque = fields.Char(string="Numero Embarque", copy=False, size=25)
    numero_contenedor = fields.Char(string="Numero Contenedor", copy=False, size=100)
    numero_referencia = fields.Char(string="Numero Referencia", copy=False, size=20)
    nombre_puerto_embarque = fields.Char(string="Nombre Puerto Embarque", copy=False, size=40)
    total_fob = fields.Monetary(string="Total FOB", currency_field='currency_id')
    seguro = fields.Monetary(string="Seguro", currency_field='currency_id')
    flete = fields.Monetary(string="Flete", currency_field='currency_id')
    total_cif = fields.Monetary(string="Total CIF", currency_field='currency_id')
    regimen_aduanero = fields.Char(string="Regimen Aduanero", copy=False, size=35)
    nombre_puerto_salida = fields.Char(string="Nombre Puerto Salida", copy=False, size=40)
    nombre_puerto_desembarque = fields.Char(string="Nombre Puerto Desembarque", copy=False, size=40)
    peso_bruto = fields.Float('Peso Bruto', copy=False)
    peso_neto = fields.Float('Peso Neto', copy=False)
    unidad_peso_bruto = fields.Many2one(comodel_name='uom.uom', string='Unidad peso bruto', copy=False)
    unidad_peso_neto = fields.Many2one(comodel_name='uom.uom', string='Unidad peso neto', copy=False)
    cantidad_bulto = fields.Float('Cantidad Bulto', copy=False)
    unidad_bulto = fields.Many2one(comodel_name='uom.uom', string='Unidad bulto', copy=False)
    volumen_bulto = fields.Float('Volumen bulto', copy=False)
    unidad_volumen = fields.Many2one(comodel_name='uom.uom', string='Unidad volumen', copy=False)
    #CAMPOS EXTRAS DGII ECF TRANSPORTE#####
    via_transporte = fields.Selection([('01', '01 - Terrestre'),
                                       ('02', '02 - Marítimo'),
                                       ('03', '03 - Aérea')],
                                        copy=False)
    pais_origen = fields.Char(string="País origen", copy=False, size=60)
    direccion_destino = fields.Char(string="Dirección destino", copy=False, size=100)
    pais_destino = fields.Char(string="País destino", copy=False, size=60)
    numero_albaran = fields.Char(string="Número albarán", copy=False, size=20)
    l10n_do_ecf_modification_code =  fields.Selection(selection=lambda self: self.env["account.move"]._get_l10n_do_ecf_modification_code(),
                                                      string="Código Motivo Nota Credito",
                                                      copy=False,default='3') #fields.Char(string="Codigo Modificacio") # Este campo existe en el ECF indexa 5/5/2025 Pedro Nunez
    ecf_modification_reason  = fields.Char(string='Razon Nota Crédito')
    purchase_order_ref = fields.Char(string='Orden Compra Ref') #05/05/2025 se usa el campo REF y se cambia por este NumeroOrdenCompra
    indicador_monto_grabado  = fields.Char(string='Indicado Monto Grabado',default='0',compute="_compute_indicador_monto_grabado",store=True)
    ecf_monto_gravado_total = fields.Float(string="Monto Grabado Total",default = 0,copy=False)
    ecf_monto_gravadoI1 = fields.Float(string="Monto Grabado 1",default = 0,copy=False)
    ecf_monto_gravadoI2 = fields.Float(string="Monto Grabado 2",default = 0,copy=False)
    ecf_monto_gravadoI3 = fields.Float(string="Monto Grabado 3",default = 0,copy=False)
    ecf_monto_exento  = fields.Float(string="Monto Exento",default = 0,copy=False)
    ecf_total_ITBIS1  = fields.Float(string="Total ITBIS1",default = 0,copy=False)
    ecf_total_ITBIS2 = fields.Float(string="Total ITBIS2",default = 0,copy=False)
    ecf_monto_total = fields.Float(string="Monto Total",default = 0,copy=False)
    ecf_monto_periodo = fields.Float(string="Monto Periodo",default = 0,copy=False)
    ecf_valor_pagar  = fields.Float(string="Valor Pagar",default = 0,copy=False)
    ecf_monto_gravadoI2_currency = fields.Float(string="Monto Grabado 2 Moneda",default = 0,copy=False)
    ecf_monto_gravadoI3_currency = fields.Float(string="Monto Grabado 3 Monedas",default = 0,copy=False)
    ecf_monto_gravado_total_currency  = fields.Float(string="Monto Grabado Total Moneda",default = 0,copy=False)
    ecf_payment_reference  = fields.Char(string="Ecf Pedido",default = "0",copy=False)

    
    @api.depends("fiscal_type_id")   
    def _compute_is_ecf_invoice(self): #set_l10n_do_sequence_prefix(self):
        for reg in self:
            if reg.l10n_do_sequence_prefix and reg.l10n_do_sequence_prefix.startswith('E34') and reg.move_type == 'in_refund':
                reg.is_ecf_invoice = False
            
            if reg.l10n_do_sequence_prefix and reg.l10n_do_sequence_prefix.startswith('E31') and reg.move_type == 'in_invoice':
                reg.is_ecf_invoice = False

            if reg.l10n_do_sequence_prefix and reg.l10n_do_sequence_prefix.startswith('E'):           
                reg.is_ecf_invoice = True
            else:
                reg.is_ecf_invoice = False
    
    """
    @api.depends("fiscal_type_id","partner_id","l10n_do_sequence_prefix")
    def _compute_split_sequence(self):
        for reg in self:
            #reg.l10n_do_sequence_prefix.startswith('E') # = reg.ref[:3]
            if reg.l10n_do_sequence_prefix and reg.l10n_do_sequence_prefix.startswith('E'):
                reg.is_ecf_invoice = True
            else:
                reg.is_ecf_invoice = False   
    """
    def _validate_tax_before_post(self):
        for move in self:
            if not move.l10n_do_sequence_prefix:
                break
                
            if move.move_type in ('out_invoice', 'in_invoice','out_refund') and move.l10n_do_sequence_prefix.startswith('E'):
                for line in move.invoice_line_ids:
                    if line.display_type not in ('line_section', 'line_note'):
                        if not line.tax_ids:
                            raise ValidationError(_("Todas las líneas de factura deben tener al menos un impuesto asignado."))

    def _post(self, soft=True):
        self._validate_tax_before_post()
        res = super()._post(soft)
        ##self.ecf(self)

        for move in self:
            if move.is_ecf_invoice:
                move.ecf(move)

            if move.l10n_do_ecf_status != '5' and move.is_ecf_invoice:
                move._envio_dgii(move)

            if move.l10n_do_ecf_status == '3' and move.is_ecf_invoice:
                #move.boton_firmar()
                move._envio_dgii(move)

        return res

    @api.model
    def action_manual(self):
        #Se regenera el XML y Firma desde la accion de windows
        active_ids = self._context.get("active_ids")
        inv = self.browse(active_ids)
        self.ecf(inv)

    def boton_firmar(self):
        # if self.l10n_do_ecf_edi_file == False:
        #if self.l10n_do_ecf_status != '3':
        #    self.ecf(self)
                
        #self._envio_dgii(self)
        for inv in self:

            # 1️⃣ Firmar si no existe XML firmado
            if not inv.l10n_do_ecf_edi_file or not inv.l10n_do_ecf_security_code or inv.l10n_do_ecf_status == '5':
                if inv.l10n_do_ecf_status == '5':
                    inv.l10n_do_ecf_security_code = False
                    inv.l10n_do_ecf_edi_file = False
                    inv.l10n_do_ecf_edi_file_name = False
                
                inv.ecf(inv)

            # -------------------------------------------------------
            # 2️⃣ SI NO HAY TRACKID → ENVIAR SIEMPRE
            # -------------------------------------------------------
            if not inv.l10n_do_ecf_trackid:
                # limpiar estado 3 basura
                inv.l10n_do_ecf_status = None
                inv._envio_dgii(inv)
                return

            # -------------------------------------------------------
            # 3️⃣ Si HAY trackid → consultar estado y re-enviar si DGII no responde
            # -------------------------------------------------------
            if inv.l10n_do_ecf_status == '3':
                inv._envio_dgii(inv)
                return

            # 4️⃣ Si ya está aceptado → no hacer nada
            if inv.l10n_do_ecf_status in ('1', '4'):
                inv.message_post(body="El e-CF ya está aceptado por DGII.")
                return

            # 5️⃣ En cualquier otro error → reintentar envío
            inv._envio_dgii(inv)
    def boton_validar_xml(self):
        self._validate_xml(self)

    def boton_acecf(self):
        #Aprobacion comercial de las facturas de compras registradas
        self.acecf(self)

    def boton_enviar_cliente(self):
        for inv in self:
            if inv.l10n_do_ecf_status not in ('1', '4'):
                continue
            if inv.l10n_do_sequence_prefix == 'E32':
                continue
            if not inv.l10n_do_ecf_ambiente:
                inv.l10n_do_ecf_ambiente = inv.company_id.l10n_do_ecf_ambiente

            sign = XMLSignature(inv.company_id.cert, inv.company_id.cert_password, inv.l10n_do_ecf_ambiente)
            if not sign._check_internet_connection():
                inv.message_post(
                    body="Sin conexión a internet. Pendiente de envío al receptor.",
                    subtype_xmlid='mail.mt_note',
                )
                continue

            token_data = sign._get_token_semilla()
            if not token_data or 'token' not in token_data:
                inv.message_post(
                    body="DGII no respondió token. Reintentar envío al receptor.",
                    subtype_xmlid='mail.mt_note',
                )
                continue

            token = token_data['token']
            xml_payload = (
                base64.b64decode(inv.l10n_do_fc_edi_file)
                if inv.l10n_do_fc_edi_file
                else base64.b64decode(inv.l10n_do_ecf_edi_file)
            )
            self._envio_receptor(inv, sign, token, xml_payload)

    def ecf(self, inv):
        #No fiscal no hace nada

        for rec in inv:
            if rec.is_ecf_invoice == False or rec.ref == False:
                print('no esta generando la factura electornica')

                return

        #Certificado cargado y su clave
        if inv.company_id.cert == False or inv.company_id.cert_password == False:
            inv.l10n_do_ecf_xml_validation = 'Certificado erroneo'
            inv.l10n_do_ecf_status = '5'
            return

        #Certificado cargado y su clave

        if inv.company_id.vat not in ecf_rnc:
            ecf_rnc.append(inv.company_id.vat) # ecf_rnc:
            #inv.l10n_do_ecf_xml_validation = 'Compañía inactiva'
            #inv.l10n_do_ecf_status = '5'
            #return

        #Control de fecha de expiracion
        if datetime.now() > ecf_expiracion:
            inv.l10n_do_ecf_xml_validation = 'Licencia expirada'
            inv.l10n_do_ecf_status = '5'
            return

        if inv.l10n_do_ecf_ambiente == False:
            inv.l10n_do_ecf_ambiente = inv.company_id.l10n_do_ecf_ambiente

        if inv.l10n_do_ecf_edi_file and inv.l10n_do_ecf_security_code:
            inv.l10n_do_ecf_xml_validation = "XML previamente firmado reutilizado."
            inv.l10n_do_ecf_status = None

            # Si es E32 < 250k y falta RFCE → generarlo
            if inv.l10n_do_sequence_prefix == 'E32' and inv.amount_total < 250000:
                if not inv.l10n_do_fc_edi_file:
                    xml_rfce = self.xml_rfce(inv, inv.l10n_do_ecf_security_code)
                    _xml_rfce, _, _ = XMLSignature(
                        inv.company_id.cert,
                        inv.company_id.cert_password,
                        inv.l10n_do_ecf_ambiente
                    )._sign_xml(xml_rfce)
                    inv.l10n_do_fc_edi_file = base64.b64encode(_xml_rfce)

            return

        #1.-Cargamos el certificado para la firma y obtenemos el token de la semilla
        sign = XMLSignature(inv.company_id.cert, inv.company_id.cert_password, inv.l10n_do_ecf_ambiente)
        inv.l10n_do_ecf_status = None
        #2.- Generar y firmar del xml, si ya tiene codigo de seguridad es que ya esta firmado
        xml_ecf = self.xml_ecf(inv)
        inv.l10n_do_ecf_edi_file_name = inv.company_id.vat + inv.ref + '.xml' #Nombre Archivo
        _xml_ecf, CodigoSeguridad, FechaHoraFirma = sign._sign_xml(xml_ecf) #Firma
        inv.l10n_do_ecf_edi_file = base64.b64encode(_xml_ecf)
        inv.l10n_do_ecf_security_code = CodigoSeguridad
        if hasattr(FechaHoraFirma, "tzinfo") and FechaHoraFirma.tzinfo is not None:
            FechaHoraFirma = FechaHoraFirma.replace(tzinfo=None)
        inv.l10n_do_ecf_sign_date = FechaHoraFirma
        inv.l10n_do_ecf_trackid = None
        inv.l10n_do_fc_edi_file = None

        #3.-Para los eNCF de Consumo menor a 250k solo se envia el resumen
        if inv.l10n_do_sequence_prefix == 'E32' and inv.amount_total < 250000:
            xml_rfce = self.xml_rfce(inv, CodigoSeguridad)
            print('xml rfce', xml_rfce)
            print('fechay hora', FechaHoraFirma)
            _xml_rfce, CodigoSeguridad, FechaHoraFirma = sign._sign_xml(xml_rfce)
            inv.l10n_do_fc_edi_file = base64.b64encode(_xml_rfce) if CodigoSeguridad else None

        if inv.l10n_do_ecf_status == False:
            inv.l10n_do_ecf_xml_validation = None
            self._validate_xml(inv)

    def _validate_xml(self, inv):
        """Validamos el formato y valores requeridos del XML por medio los schema de la DGII
        """
        TipoeCF = inv.l10n_do_sequence_prefix[1:3]
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)))
        path = path.replace('models','schema/')
        path = path.replace('//dist','/')
        archivo = f'e-CF {TipoeCF} v.1.0.xsd'
        ruta = path + archivo
        try:
            schema_file = open(ruta)
            schema = xmlschema.XMLSchema(schema_file)
            xml = base64.b64decode(inv.l10n_do_ecf_edi_file)
            valido = schema.is_valid(xml)
            schema.validate(xml)

            #Revisamos el xml del resumen de consumo
            if inv.l10n_do_fc_edi_file:
                archivo = 'RFCE 32 v.1.0.xsd'
                ruta = path + archivo
                schema_file = open(ruta)
                schema = xmlschema.XMLSchema(schema_file)
                xml = base64.b64decode(inv.l10n_do_fc_edi_file)
                valido = schema.is_valid(xml)
                schema.validate(xml)

            inv.l10n_do_ecf_xml_validation = 'XML firmado Correctamente'
            inv.l10n_do_ecf_status = None
        except Exception as e:
            inv.l10n_do_ecf_xml_validation = e
            inv.l10n_do_ecf_status = '5'

    def _envio_dgii(self, inv):
        """
        Envio de xml firmado a la DGII para su aprobacion
        # ESTADO DE VALIDACION DE ENVIO (l10n_do_ecf_status)
        # 0 - No encontrado
        # 1 - Aceptado
        # 2 - Rechazado
        # 3 - En Proceso
        # 4 - Aceptado Condicional
        # 5 - Error interno ODOO (Para las validaciones internas)
        """
        # #Certificado cargado y su clave
        # if inv.company_id.vat not in ecf_rnc:
        #     inv.l10n_do_ecf_xml_validation = 'Compañía inactiva'
        #     inv.l10n_do_ecf_status = '5'
        #     return

        # #Control de fecha de expiracion
        # if datetime.now() > ecf_expiracion:
        #     inv.l10n_do_ecf_xml_validation = 'Licencia expirada'
        #     inv.l10n_do_ecf_status = '5'
        #     return

        if inv.l10n_do_ecf_ambiente == False:
            inv.l10n_do_ecf_ambiente = inv.company_id.l10n_do_ecf_ambiente

        sign = XMLSignature(inv.company_id.cert, inv.company_id.cert_password, inv.l10n_do_ecf_ambiente)

        if not sign._check_internet_connection():
            inv.l10n_do_ecf_status = '3'  # En proceso
            inv.l10n_do_ecf_response = 'Sin conexión a internet. Pendiente de envío a DGII.'
            return

        token_data = sign._get_token_semilla()
        if not token_data or 'token' not in token_data:
            inv.l10n_do_ecf_status = '3'
            inv.l10n_do_ecf_response = 'DGII no respondió token. Reintentar.'
            return

        token = token_data['token']
        #token = sign._get_token_semilla()['token']
        _xml = base64.b64decode(inv.l10n_do_fc_edi_file) if inv.l10n_do_fc_edi_file else base64.b64decode(inv.l10n_do_ecf_edi_file)
        if inv.l10n_do_ecf_status != '3':
            resp_json = None
            if inv.l10n_do_ecf_status != '5':
                resp_json, Response = sign._validate_ecf(_xml, inv.l10n_do_ecf_edi_file_name, token)
                inv.l10n_do_ecf_response = Response.replace(",", " ")
            if resp_json:
                inv.l10n_do_ecf_status = str(resp_json.get('codigo')) if resp_json.get('codigo') else None
                inv.l10n_do_ecf_trackid = resp_json.get('trackId') if resp_json.get('trackId') else None
            else:
                # inv.l10n_do_ecf_status = None
                inv.l10n_do_ecf_trackid = None

        #Revisar el estado del envio
        if inv.l10n_do_ecf_trackid:
            #NOTA el campo SecuenciaUtilizada = False se podra reutilizar el NCF
            Response, codigo = sign._resultado_ecf(inv.l10n_do_ecf_trackid, token)
            Response = Response.replace(",", "\n").replace(" ", "\n")
            inv.l10n_do_ecf_response = Response
            inv.l10n_do_ecf_status = codigo

        #6.-Enviarmos el xml firmado al receptor aceptados por DGII
        if inv.l10n_do_ecf_status in ('1', '4') and inv.l10n_do_sequence_prefix != 'E32':
            self._envio_receptor(inv, sign, token, _xml)

    def _envio_receptor(self, inv, sign, token, xml_payload):
         #Si es emisor electronico aqui se busca el URL para el envio al receptor
        resp_json = sign._directorios_url(token, inv.partner_id.vat)
        if isinstance(resp_json, list) and len(resp_json) > 0:
            urlRecepcion = resp_json[0].get('urlRecepcion')
            urlAceptacion = resp_json[0].get('urlAceptacion')
        elif isinstance(resp_json, dict):
            urlRecepcion = resp_json.get('urlRecepcion')
            urlAceptacion = resp_json.get('urlAceptacion')
        else:
            urlRecepcion = urlAceptacion = None

        if not urlRecepcion:
            inv.message_post(
                body="Error enviando eCF al receptor: No hay URL de recepción en el directorio de la DGII para este RNC: %s." % (inv.partner_id.vat or "N/A"),
                subtype_xmlid='mail.mt_note',
            )
            return False

        Response = sign._envio_comprador(xml_payload, inv.l10n_do_ecf_edi_file_name, token, urlRecepcion)

        if hasattr(Response, "status_code") and Response.status_code == 200:
            response_content = getattr(Response, "content", None)
            if not response_content:
                response_text = getattr(Response, "text", "") or ""
                response_content = response_text.encode("utf-8") if isinstance(response_text, str) else response_text
            attachments = []
            if response_content and response_content.strip():
                base_name = inv.l10n_do_ecf_edi_file_name or "document.xml"
                filename = "ARECF_%s" % base_name
                if not filename.lower().endswith(".xml"):
                    filename = "%s.xml" % filename
                attachments = [(filename, response_content)]
            inv.message_post(
                body=(
                    "eCF enviado al Receptor correctamente. "
                    "URL de recepción: %s (/fe/recepcion/api/ecf)"
                ) % (urlRecepcion),
                attachments=attachments,
                subtype_xmlid='mail.mt_note'  # This makes it an internal "Log Note"
            )
            return True

        if isinstance(Response, str):
            error_text = Response or "N/A"
        else:
            error_text = getattr(Response, "text", "") or "N/A"
            
        url_recepcion_full = "%s (/fe/recepcion/api/ecf)" % urlRecepcion.rstrip("/")
        _logger.error(
            "Error enviando eCF al receptor: %s URL recepcion: %s",
            error_text,
            url_recepcion_full,
        )

        billing_group = self.env.ref('account.group_account_manager', raise_if_not_found=False)
        """
        partner_ids = billing_group.users.mapped('partner_id').ids if billing_group else []
        error_text = (
            "Error enviando eCF al receptor: %s - URL de recepcion: %s"
            % (error_text, url_recepcion_full)
        )
        inv.message_post(
            body=error_text,
            subtype_xmlid='mail.mt_note',
            partner_ids=partner_ids,
        )
        """
        
        return False



    def xml_ecf(self, reg):
        reg.l10n_do_ecf_response = None
        reg.l10n_do_ecf_status = None
        #ECF
        ecf = ET.Element('ECF')

        #ECF/ENCABEZADO
        encabezado = ET.SubElement(ecf, 'Encabezado')
        ET.SubElement(encabezado, 'Version').text = '1.0'

        #ECF/ENCABEZADO/IDDOC 
        encabezado.insert(1, self.xml_ecf_iddoc(reg))

        #ECF/ENCABEZADO/EMISOR
        encabezado.insert(2, self.xml_ecf_emisor(reg))

        #ECF/ENCABEZADO/COMPRADOR
        if reg.l10n_do_sequence_prefix != 'E43':
            encabezado.insert(3, self.xml_ecf_comprador(reg))

        ##ECF/ENCABEZADO/INFORMACIONESADICIONALES
        encabezado.insert(4, self.xml_ecf_adicional(reg))

        ##ECF/ENCABEZADO/TRANSPORTE
        encabezado.insert(5, self.xml_ecf_transporte(reg))

        #ECF/ENCABEZADO/TOTALES
        xml_totales, otra_moneda = self.xml_ecf_totales(reg)
        encabezado.insert(6, xml_totales)

        #ECF/ENCABEZADO/OTRAMONEDA
        if reg.currency_id.id != reg.company_id.currency_id.id:
            encabezado.insert(7, otra_moneda)

        #ECF/DETALLESITEMS
        ecf.insert(2, self.xml_ecf_detallesitems(reg))

        #ECF/DESCUENTOSORECARGOS
        descuentosrecargos = self.xml_ecf_descuentos(reg)
        if isinstance(descuentosrecargos, ET.Element) and len(descuentosrecargos):
            ecf.insert(3, descuentosrecargos)

        #ECF/SUBTOTALES
        if reg.l10n_do_sequence_prefix in ('E47'): #CERTIFICACION (OPCIONAL)
            ecf.insert(4, self.xml_ecf_subtotales(reg))

        #ECF/INFORMACIONREFERENCIA
        if reg.l10n_do_sequence_prefix in ('E33','E34'): #NOTA CREDITO / DEBITO
            ecf.insert(5, self.xml_ecf_referencia(reg))   

        #Borrar todos los elementos vacios
        for x in range(10):
            for element in ecf.findall('.//'):
                for subelement in element:
                    if subelement.__len__() == 0 and subelement.text in (False, None, ''):
                        element.remove(subelement)

        #sino hay impuestos no debe tener el indicadormontogravado
        IndicadorMontoGravado = False
        if encabezado.find('.//ITBIS1') != None:
            IndicadorMontoGravado = True
        if encabezado.find('.//ITBIS2') != None:
            IndicadorMontoGravado = True
        if IndicadorMontoGravado == False:
            IdDoc = encabezado.find('.//IdDoc')
            IdDoc.remove(IdDoc.find('IndicadorMontoGravado'))

        xml = ET.tostring(ecf)
        return (xml)
    
    def xml_ecf_subtotales(self, reg):
        tasa = 1 / reg.invoice_line_ids[0].currency_rate
        totales = reg._get_l10n_do_amounts()   #heredado -> l10n_do_accounting
        MontoExento = totales['exempt_amount']
        TotalISRRetencion = totales['isr_withholding_amount'] # 12-05-2025 para obtener el ISR retenido
        MontoTotal = reg.amount_total

        #Esta Restando la rentecion en los pagas el extrenjero 12-05-2025
        if reg.l10n_do_sequence_prefix == 'E47':
            MontoTotal += TotalISRRetencion
        Subtotales = ET.Element('Subtotales')
        Subtotal = ET.SubElement(Subtotales, 'Subtotal')
        ET.SubElement(Subtotal, 'NumeroSubTotal').text = '1'
        ET.SubElement(Subtotal, 'DescripcionSubtotal').text = 'N/A'
        ET.SubElement(Subtotal, 'Orden').text = '1'
        ET.SubElement(Subtotal, 'SubTotalExento').text = self.format_valores(MontoExento * tasa) 
        ET.SubElement(Subtotal, 'MontoSubTotal').text = self.format_valores(MontoTotal  * tasa) 
        ET.SubElement(Subtotal, 'Lineas').text = '1'
        return Subtotales
    
    def xml_ecf_transporte(self, reg):
        Transporte = ET.Element('Transporte')
        ET.SubElement(Transporte, 'ViaTransporte').text = reg.via_transporte
        ET.SubElement(Transporte, 'PaisOrigen').text = reg.pais_origen
        ET.SubElement(Transporte, 'DireccionDestino').text = reg.direccion_destino
        ET.SubElement(Transporte, 'PaisDestino').text = reg.pais_destino
        ET.SubElement(Transporte, 'NumeroAlbaran').text = reg.numero_albaran
        return Transporte
    
    def xml_ecf_referencia(self, reg):
        ecf_origin = self.search([('ref','=', reg.origin_out), ('move_type', '=', 'out_invoice')])
        informacionreferencia = ET.Element('InformacionReferencia')
        ET.SubElement(informacionreferencia, 'NCFModificado').text = reg.origin_out
        ET.SubElement(informacionreferencia, 'FechaNCFModificado').text = self.format_valores(ecf_origin[0].invoice_date)
        ET.SubElement(informacionreferencia, 'CodigoModificacion').text = reg.l10n_do_ecf_modification_code if reg.l10n_do_ecf_modification_code else '3'
        ET.SubElement(informacionreferencia, 'RazonModificacion').text = reg.ecf_modification_reason #str(reg.narration).replace('<p>','').replace('<br>','').replace('</p>','') if reg.narration else None
        return informacionreferencia

    def xml_ecf_adicional(self, reg):
        InformacionesAdicionales = ET.Element('InformacionesAdicionales')
        ET.SubElement(InformacionesAdicionales, 'FechaEmbarque').text = self.format_valores(reg.fecha_embarque)
        ET.SubElement(InformacionesAdicionales, 'NumeroEmbarque').text = reg.numero_embarque
        ET.SubElement(InformacionesAdicionales, 'NumeroContenedor').text = reg.numero_contenedor
        ET.SubElement(InformacionesAdicionales, 'NumeroReferencia').text = reg.numero_referencia
        ET.SubElement(InformacionesAdicionales, 'NombrePuertoEmbarque').text = reg.nombre_puerto_embarque
        ET.SubElement(InformacionesAdicionales, 'CondicionesEntrega').text = reg.invoice_incoterm_id.code
        ET.SubElement(InformacionesAdicionales, 'TotalFob').text = self.format_valores(reg.total_fob)
        ET.SubElement(InformacionesAdicionales, 'Seguro').text = self.format_valores(reg.seguro)
        ET.SubElement(InformacionesAdicionales, 'Flete').text = self.format_valores(reg.flete)
        ET.SubElement(InformacionesAdicionales, 'TotalCif').text = self.format_valores(reg.total_cif)
        ET.SubElement(InformacionesAdicionales, 'RegimenAduanero').text = reg.regimen_aduanero
        ET.SubElement(InformacionesAdicionales, 'NombrePuertoSalida').text = reg.nombre_puerto_salida
        ET.SubElement(InformacionesAdicionales, 'NombrePuertoDesembarque').text = reg.nombre_puerto_desembarque
        ET.SubElement(InformacionesAdicionales, 'PesoBruto').text = self.format_valores(reg.peso_bruto)
        ET.SubElement(InformacionesAdicionales, 'PesoNeto').text = self.format_valores(reg.peso_neto)
        ET.SubElement(InformacionesAdicionales, 'UnidadPesoBruto').text = reg.unidad_peso_bruto.name.split('-')[0] if reg.unidad_peso_bruto.name else None
        ET.SubElement(InformacionesAdicionales, 'UnidadPesoNeto').text = reg.unidad_peso_neto.name.split('-')[0] if reg.unidad_peso_neto.name else None
        ET.SubElement(InformacionesAdicionales, 'CantidadBulto').text = self.format_valores(reg.cantidad_bulto)
        ET.SubElement(InformacionesAdicionales, 'UnidadBulto').text = reg.unidad_bulto.name.split('-')[0] if reg.unidad_bulto.name else None
        ET.SubElement(InformacionesAdicionales, 'VolumenBulto').text = "{0:.0f}".format(reg.volumen_bulto) if reg.volumen_bulto else None
        ET.SubElement(InformacionesAdicionales, 'UnidadVolumen').text = reg.unidad_volumen.name.split('-')[0] if reg.unidad_volumen.name else None
        return InformacionesAdicionales

    def xml_ecf_iddoc(self, reg):
        iddoc =  ET.Element('IdDoc')
        ET.SubElement(iddoc, 'TipoeCF').text = reg.l10n_do_sequence_prefix[1:3]
        ET.SubElement(iddoc, 'eNCF').text = reg.ref
        ET.SubElement(iddoc, 'FechaVencimientoSecuencia').text = self.format_valores(reg.ncf_expiration_date) if reg.l10n_do_sequence_prefix not in ('E32','E34') else None
        if reg.l10n_do_sequence_prefix == 'E34': #Nota de Credito
            ecf_origin = self.search([('ref','=', reg.origin_out), ('move_type', '=', 'out_invoice')])
            dias_nc = (reg.invoice_date - ecf_origin[0].invoice_date).days
            dias = '0' if dias_nc <= 30 else '1'
            ET.SubElement(iddoc, 'IndicadorNotaCredito').text = dias
        ET.SubElement(iddoc, 'IndicadorMontoGravado').text = reg.indicador_monto_grabado 
        ET.SubElement(iddoc, 'TipoIngresos').text = reg.income_type if reg.l10n_do_sequence_prefix not in ('E41','E43','E47') else None
        if reg.l10n_do_sequence_prefix not in ('E43', 'E47'):
            TipoPago = '2'
            if reg.invoice_payment_term_id:
                TipoPago = '1' if 'contado' in reg.invoice_payment_term_id.name else '2'
            ET.SubElement(iddoc, 'TipoPago').text = TipoPago
            if TipoPago == '2':
                ET.SubElement(iddoc, 'FechaLimitePago').text = self.format_valores(reg.invoice_date_due)
                ET.SubElement(iddoc, 'TerminoPago').text = None #str(reg.narration).replace('<p>','').replace('<br>','').replace('</p>','') if reg.narration else None
        if reg.invoice_payments_widget and reg.move_type in ('out_invoice'):
            TablaFormasPago, BancoCuenta = self.xml_ecf_formaspago(reg)
            iddoc.append(TablaFormasPago)
            ET.SubElement(iddoc, 'TipoCuentaPago').text = BancoCuenta['TipoCuentaPago'] if BancoCuenta else None 
            ET.SubElement(iddoc, 'NumeroCuentaPago').text = BancoCuenta['NumeroCuentaPago'] if BancoCuenta else None
            ET.SubElement(iddoc, 'BancoPago').text = BancoCuenta['BancoPago'] if BancoCuenta else None
        if reg.partner_bank_id and reg.move_type in ('in_invoice'):
            ET.SubElement(iddoc, 'NumeroCuentaPago').text = reg.partner_bank_id.acc_number
            ET.SubElement(iddoc, 'BancoPago').text = reg.partner_bank_id.bank_id.name
        return iddoc

    def xml_ecf_formaspago(self, reg):
        FormaPagoDist = {
            'cash': '1',
            'bank': '2',
            'card': '3',
            'credit': '4',
            'bond': '5',
            'swarp': '6',
            'others': '8'
        }
        BancoCuenta = None
        payments = reg.invoice_payments_widget['content']
        TablaFormasPago =  ET.Element('TablaFormasPago')
        for payment in payments:
            payment_id = self.env['account.payment'].browse(payment['account_payment_id'])
            FormaDePago =  ET.SubElement(TablaFormasPago, 'FormaDePago')
            ET.SubElement(FormaDePago, 'FormaPago').text = FormaPagoDist.get(payment_id.journal_id.l10n_do_payment_form)
            ET.SubElement(FormaDePago, 'MontoPago').text = self.format_valores(payment['amount'])

            if payment_id.journal_id.bank_id:
                BancoCuenta = {
                    'TipoCuentaPago': payment_id.journal_id.bank_id.bic,
                    'NumeroCuentaPago': payment_id.journal_id.bank_acc_number,
                    'BancoPago': payment_id.journal_id.bank_id.name
                }
        return TablaFormasPago, BancoCuenta

    def xml_ecf_emisor(self, reg):
        emisor =  ET.Element('Emisor')
        ET.SubElement(emisor, 'RNCEmisor').text =reg.company_id.vat
        ET.SubElement(emisor, 'RazonSocialEmisor').text = reg.company_id.name
        ET.SubElement(emisor, 'NombreComercial').text = reg.company_id.name
        ET.SubElement(emisor, 'Sucursal').text = None
        ET.SubElement(emisor, 'DireccionEmisor').text = reg.company_id.street if reg.company_id.street else 'N/A'
        ET.SubElement(emisor, 'Municipio').text = None #reg.company_id.city
        ET.SubElement(emisor, 'Provincia').text = None #reg.company_id.zip
        if reg.company_id.phone:# or reg.company_id.mobile:
            TablaTelefonoEmisor = ET.SubElement(emisor, 'TablaTelefonoEmisor')
            ET.SubElement(TablaTelefonoEmisor, 'TelefonoEmisor').text = reg.company_id.phone
            #ET.SubElement(TablaTelefonoEmisor, 'TelefonoEmisor').text = reg.company_id.mobile
        ET.SubElement(emisor, 'CorreoEmisor').text = reg.company_id.email
        ET.SubElement(emisor, 'WebSite').text = reg.company_id.website.replace('http://','') if reg.company_id.website else None
        ET.SubElement(emisor, 'CodigoVendedor').text = reg.user_id.ref if reg.move_type in ('out_invoice','out_refund') else None
        ET.SubElement(emisor, 'NumeroFacturaInterna').text = reg.ecf_payment_reference # 12-05-2025 evitar errores
        ET.SubElement(emisor, 'NumeroPedidoInterno').text = reg.ecf_payment_reference # 12-5-2025 evitar errores
        try:
            ET.SubElement(emisor, 'ZonaVenta').text = reg.partner_id.team_id.name if reg.move_type in ('out_invoice','out_refund') else None
        except:
            None
        ET.SubElement(emisor, 'FechaEmision').text = self.format_valores(reg.invoice_date)
        
        #Borramos los elementos vacios
        for element in emisor.findall('.//'):
            if element.__len__() == 0 and element.text in (False, None, ''):
                try:
                    emisor.remove(element)
                except:
                    pass

        return emisor
    
    def xml_ecf_comprador(self, reg):
        comprador =  ET.Element('Comprador')       
        if reg.l10n_do_sequence_prefix != 'E47':
            ET.SubElement(comprador, 'RNCComprador').text = self._clean_rnc(reg.partner_id.vat) 
        else:
            ET.SubElement(comprador, 'IdentificadorExtranjero').text = reg.partner_id.vat
        ET.SubElement(comprador, 'RazonSocialComprador').text = reg.partner_id.parent__name if reg.partner_id.parent_name else reg.partner_id.name
        if reg.move_type == 'in_invoice':
            return comprador
        ET.SubElement(comprador, 'ContactoComprador').text = reg.partner_id.ecf_contact_name
        ET.SubElement(comprador, 'CorreoComprador').text =  None #rreg.partner_id.email
        ET.SubElement(comprador, 'DireccionComprador').text = reg.partner_id.street[:100] if reg.partner_id.street else None
        ET.SubElement(comprador, 'MunicipioComprador').text = None #reg.partner_id.city 
        ET.SubElement(comprador, 'ProvinciaComprador').text = None #reg.partner_id.zip
        ET.SubElement(comprador, 'FechaEntrega').text = self.format_valores(reg.fecha_entrega) 
        if reg.partner_shipping_id != reg.partner_id:
            ET.SubElement(comprador, 'ContactoEntrega').text = reg.partner_shipping_id.name[:100] if reg.partner_shipping_id.name else None
            ET.SubElement(comprador, 'DireccionEntrega').text = reg.partner_shipping_id.street[:100] if reg.partner_shipping_id.street else None
            ET.SubElement(comprador, 'TelefonoAdicional').text =  None #reg.partner_shipping_id.phone.replace('+1 ', '')
        ET.SubElement(comprador, 'FechaOrdenCompra').text = self.format_valores(reg.fecha_orden_compra) 
        if reg.purchase_order_ref:
            ET.SubElement(comprador, 'NumeroOrdenCompra').text = reg.purchase_order_ref if reg.purchase_order_ref.isnumeric() else None
        ET.SubElement(comprador, 'CodigoInternoComprador').text = reg.partner_id.ref 
        return comprador
    
    def xml_ecf_detallesitems(self, reg):
        detallesitems = ET.Element('DetallesItems')
        numero_linea = 0
        for reg_lin in reg.invoice_line_ids.filtered(lambda lin: lin.price_unit >= 0 and lin.quantity > 0):
            MontoITBISRetenido = 0
            MontoISRRetenido = 0
            numero_linea += 1
            tasa = 1 / reg_lin.currency_rate

            #IMPUESTOS
            indicador_facturacion = '4' #0:No facturable, 1:ITBIS 18%, 2:ITBIS 16%, 3:ITBIS 0%, 4:EXENTO
            TablaImpuestoAdicional = ET.Element('TablaImpuestoAdicional')
            for tax in reg_lin.tax_ids:
                if 'ITBIS1' in tax.tax_group_id.name:
                    indicador_facturacion = '1'
                if 'ITBIS2' in tax.tax_group_id.name:
                    indicador_facturacion = '2'
                if 'ITBIS3' in tax.tax_group_id.name:
                    indicador_facturacion = '3'
                if 'RITBIS' in tax.tax_group_id.name: #RETENCION ITBIS
                    MontoITBISRetenido += (reg_lin.price_subtotal * tax.amount / 100 * -1)
                if 'ISR' in tax.tax_group_id.name:    #RETENCION IMPUESTO SOBRO LA RENTA
                    MontoISRRetenido += (reg_lin.price_subtotal * tax.amount / 100 * -1)
                if '-ISC' in tax.tax_group_id.name:   #IMPUESTO ADICIONALES
                    ImpuestoAdicional = ET.SubElement(TablaImpuestoAdicional, 'ImpuestoAdicional')
                    ET.SubElement(ImpuestoAdicional, 'TipoImpuesto').text = tax.tax_group_id.name.split('-')[0]
            
            #RETENCIONES
            if MontoITBISRetenido or MontoISRRetenido:
                Retencion = ET.Element('Retencion')
                ET.SubElement(Retencion, 'IndicadorAgenteRetencionoPercepcion').text = '1'
                ET.SubElement(Retencion, 'MontoITBISRetenido').text =  self.format_valores(MontoITBISRetenido * tasa) if MontoITBISRetenido else None
                ET.SubElement(Retencion, 'MontoISRRetenido').text =  self.format_valores(MontoISRRetenido * tasa) if MontoISRRetenido else None

            #DESCUENTOS
            descuento = 0
            recargo = 0
            TablaSubDescuento = ET.Element('TablaSubDescuento')
            TablaSubRecargo = ET.Element('TablaSubRecargo')
            
            #DESCUENTO EN PORCENTAJE (misma lineas estandar)
            monto_bruto = reg_lin.price_unit * reg_lin.quantity
            monto_descuento = (monto_bruto * (reg_lin.discount  / 100))
            monto_neto_item = (monto_bruto - monto_descuento) * tasa         
            price_unit = 100.0 * abs(reg_lin.balance)                     
            descuento = abs(reg_lin.balance) - price_unit #ojo
            
            #ECF/DETALLESITEMS/ITEMS
            item = ET.SubElement(detallesitems, 'Item')
            ET.SubElement(item, 'NumeroLinea').text =  str(numero_linea)
            if reg_lin.product_id.default_code:
                TablaCodigosItem = ET.SubElement(item, 'TablaCodigosItem')
                CodigosItem = ET.SubElement(TablaCodigosItem, 'CodigosItem')
                ET.SubElement(CodigosItem, 'TipoCodigo').text = reg_lin.product_id.ecf_tipo_codigo #'INTERNA' en la Certificacion cambia a interno 7/05/2025
                ET.SubElement(CodigosItem, 'CodigoItem').text = reg_lin.product_id.default_code
            ET.SubElement(item, 'IndicadorFacturacion').text = indicador_facturacion #0:No facturable, 1:ITBIS 18%, 2:ITBIS 16%, 3:ITBIS 0%, 4:EXENTO
            ##hijo = item.append(Retencion) if MontoITBISRetenido or MontoISRRetenido else None
            if MontoITBISRetenido or MontoISRRetenido:
                Retencion = ET.SubElement(item, 'Retencion')
                ET.SubElement(Retencion, 'IndicadorAgenteRetencionoPercepcion').text = '1'
                if MontoITBISRetenido:
                    ET.SubElement(Retencion, 'MontoITBISRetenido').text = self.format_valores(MontoITBISRetenido * tasa)
                if MontoISRRetenido:
                    ET.SubElement(Retencion, 'MontoISRRetenido').text = self.format_valores(MontoISRRetenido * tasa)
            else:
                if reg.l10n_do_sequence_prefix == 'E47':
                    Retencion = ET.SubElement(item, 'Retencion')
                    ET.SubElement(Retencion, 'IndicadorAgenteRetencionoPercepcion').text = '1'
                    ET.SubElement(Retencion, 'MontoISRRetenido').text = '0.00'

            ET.SubElement(item, 'NombreItem').text = reg_lin.name[:80] if reg_lin.product_id.name == False else reg_lin.product_id.name[:80]
            ET.SubElement(item, 'IndicadorBienoServicio').text = '1' if reg_lin.product_id.type in ('product','consu') else '2' # 1:bien, 2:servicio
            ET.SubElement(item, 'DescripcionItem').text = reg_lin.product_id.description_sale
            ET.SubElement(item, 'CantidadItem').text = self.format_valores(reg_lin.quantity,reg_lin.ecf_quantity_precision) 
            if reg_lin.product_uom_id.ecf_code:
                ET.SubElement(item, 'UnidadMedida').text = reg_lin.product_uom_id.ecf_code 

            if reg_lin.fecha_elaboracion:
                ET.SubElement(item, 'FechaElaboracion').text = self.format_valores(reg_lin.fecha_elaboracion)
                        
            if reg_lin.fecha_vencimiento:
                ET.SubElement(item, 'FechaVencimientoItem').text = self.format_valores(reg_lin.fecha_vencimiento)
            
            # ET.SubElement(item, 'CantidadReferencia').text = self.format_valores(reg_lin.product_uom_id.factor_inv),
            # ET.SubElement(item, 'UnidadReferencia').text = reg_lin.product_uom_id.category_id.name.split('-')[0] if '-' in reg_lin.product_uom_id.category_id.name else None,
            # TablaSubcantidad = ET.SubElement(item, 'TablaSubcantidad')
            # SubcantidadItem = ET.SubElement(TablaSubcantidad, 'SubcantidadItem')
            # ET.SubElement(SubcantidadItem, 'Subcantidad').text = None
            # ET.SubElement(SubcantidadItem, 'CodigoSubcantidad').text = None
            # ET.SubElement(item, 'GradosAlcohol').text = '5.00', #TEMPORAL CERTIFICACION
            # ET.SubElement(item, 'PrecioUnitarioReferencia').text = self.format_valores(reg_lin.product_id.list_price),

            ET.SubElement(item, 'PrecioUnitarioItem').text = self.format_valores((reg_lin.price_unit * tasa),reg_lin.ecf_decimal_precision) 
            #if descuento > 0:
            #    ET.SubElement(item, 'DescuentoMonto').text = self.format_valores(descuento * tasa)
            #    item.append(TablaSubDescuento)
            if reg_lin.discount > 0:
                ET.SubElement(item, 'DescuentoMonto').text = self.format_valores(monto_descuento * tasa)
                TablaSubDescuento = ET.Element('TablaSubDescuento')
                SubDescuento = ET.SubElement(TablaSubDescuento, 'SubDescuento')
                ET.SubElement(SubDescuento, 'TipoSubDescuento').text = '%'
                ET.SubElement(SubDescuento, 'SubDescuentoPorcentaje').text = self.format_valores(reg_lin.discount)
                ET.SubElement(SubDescuento, 'MontoSubDescuento').text = self.format_valores(monto_descuento * tasa) 
                item.append(TablaSubDescuento)
            
            if recargo > 0:
                ET.SubElement(item, 'RecargoMonto').text = self.format_valores(recargo * tasa)
                item.append(TablaSubRecargo)
            for child in TablaImpuestoAdicional:
                item.append(TablaImpuestoAdicional)
                break
            if reg.currency_id.id != reg.company_id.currency_id.id:
                OtraMonedaDetalle = ET.SubElement(item, 'OtraMonedaDetalle')
                precio_unit_otra = (reg_lin.price_subtotal / reg_lin.quantity) if reg_lin.quantity else 0.0
                ET.SubElement(OtraMonedaDetalle, 'PrecioOtraMoneda').text = self.format_valores(precio_unit_otra,reg_lin.ecf_currency_precision)
                ET.SubElement(OtraMonedaDetalle, 'MontoItemOtraMoneda').text = self.format_valores(monto_bruto - monto_descuento) #reg_lin.price_subtotal) 
                #ET.SubElement(OtraMonedaDetalle, 'PrecioOtraMoneda').text = self.format_valores(new_price,reg_lin.ecf_currency_precision)
                #ET.SubElement(OtraMonedaDetalle, 'MontoItemOtraMoneda').text = self.format_valores(abs(reg_lin.balance)/tasa) 
            #ET.SubElement(item, 'MontoItem').text = self.format_valores((reg_lin.price_subtotal - descuento + recargo) * tasa)
            #ET.SubElement(item, 'MontoItem').text = self.format_valores((reg_lin.price_subtotal) * tasa)
            ET.SubElement(item, 'MontoItem').text = self.format_valores(monto_neto_item)

        return detallesitems
    
    def xml_ecf_descuentos(self, reg):       
        #Descuentos globales, cantidad negativa, precio positivo
        reg_lines = reg.invoice_line_ids.filtered(lambda lin: lin.display_type not in ('line_section', 'line_note') and lin.price_unit < 0)
        if len(reg_lines) == 0:
            return False
        NumeroLinea = 0 
        DescuentosORecargos = ET.Element('DescuentosORecargos')
        for reg_lin in reg_lines:  
            tasa = 1 / reg_lin.currency_rate         
            TipoValor = reg_lin.product_uom_id.name
            price_subtotal = reg_lin.price_subtotal * tasa
            if reg_lin.discount  > 0:
                TipoValor = '%'
                price_subtotal = reg_lin.discount
           
            if TipoValor not in ('$','%'):
                continue

            if TipoValor == '%':
                # Aseguramos que no supere 100% para evitar errores 27-10-2025                
                quantity = min(abs(reg_lin.quantity), 100)               

            IndicadorFacturacionDescuentooRecargo = '4'
            for tax in reg_lin.tax_ids:
                if 'ITBIS1' in tax.tax_group_id.name:
                    IndicadorFacturacionDescuentooRecargo = '1'
                if 'ITBIS2' in tax.tax_group_id.name:
                    IndicadorFacturacionDescuentooRecargo = '2'
                if 'ITBIS3' in tax.tax_group_id.name:
                    IndicadorFacturacionDescuentooRecargo = '3'
            NumeroLinea += 1
            DescuentoORecargo = ET.SubElement(DescuentosORecargos, 'DescuentoORecargo')
            ET.SubElement(DescuentoORecargo, 'NumeroLinea').text = str(NumeroLinea)
            ET.SubElement(DescuentoORecargo, 'TipoAjuste').text = 'D'
            ET.SubElement(DescuentoORecargo, 'IndicadorNorma1007').text = None
            ET.SubElement(DescuentoORecargo, 'DescripcionDescuentooRecargo').text = reg_lin.name
            ET.SubElement(DescuentoORecargo, 'TipoValor').text = TipoValor 
            ET.SubElement(DescuentoORecargo, 'ValorDescuentooRecargo').text = self.format_valores(abs(quantity)) if TipoValor == '%' else None
            ET.SubElement(DescuentoORecargo, 'MontoDescuentooRecargo').text = self.format_valores(abs(price_subtotal)) 
            ET.SubElement(DescuentoORecargo, 'MontoDescuentooRecargoOtraMoneda').text = None
            ET.SubElement(DescuentoORecargo, 'IndicadorFacturacionDescuentooRecargo').text = IndicadorFacturacionDescuentooRecargo
        return DescuentosORecargos
    
    def xml_ecf_totales(self, reg):
        """OBTENER LOS TOTALES Y RESUMEN IMPUESTOS,
        Se deben crear los siguientes grupos de Impuestos:
        ITBIS1 = 18% ITbis
        ITBIS2 = 16% de Itbis
        ITBIS3 = 0% de Itbis (Gravados per el cliente no paga ITBIS)
        RITBIS = Retencion de Itbis
        EXENTO = Exento
        ISR    = Retencion de Impuestos Sobre la Renta
        XXX-ISCE = Impuesto adicional selectivo Especifico (donde XXX es codigo DGII ejemplo 006-ISCE) 
        XXX-ISCA = Impuesto adicional selectivo Advalorem
        XXX-ISCO = Impuesto selectivo al consumo, Otros
        """
        tasa = 1 / reg.invoice_line_ids[0].currency_rate
        totales = reg._get_l10n_do_amounts()   #heredado -> l10n_do_accounting y reescrito
        MontoGravadoI1 = (totales['itbis_18_base_amount'] * tasa) if reg.ecf_monto_gravadoI1 == 0 else reg.ecf_monto_gravadoI1
        #MontoGravadoI2 = totales['itbis_16_base_amount'] if reg.ecf_monto_gravadoI2 == 0 else reg.ecf_monto_gravadoI2
        MontoGravadoI2 = (totales['itbis_16_base_amount'] * tasa) if reg.ecf_monto_gravadoI2 == 0 else reg.ecf_monto_gravadoI2
        MontoGravadoI3 = (totales['itbis_0_base_amount'] * tasa) if reg.ecf_monto_gravadoI3 == 0 else reg.ecf_monto_gravadoI3
        MontoExento = (totales['exempt_amount'] * tasa) if reg.ecf_monto_exento == 0 else reg.ecf_monto_exento
        TotalITBIS1 = (totales['itbis_18_tax_amount'] * tasa) if reg.ecf_total_ITBIS1 == 0 else reg.ecf_total_ITBIS1
        TotalITBIS2 = (totales['itbis_16_tax_amount'] * tasa)  if reg.ecf_total_ITBIS2 == 0 else reg.ecf_total_ITBIS2
        TotalITBISRetenido = totales['itbis_withholding_amount'] * tasa
        TotalISRRetencion = totales['isr_withholding_amount'] * tasa
        MontoTotal = (totales['l10n_do_invoice_total'] * tasa) if reg.ecf_monto_total == 0 else reg.ecf_monto_total
        #IMPUESTOS ADICIONALES
        MontoImpuestoAdicional = 0
        ImpuestosAdicionales = ET.Element('ImpuestosAdicionales')
        
        #Montos en Otras monedas
        MontoGravado1OtraMoneda  = totales['itbis_18_base_amount'] 
        MontoGravado2OtraMoneda =  totales['itbis_0_base_amount']
        MontoGravado3OtraMoneda = totales['itbis_0_base_amount']
        MontoGravadoTotalOtraMoneda = MontoGravado1OtraMoneda + MontoGravado2OtraMoneda + MontoGravado3OtraMoneda
        MontoExentoOtraMoneda = totales['exempt_amount']        
        TotalITBIS1OtraMoneda =  totales['itbis_18_tax_amount']
        TotalITBIS2OtraMoneda =  totales['itbis_16_tax_amount']
        TotalITBIS3OtraMoneda = totales['itbis_0_base_amount']
        TotalITBISOtraMoneda = TotalITBIS1OtraMoneda + TotalITBIS2OtraMoneda        
        MontoImpuestoAdicionalOtraMoneda = MontoImpuestoAdicional
        MontoTotalOtraMoneda = totales['l10n_do_invoice_total']
       
        #tax_totals = reg.tax_totals['groups_by_subtotal']['Subtotal']
        tax_totals = self._get_tax_groups_by_name()    
       
        for tax in tax_totals:
            tax_group_name = tax['group_name']
            base = tax['base_amount']
            tax_group_amount = tax['tax_amount']
            if '-ISC' in tax_group_name: # tax['tax_group_name']:
                type_tax_use = 'purchase'
                if reg.move_type.startswith('out'):
                    type_tax_use = 'sale'

                tax_id = self.env['account.tax'].search([('tax_group_id.id', '=',tax['tax_group_id']),('type_tax_use','=',type_tax_use)])
                MontoImpuestoAdicional += tax_group_amount #tax['tax_group_amount'] Migracion 18 26-01-2025

                # Si se coloca la propina en las ventas da errores por eso se agrego esta parte 18-10-202 Pedro Nunez.
                if  type_tax_use == 'purchase' and  reg.l10n_do_sequence_prefix in ('E41','E43','47'):
                    #tax_id = self.env['account.tax'].search([('tax_group_id.id', '=',tax['tax_group_id'])])
                    MontoImpuestoAdicional += tax_group_amount #tax['tax_group_amount'] Migracion 18 26-01-2025
                    ImpuestoAdicional = ET.SubElement(ImpuestosAdicionales, 'ImpuestoAdicional')
                    ET.SubElement(ImpuestoAdicional, 'TipoImpuesto').text = tax_group_name.split('-')[0] if '-' in tax_group_name else None
                    ET.SubElement(ImpuestoAdicional, 'TasaImpuestoAdicional').text = tax_id.amount
                    ET.SubElement(ImpuestoAdicional, 'MontoImpuestoSelectivoConsumoEspecifico').text = tax_group_amount if 'ISCE' in tax_group_name else None
                    ET.SubElement(ImpuestoAdicional, 'MontoImpuestoSelectivoConsumoAdvalorem').text = tax_group_amount if 'ISCA' in tax_group_name else None
                    ET.SubElement(ImpuestoAdicional, 'OtrosImpuestosAdicionales').text = tax_group_amount if 'ISCO' in tax_group_name else None

        TotalITBIS = self.format_valores(TotalITBIS1 + TotalITBIS2) 
        TotalITBIS = '0.00' if MontoGravadoI3 > 0 and TotalITBIS == None else TotalITBIS
        totales =  ET.Element('Totales')
        ET.SubElement(totales, 'MontoGravadoTotal').text = self.format_valores((MontoGravadoI1 + MontoGravadoI2 + MontoGravadoI3)) 
        ET.SubElement(totales, 'MontoGravadoI1').text = self.format_valores(MontoGravadoI1) 
        ET.SubElement(totales, 'MontoGravadoI2').text = self.format_valores(MontoGravadoI2)
        ET.SubElement(totales, 'MontoGravadoI3').text = self.format_valores(MontoGravadoI3) 
        ET.SubElement(totales, 'MontoExento').text = self.format_valores(MontoExento) if MontoExento else None
        ET.SubElement(totales, 'ITBIS1').text = '18' if MontoGravadoI1 > 0 else None
        ET.SubElement(totales, 'ITBIS2').text = '16' if MontoGravadoI2 > 0 else None
        ET.SubElement(totales, 'ITBIS3').text = '0' if MontoGravadoI3 > 0 else None
        ET.SubElement(totales, 'TotalITBIS').text = TotalITBIS 
        ET.SubElement(totales, 'TotalITBIS1').text = self.format_valores(TotalITBIS1)
        ET.SubElement(totales, 'TotalITBIS2').text = self.format_valores(TotalITBIS2) 
        ET.SubElement(totales, 'TotalITBIS3').text = '0.00' if MontoGravadoI3 > 0 else None
        ET.SubElement(totales, 'MontoImpuestoAdicional').text = self.format_valores(MontoImpuestoAdicional)
        totales.append(ImpuestosAdicionales)
        ET.SubElement(totales, 'MontoTotal').text = self.format_valores(MontoTotal)
        #ET.SubElement(totales, 'MontoNoFacturable').text = "0.00"  # 5/5/2025 PN nuevo campo provicional que fue agreado se queda por sale algun error luego se decomenta
        ET.SubElement(totales, 'MontoPeriodo').text = self.format_valores(MontoTotal) if reg.l10n_do_sequence_prefix != 'E32' else None 
        ET.SubElement(totales, 'ValorPagar').text = self.format_valores(MontoTotal) if reg.l10n_do_sequence_prefix in ('E31','E32','E41','E44') else None  
        if reg.l10n_do_sequence_prefix not in ('E47'):
            ET.SubElement(totales, 'TotalITBISRetenido').text = self.format_valores(TotalITBISRetenido) #* tasa)  
        if reg.l10n_do_sequence_prefix in ('E47'):
            ET.SubElement(totales, 'TotalISRRetencion').text = self.format_valores(TotalISRRetencion) if TotalISRRetencion else '0.00'
        else:
            ET.SubElement(totales, 'TotalISRRetencion').text = self.format_valores(TotalISRRetencion)
        

        OtraMoneda = None
        if reg.currency_id.id != reg.company_id.currency_id.id:
            TotalITBIS = self.format_valores(TotalITBIS1 + TotalITBIS2)
            TotalITBIS = '0.00' if MontoGravadoI3 > 0 and TotalITBIS == None else TotalITBIS

            OtraMoneda =  ET.Element('OtraMoneda')
            ET.SubElement(OtraMoneda, 'TipoMoneda').text = reg.currency_id.name
            ET.SubElement(OtraMoneda, 'TipoCambio').text = "{0:.4f}".format(tasa)
            ET.SubElement(OtraMoneda, 'MontoGravadoTotalOtraMoneda').text =  self.format_valores(MontoGravadoTotalOtraMoneda) # MontoGravadoI1 + MontoGravadoI2 + MontoGravadoI3) 
            ET.SubElement(OtraMoneda, 'MontoGravado1OtraMoneda').text = self.format_valores(MontoGravado1OtraMoneda) #MontoGravadoI1)
            ET.SubElement(OtraMoneda, 'MontoGravado2OtraMoneda').text = self.format_valores(MontoGravado2OtraMoneda)# MontoGravadoI2)
            ET.SubElement(OtraMoneda, 'MontoGravado3OtraMoneda').text = self.format_valores(MontoGravado3OtraMoneda)  #MontoGravadoI3)
            ET.SubElement(OtraMoneda, 'MontoExentoOtraMoneda').text = self.format_valores(MontoExentoOtraMoneda) #MontoExento)
            ET.SubElement(OtraMoneda, 'TotalITBISOtraMoneda').text = self.format_valores(TotalITBISOtraMoneda) # TotalITBIS
            ET.SubElement(OtraMoneda, 'TotalITBIS1OtraMoneda').text = self.format_valores(TotalITBIS1OtraMoneda)  #TotalITBIS1)
            ET.SubElement(OtraMoneda, 'TotalITBIS2OtraMoneda').text = self.format_valores(TotalITBIS2OtraMoneda)  #TotalITBIS2)
            ET.SubElement(OtraMoneda, 'TotalITBIS3OtraMoneda').text = self.format_valores( MontoGravado3OtraMoneda) #"0.00" = totales['itbis_0_base_amount']
            ET.SubElement(OtraMoneda, 'MontoImpuestoAdicionalOtraMoneda').text = self.format_valores(MontoImpuestoAdicionalOtraMoneda)#MontoImpuestoAdicional)
            ET.SubElement(OtraMoneda, 'MontoTotalOtraMoneda').text = self.format_valores(MontoTotalOtraMoneda) # MontoTotal)

        return totales, OtraMoneda

    def xml_rfce(self, reg, CodigoSeguridad):
        #FACTURA DE CONSUMO E32 FORMATO RESUMEN MONTO < 250,000.00
        #RFCE
        rfce = ET.Element('RFCE')

        #RFCE/ENCABEZADO
        encabezado = ET.SubElement(rfce, 'Encabezado')
        ET.SubElement(encabezado, 'Version').text = '1.0'

        #RFCE/ENCABEZADO/IDDOC 
        IdDoc = self.xml_ecf_iddoc(reg)
        IdDoc.remove(IdDoc.find('IndicadorMontoGravado'))
        if IdDoc.find('FechaLimitePago') != None:
            IdDoc.remove(IdDoc.find('FechaLimitePago'))
        encabezado.insert(1, IdDoc)

        #RFCE/ENCABEZADO/EMISOR
        emisor =  ET.SubElement(encabezado, 'Emisor')
        ET.SubElement(emisor, 'RNCEmisor').text = reg.company_id.vat
        ET.SubElement(emisor, 'RazonSocialEmisor').text = reg.company_id.name
        ET.SubElement(emisor, 'FechaEmision').text = self.format_valores(reg.invoice_date)

        #RFCE/ENCABEZADO/COMPRADOR
        comprador =  ET.SubElement(encabezado, 'Comprador')
        if reg.l10n_do_sequence_prefix == 'E47':            
            ET.SubElement(comprador, 'IdentificadorExtranjero').text = reg.partner_id.vat
        else:
            ET.SubElement(comprador, 'RNCComprador').text =  self._clean_rnc(reg.partner_id.vat) 
        ET.SubElement(comprador, 'RazonSocialComprador').text = reg.partner_id.parent_name if reg.partner_id.parent_name else reg.partner_id.name

        #RFCE/ENCABEZADO/TOTALES
        xml_totales, otra_moneda = self.xml_ecf_totales(reg)

        #Eliminamos los tag no usado en el resumen 
        if xml_totales.find('ITBIS1') != None:
            xml_totales.remove(xml_totales.find('ITBIS1'))
        if xml_totales.find('ITBIS2') != None:
            xml_totales.remove(xml_totales.find('ITBIS2'))
        if xml_totales.find('ITBIS3') != None:
            xml_totales.remove(xml_totales.find('ITBIS3'))
        if xml_totales.find('ValorPagar') != None:
            xml_totales.remove(xml_totales.find('ValorPagar'))
        encabezado.append(xml_totales)

        #RFCE/ENCABEZADO/CODIGOSEGURIDADECF
        ET.SubElement(encabezado, 'CodigoSeguridadeCF').text = CodigoSeguridad

        #Borrar todos los elementos vacios
        for x in range(10):
            for element in rfce.findall('.//'):
                for subelement in element:
                    if subelement.__len__() == 0 and subelement.text in (False, None, ''):
                        element.remove(subelement)

        return (ET.tostring(rfce))

    def acecf(self, inv):
        """
        Aprobacion comercial de las facturas de compras registradas
        *Se envia a la DGII y al proveedor
        """
        if inv.is_ecf_invoice == False:
            return

        #1.-Cargamos el certificado para la firma y obtenemos el token de la semilla
        sign = XMLSignature(inv.company_id.cert, inv.company_id.cert_password, inv.company_id.l10n_do_ecf_ambiente)
        token = sign._get_token_semilla()['token']

        #2.- Genera el xml
        xml = self.xml_acecf(inv)

        #3.- Firmar el xml
        _xml, CodigoSeguridad, FechaHoraFirma = sign._sign_xml(xml)

        #4.- Buscamos el URL del proveedor
        resp_json = sign._directorios_url(token,self.company_id.vat) 
        urlAceptacion = None
        if resp_json:
            urlRecepcion = resp_json[0]['urlRecepcion']
            urlAceptacion = resp_json[0]['urlAceptacion']

        file_name = inv.company_id.vat + inv.ref + '.xml'

        #5.- Envio al proveedor o DGII
        #Con la url se envio al proveedor
        #Sin el url se envia a la DGII
        if urlAceptacion:
            Response = sign._aprobacion_comercial(_xml, file_name, token, urlAceptacion)
            # Response = sign._aprobacion_comercial(_xml, file_name, token, None)
            Response = Response.replace(",", "\n")
            inv.l10n_do_ecf_response = Response

    def xml_acecf(self, reg):
        #APROBACION COMERCIAL AL PROVEEDOR Y DGII
        FechaHora = datetime.now()
        FechaHoraTxt = FechaHora.strftime('%d-%m-%Y %H:%M:%S')
        #FechaHoraTxt = '10-06-2023 17:08:55'

        #ACECF
        acecf = ET.Element('ACECF')

        #ACECF/DETALLEAPROBACIONCOMERCIAL
        DetalleAprobacionComercial = ET.SubElement(acecf, 'DetalleAprobacionComercial')
        ET.SubElement(DetalleAprobacionComercial, 'Version').text = '1.0'
        ET.SubElement(DetalleAprobacionComercial, 'RNCEmisor').text = reg.partner_id.vat
        ET.SubElement(DetalleAprobacionComercial, 'eNCF').text = reg.ref
        ET.SubElement(DetalleAprobacionComercial, 'FechaEmision').text = self.format_valores(reg.invoice_date)
        ET.SubElement(DetalleAprobacionComercial, 'MontoTotal').text = "{0:.2f}".format(reg.amount_total)
        ET.SubElement(DetalleAprobacionComercial, 'RNCComprador').text = self._clean_rnc(reg.company_id.vat)            
        ET.SubElement(DetalleAprobacionComercial, 'Estado').text = '1' #1: e-CF Aceptado, 2: e-CF Rechazado
        # ET.SubElement(DetalleAprobacionComercial, 'DetalleMotivoRechazo').text = ''
        ET.SubElement(DetalleAprobacionComercial, 'FechaHoraAprobacionComercial').text = FechaHoraTxt

        xml = ET.tostring(acecf)
        return (xml)

    def format_valores (self, valor,precision = 2):        
        if valor in (None, 0):
            return None
        if 'date' in str(type(valor)):
            return (valor.strftime('%d-%m-%Y'))
        else:
            if precision == 0:
                return("{0:.0f}".format(valor))
            elif precision != 2:
                return("{0:.4f}".format(valor))
            return("{0:.2f}".format(valor))
    
    def _build_dgii_url(self, base_url, params,inv):
        """Construye URL DGII correctamente codificada."""
        from urllib.parse import urlencode, quote_plus, quote
        
        if inv.l10n_do_sequence_prefix == 'E32' and inv.amount_total < 250000:
            return f"{base_url}?{urlencode(params, quote_via=quote)}"
        return f"{base_url}?{urlencode(params, quote_via=quote)}"
        #return f"{base_url}?{urlencode(params, quote_via=quote_plus)}"
        
    @api.depends(
        "l10n_do_ecf_security_code",
        "l10n_do_ecf_sign_date",
        "invoice_date",
        "is_ecf_invoice",
        "state",
        "amount_total",
    )
    def _compute_l10n_do_electronic_stamp(self):
        """
        Calcula la URL oficial de timbre DGII (ConsultaTimbre o ConsultaTimbreFC)
        y genera automáticamente el código QR como imagen PNG (campo Binary).
        """
        invoices = self.filtered(
            lambda i: i.is_ecf_invoice
            and i.l10n_do_ecf_security_code
            and i.state == "posted"
            and i.l10n_do_ecf_sign_date
        )

        for inv in invoices:           
            try:
                tz_name = inv.company_id.partner_id.tz or inv.env.user.tz or "America/Santo_Domingo"
                tz_local = pytz.timezone(tz_name)
            except Exception:
                tz_local = timezone(timedelta(hours=-4)) 

            ambiente = inv.l10n_do_ecf_ambiente or inv.company_id.l10n_do_ecf_ambiente
            zona_horaria = timezone(timedelta(hours=-4))  # Hora República Dominicana
           
            # Convertir la fecha de firma a zona horaria local
            FechaFirma = inv.l10n_do_ecf_sign_date
            if hasattr(FechaFirma, "tzinfo") and FechaFirma.tzinfo is not None:
                FechaFirma = FechaFirma.astimezone(tz_local)
            else:
                FechaFirma = tz_local.localize(FechaFirma)
            
            totales = inv._get_l10n_do_amounts()
            #monto = round(totales.get("l10n_do_invoice_total", 0), 2)
            monto = inv.amount_total
            if inv.currency_id != inv.company_id.currency_id:    
                tasa = 1 / inv.invoice_line_ids[0].currency_rate
                monto = round(monto * tasa, 2)
                
           
            # Parámetros de DGII según tipo de eCF
            if inv.l10n_do_sequence_prefix == 'E32' and inv.amount_total < 250000:
                # FACTURA CONSUMO < 250k
                params = {
                    "RncEmisor": inv.company_id.vat,
                    "ENCF": inv.ref,
                    "MontoTotal": f"{monto:.2f}",
                    "CodigoSeguridad":inv.l10n_do_ecf_security_code,                 
                }
                url_base = f"https://fc.dgii.gov.do/{ambiente}/ConsultaTimbreFC"
            else:
                # OTROS TIPOS DE eCF
                params = {
                    "RncEmisor": inv.company_id.vat,
                    "RncComprador": inv.partner_id.vat,
                    "ENCF": inv.ref,
                    "FechaEmision": inv.format_valores(inv.invoice_date),
                    "MontoTotal": f"{monto:.2f}",
                    "FechaFirma": FechaFirma.strftime("%d-%m-%Y %H:%M:%S"),
                    #"CodigoSeguridad": inv.l10n_do_ecf_security_code.replace("/", "%2F"),
                    "CodigoSeguridad": inv.l10n_do_ecf_security_code,
                }
                if inv.l10n_do_sequence_prefix == 'E43':
                    # En tipo E43 (Compras Electrónicas) no se incluye RNC del comprador
                    params.pop("RncComprador")
                url_base = f"https://ecf.dgii.gov.do/{ambiente}/ConsultaTimbre"
       
            # Generar URL final de timbre
            #url_timbre = self._build_dgii_url(url_base, params) #f"{url_base}?{urlencode(params)}"
            #inv.l10n_do_electronic_stamp = urls.url_quote_plus(url_timbre, safe="%")
            #inv.l10n_do_electronic_stamp = quote(url_timbre, safe=':/?=&+.%')
            url_timbre = self._build_dgii_url(url_base, params,inv)
            inv.l10n_do_electronic_stamp = url_timbre
            # ----------------------------------------------------------------
            # GENERAR IMAGEN QR (campo Binary)
            # ----------------------------------------------------------------
            try:
                qr = qrcode.QRCode(
                    version=8,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=20,
                    border=4,
                )
                qr.add_data(url_timbre)
                qr.make(fit=True)
                img = qr.make_image()
                temp = BytesIO()
                img.save(temp, format="PNG")
                inv.l10n_do_ecf_qr_image = base64.b64encode(temp.getvalue())
            except Exception as e:
                inv.l10n_do_ecf_qr_image = False
                inv.l10n_do_ecf_xml_validation = f"Error al generar QR: {str(e)}"

        # Si no aplica, limpiar campos
        (self - invoices).update({
            "l10n_do_electronic_stamp": False,
            "l10n_do_ecf_qr_image": False,
        })
        
    """
    def _get_ecf_discount_amount(self,reg,tax_group_name):
        for d in reg:
            if d.ecf_monto_descuento > 0:
                for tax in d.tax_ids:
                    if tax_group_name == tax.tax_group_id.name:
                        return  d.ecf_monto_descuento
        return 0
    """
    def _get_tax_groups_by_name(self):
        """
        Devuelve los grupos de impuestos del subtotal principal
        Compatible Odoo 18
        """
        self.ensure_one()
        result = []

        for subtotal in self.tax_totals.get('subtotals', []):
            if subtotal.get('name') == 'Subtotal':
                result.extend(subtotal.get('tax_groups', []))

        return result

    def _get_l10n_do_amounts(self, company_currency=False):
        """
        ***MERPLUS, Heredado de l10n_do_accounting***
        Method used to to prepare dominican fiscal invoices amounts data. Widely used
        on reports and electronic invoicing.
        """
        self.ensure_one()
        MontoGravadoI1 = 0 
        MontoGravadoI2 = 0 
        MontoGravadoI3 = 0 
        MontoExento = 0 
        TotalITBIS1 = 0 
        TotalITBIS2 = 0 
        TotalITBISRetenido = 0 
        TotalISRRetencion = 0 
        MontoImpuestoAdicional = 0
        tasa = 1 / self.invoice_line_ids[0].currency_rate
        MontoTotal = self.amount_total
        #for r in range(10):
        #    print("{} {} {}".format(r,self.tax_totals['groups_by_subtotal'],self.tax_totals))
        #tax_totals = self.tax_totals['groups_by_subtotal']['Subtotal']
        tax_totals = self._get_tax_groups_by_name()
        ecf_discount = 0
        for tax in tax_totals:
            name = tax['group_name']
            base = tax['base_amount']
            amount = tax['tax_amount']
            if '-ISC' in name:
                MontoImpuestoAdicional += amount
            elif 'ITBIS1' in name:
                MontoGravadoI1 = base
                TotalITBIS1 = amount
            elif 'ITBIS2' in name:
                MontoGravadoI2 = base
                TotalITBIS2 = amount
            elif 'ITBIS3' in name:
                MontoGravadoI3 = base
            elif 'EXENTO' in name:
                MontoExento += base
            elif 'RITBIS' in name:
                TotalITBISRetenido = abs(amount)
                MontoTotal -= amount
            elif 'ISR' in name:
                TotalISRRetencion = abs(amount)
                MontoTotal -= amount         
            else:            
                self.l10n_do_ecf_status = '5'
                self.l10n_do_ecf_response = """Los grupos de Impuestos deben ser los siguientes:
                  ITBIS1 para el 18%, 
                  ITBIS2 para el 16%, 
                  ITBIS3 para el 0%, 
                  EXENTO para los no gravados, 
                  RTIBIS para retención de itbis, 
                  ISR para retención del Impuesto sobre la renta"""
        
        # TotalITBIS = (TotalITBIS1 + TotalITBIS2) * tasa
        # TotalITBIS = '0.00' if MontoGravadoI3 > 0 and TotalITBIS == None else TotalITBIS
        result = {
            "base_amount": (MontoGravadoI1 + MontoGravadoI2 + MontoGravadoI3), # * tasa 9/5/2025 Pedro Nunez se quito  porque la vuelve a multiplicar fuera 
            "exempt_amount": MontoExento, # * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "itbis_18_tax_amount": TotalITBIS1, # * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "itbis_18_base_amount": MontoGravadoI1,# * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "itbis_16_tax_amount": TotalITBIS2,# * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "itbis_16_base_amount": MontoGravadoI2, # * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "itbis_0_tax_amount": 0,  # not supported
            "itbis_0_base_amount": MontoGravadoI3, # * tasa #0,  # not supported 06/05/2025 Pedro Nunez se agrego la variable MontoGravadoI3 
            "itbis_withholding_amount": TotalITBISRetenido, # * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "itbis_withholding_base_amount": 0,
            "isr_withholding_amount": TotalISRRetencion, # * tasa 9/5/2025 Pedro Nunez se quito la tasa por la vuelve a multiplicar fuera
            "isr_withholding_base_amount": 0,
            "l10n_do_invoice_total": MontoTotal,
        }

        # convert values to positives
        for key, value in result.items():
            result[key] = abs(value)

        # result["l10n_do_invoice_total"] = (self.move_id.amount_untaxed + result["itbis_18_tax_amount"] + result["itbis_16_tax_amount"] + result["itbis_0_tax_amount"])
        if self.currency_id != self.company_id.currency_id:
            # rate = (self.currency_id + self.company_id.currency_id)._get_rates(self.company_id, self.move_id.date).get(self.currency_id.id) or 1
            currency_vals = {}
            for k, v in result.items():
                currency_vals[k + "_currency"] = v / tasa
            result.update(currency_vals)

        return result
    
   
    def validar_timbre_dgii(self):
        """
        Regenera y valida el timbre DGII usando la misma lógica del compute.
        """
        self._compute_l10n_do_electronic_stamp()
        for inv in self:
            if inv.l10n_do_electronic_stamp:
                inv.l10n_do_ecf_xml_validation = "✅ Timbre DGII regenerado y validado correctamente."
            else:
                inv.l10n_do_ecf_xml_validation = "⚠️ No se pudo generar el timbre DGII."
    
    def _clean_rnc(self, value):
        if not value:
            return ''
        return ''.join(c for c in value.strip() if c.isalnum())

    def action_enviar_dgii_forzar_trackid(self):
        for inv in self:
            if not inv.l10n_do_ecf_edi_file:
                return

            sign = XMLSignature(
                inv.company_id.cert,
                inv.company_id.cert_password,
                inv.l10n_do_ecf_ambiente
            )

            token_data = sign._get_token_semilla()
            if not token_data or 'token' not in token_data:
                raise UserError("DGII no respondió token.")

            token = token_data['token']
            xml = base64.b64decode(inv.l10n_do_ecf_edi_file)

            resp_json, response = sign._validate_ecf(
                xml,
                inv.l10n_do_ecf_edi_file_name,
                token
            )

            inv.l10n_do_ecf_response = response.replace(",", " ")

            if resp_json:
                inv.l10n_do_ecf_trackid = resp_json.get('trackId')

                codigo = resp_json.get('codigo')
                inv.l10n_do_ecf_status = str(codigo) if codigo else '3'
                
    def _compute_show_reset_to_draft_button(self):
        super()._compute_show_reset_to_draft_button()

        for move in self:
            if move.l10n_do_ecf_status in ('1', '4'):
                move.show_reset_to_draft_button = False

    def _get_l10n_do_ecf_modification_code(self):
        """ Return the list of e-CF modification codes required by DGII. """
        return [("1", _("01 - Anulación total")),
                ("2", _("02 - Corrección de texto")),
                ("3", _("03 - Corrección de monto")),
                ("4", _("04 - Reemplazo de NCF emitido en contingencia")),
                ("5", _("05 - Referencia de factura electrónica de consumo")),]
    
    @api.depends('invoice_line_ids.tax_ids', 'invoice_line_ids.discount')
    def _compute_indicador_monto_grabado(self):
        for reg in self:
            tiene_descuento = any(line.discount > 0 for line in reg.invoice_line_ids)
            impuesto_incluido = any(
                tax.price_include
                for line in reg.invoice_line_ids
                for tax in line.tax_ids)
            
            if tiene_descuento and impuesto_incluido:
                reg.indicador_monto_grabado = '1'
            else:
                reg.indicador_monto_grabado = '0'