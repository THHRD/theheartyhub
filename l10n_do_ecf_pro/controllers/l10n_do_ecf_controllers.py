from odoo.http import request, Controller, route
from lxml import etree
import xml.etree.ElementTree as ET
from datetime import datetime
from ..models.sign import XMLSignature
import pprint
import logging
import os
import re
import tempfile
_logger = logging.getLogger(__name__)


parser = etree.XMLParser(remove_blank_text=True)


class EcfControllers(Controller):

    # ============================================================
    # Detectar RNC dinámico según:
    #   1) URL
    #   2) subdominio *.shortcut.do
    #   3) empresa en la base de datos (fallback)
    # ============================================================
    def _get_company_by_rnc(self, rnc=None):

        # 1️⃣ RNC en URL /<rnc>/fe/...
        if rnc and rnc.isdigit():
            company = request.env['res.company'].sudo().search([('vat', '=', rnc)], limit=1)
            if company:
                return company

        # 2️⃣ RNC en subdominio
        hostname = request.httprequest.host.split('.')[0]
        if hostname.isdigit():
            company = request.env['res.company'].sudo().search([('vat', '=', hostname)], limit=1)
            if company:
                return company

        # Entornos ERP17 (SOFTNET without RNC in subdomain or url path)
        if hostname in ['erp17', 'erp17-test']:
            company = request.env['res.company'].sudo().search([('vat', '=', '131071422')], limit=1)
            if company:
                return company

        # 3️⃣ Fallback: empresa activa de la base
        return request.env['res.company'].sudo().search([], limit=1)

    @route([
    '/<path:fullpath>',
    ], type='http', auth='public', csrf=False, methods=['GET', 'POST'])
    def dynamic_router(self, fullpath=None, **kw):

        # Normalizar
        ruta = (fullpath or "").lower().strip("/")

        # GET: solo para pruebas
        if request.httprequest.method == "GET":
            return "Servicio activo"

        # === MATCH EXACTO ===
        if ruta.endswith("fe/recepcion/api/ecf"):
            return self.EcfRecepcion(**kw)

        if ruta.endswith("fe/aprobacioncomercial/api/ecf"):
            return self.EcfAprobacion(**kw)

        return request.make_response("Ruta no reconocida", status=404)

    # ============================================================
    # RECEPCIÓN DE ECF
    # ============================================================
    def EcfRecepcion(self, **kw):

        '''
            #TODO 
            Recepción de un e-CF que envía el emisor electrónico (nuestro proveedor).

            No confundir con el Acuse de Recibo. Este se recibe cuando el emisor envía el e-CF (probablemente)

            Aquí se debe seguir este flujo:
            - Que la firma digital sea válida y corresponda al emisor (nuestro proveedor).
            - Si la firma es válida, entonces se debe generar el Acuse de Recibo (ARECF) y firmarlo digitalmente con nuestro certificado.
            - Registrar la factura de proveedor y dejarla en borrador para validación manual, y en este caso notificar al staff.
            
        '''

        xml_file = request.httprequest.files.get("xml")
        if not xml_file:
            return request.make_response("No se recibió XML", status=400)

        xml = xml_file.read()
        try:
            _xml = etree.XML(xml, parser=parser)
        except:
            return request.make_response("XML inválido", status=400)

        rnc_comprador = _xml.find('Encabezado/Comprador/RNCComprador').text
        rnc_emisor = _xml.find('Encabezado/Emisor/RNCEmisor').text
        razon_social_emisor = _xml.find('Encabezado/Emisor/RazonSocialEmisor').text

        # Empresa correcta de la base
        company = self._get_company_by_rnc(rnc_comprador)

        if not company:
             return request.make_response(f"Emisor {rnc_emisor} no configurado", status=404)

        self._store_xml_and_notify(
            xml_content=xml,
            original_filename=getattr(xml_file, "filename", None),
            company=company,
            rnc_emisor=rnc_emisor,
            rnc_comprador=rnc_comprador,
            razon_social_emisor=razon_social_emisor,
            endpoint="recepcion",
        )
        
        # Safety Check to prevent the crash
        if not company.cert:
            return request.make_response(f"La compañía {company.name} no tiene certificado configurado", status=500)        

        # Generar ARECF
        now = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

        arecf = ET.Element("ARECF")
        det = ET.SubElement(arecf, "DetalleAcusedeRecibo")
        ET.SubElement(det, "Version").text = "1.0"
        ET.SubElement(det, "RNCEmisor").text = rnc_emisor
        ET.SubElement(det, "RNCComprador").text = rnc_comprador
        ET.SubElement(det, "eNCF").text = _xml.find("Encabezado/IdDoc/eNCF").text
        ET.SubElement(det, "Estado").text = "0"
        ET.SubElement(det, "FechaHoraAcuseRecibo").text = now

        xml_out = ET.tostring(arecf)

        signer = XMLSignature(company.cert, company.cert_password, company.l10n_do_ecf_ambiente)
        firmado, cs, ffirm = signer._sign_xml(xml_out)

        return request.make_response(firmado, headers={'Content-Type': 'application/xml'})

    # ============================================================
    # APROBACIÓN COMERCIAL
    # ============================================================
    def EcfAprobacion(self, **kw):

        #TODO según la DGII, aquí se debe: 
        # El receptor electrónico podrá dar respuesta de su conformidad, al emisor electrónico, mediante la Aprobación o Rechazo Comercial.
        # Por lo cual hay que leer el XML recibido y determinar si se aprueba o rechaza comercialmente y si es rechazo entonces alertar
        # al staff para emitor una nota de crédito en el eCF.         

        '''
            ¿Qué implica el rechazo de un e-CF en la Aprobación o Rechazo Comercial? 

            El rechazo de un e-CF implica que el receptor no está de acuerdo con la transacción realizada, por lo que en este caso, 
            el emisor electrónico deberá anular mediante Nota de Crédito el e-CF previamente emitido y aceptado en DGII.
        '''

        xml_file = request.httprequest.files.get("xml")
        if not xml_file:
            return request.make_response("Insatisfactorio", status=400)

        try:
            xml_content = xml_file.read()
            _xml = etree.XML(xml_content, parser=parser)
        except:
            return request.make_response("Insatisfactorio", status=400)

        rnc_emisor = _xml.findtext('DetalleAprobacionComercial/RNCEmisor')
        rnc_comprador = _xml.findtext('DetalleAprobacionComercial/RNCComprador')
        company = self._get_company_by_rnc(rnc_emisor) if rnc_emisor else self._get_company_by_rnc()

        self._store_xml_and_notify(
            xml_content=xml_content,
            original_filename=getattr(xml_file, "filename", None),
            company=company,
            rnc_emisor=rnc_emisor,
            rnc_comprador=rnc_comprador,
            endpoint="aprobacion",
        )

        return "Satisfactorio"

    def _store_xml_and_notify(
        self,
        xml_content,
        original_filename=None,
        company=None,
        rnc_emisor=None,
        rnc_comprador=None,
        razon_social_emisor=None,
        endpoint=None,
    ):
        temp_dir = os.path.join(tempfile.gettempdir(), "ecf_commings")
        try:
            os.makedirs(temp_dir, exist_ok=True)
        except Exception:
            _logger.exception("Failed to create temp directory for ECF XML")
            return None

        original_name = os.path.basename(original_filename or "ecf.xml")
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", original_name).strip("_")
        if not safe_name:
            safe_name = "ecf.xml"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        stored_name = f"{timestamp}_{safe_name}"
        stored_path = os.path.join(temp_dir, stored_name)

        try:
            with open(stored_path, "wb") as handle:
                handle.write(xml_content)
        except Exception:
            _logger.exception("Failed to store ECF XML in temp dir")
            return None

        subject = "ECF XML received"
        if endpoint:
            subject = f"ECF XML received ({endpoint})"

        body_parts = [
            "An ECF XML file was received and stored.",
            f"Stored path: {stored_path}",
        ]
        if original_filename:
            body_parts.append(f"Original filename: {original_filename}")
        if rnc_emisor:
            body_parts.append(f"RNC Emisor: {rnc_emisor}")
        if razon_social_emisor:
            body_parts.append(f"Razon Social Emisor: {razon_social_emisor}")
        if rnc_comprador:
            body_parts.append(f"RNC Comprador: {rnc_comprador}")
        if company:
            body_parts.append(f"Company: {company.name}")

        body_html = "<br/>".join(body_parts)

        email_sent = False
        config = request.env["ir.config_parameter"].sudo()
        recipients = ["info@softnet.com.do"]

        if recipients:
            email_from = None
            if company:
                email_from = company.email or company.partner_id.email
            email_from = email_from or request.env.user.company_id.email
            email_from = email_from or config.get_param("mail.default.from")

            mail_values = {
                "subject": subject,
                "body_html": body_html,
                "email_to": ", ".join(recipients),
            }
            if email_from:
                mail_values["email_from"] = email_from

            try:
                request.env["mail.mail"].sudo().create(mail_values).send()
                email_sent = True
            except Exception:
                _logger.exception("Failed to send ECF XML notification email")

        if email_sent:
            return stored_path

        user_ids = [2]

        partners = request.env["res.users"].sudo().browse(user_ids).mapped("partner_id")
        if not partners:
            _logger.warning("ECF XML notify users not found; skipped Odoo alert")
            return stored_path

        target_company = company or self._get_company_by_rnc()
        try:
            target_company.sudo().message_post(
                body=body_html,
                partner_ids=partners.ids,
                message_type="notification",
                subtype_xmlid="mail.mt_note",
            )
        except Exception:
            _logger.exception("Failed to post ECF XML notification alert")

        return stored_path
