from contextlib import contextmanager

import odoo
from odoo.tests import common

from odoo.tests.common import TransactionCase

ADMIN_USER_ID = common.ADMIN_USER_ID


@contextmanager
def environment():
    """ Return an environment with a new cursor for the current database; the
        cursor is committed and closed after the context block.
    """
    registry = odoo.registry(common.get_db_name())
    with registry.cursor() as cr:
        yield odoo.api.Environment(cr, ADMIN_USER_ID, {})


class CommonSetup(TransactionCase):
    def setUp(self):
        super(CommonSetup, self).setUp()

        self.fiscal_sequence_obj = self.env["account.fiscal.sequence"]
        self.fiscal_type_obj = self.env["account.fiscal.type"]
        self.fiscal_seq_credito_fiscal = self.ref(
            "l10n_do_ncf.credito_fiscal_demo"
        )
        self.fiscal_seq_unico = self.ref("l10n_do_ncf.unico_demo")
        self.fiscal_type_credito_fiscal = self.ref(
            "l10n_do_ncf.fiscal_type_credito_fiscal"
        )
        self.fiscal_type_consumo = self.ref("l10n_do_ncf.fiscal_type_consumo")
        self.fiscal_type_unico = self.ref("l10n_do_ncf.fiscal_type_unico")


class AccountMoveCommon(CommonSetup):
    def setUp(self):
        super(AccountMoveCommon, self).setUp()

        self.invoice_obj = self.env["account.move"]
        self.journal_obj = self.env["account.journal"]
        self.partner_obj = self.env["res.partner"]
        self.fiscal_type_obj = self.env["account.fiscal.type"]
        self.invoice_refund_obj = self.env["account.move.reversal"]

        self.sale_journal = False
        self.purchase_journal = False

        # Setup Fiscal Journals
        for journal in self.journal_obj.search([("type", "in", ("sale", "purchase"))]):
            journal.l10n_do_fiscal_journal = True
            if journal.type == "sale":
                self.sale_journal = journal
            else:
                self.purchase_journal = journal

        # Demo partners
        self.partner_demo_1 = self.ref("l10n_do_ncf.res_partner_demo_1")
        self.partner_demo_2 = self.ref("l10n_do_ncf.res_partner_demo_2")
        self.partner_demo_3 = self.ref("l10n_do_ncf.res_partner_demo_3")
        self.partner_demo_4 = self.ref("l10n_do_ncf.res_partner_demo_4")
        self.partner_demo_5 = self.ref("l10n_do_ncf.res_partner_demo_5")

        # Demo fiscal sequence
        self.seq_fiscal = self.ref("l10n_do_ncf.credito_fiscal_demo")
        self.seq_consumo = self.ref("l10n_do_ncf.consumo_demo")
        self.seq_unico = self.ref("l10n_do_ncf.unico_demo")
        self.seq_informal = self.ref("l10n_do_ncf.informal_demo")
        self.seq_credit_note = self.ref("l10n_do_ncf.cn_demo")
        self.seq_debit_note = self.ref("l10n_do_ncf.dn_demo")

        # Demo fiscal type
        self.fiscal_type_fiscal = self.ref(
            "l10n_do_ncf.fiscal_type_credito_fiscal"
        )
        self.fiscal_type_consumo = self.ref("l10n_do_ncf.fiscal_type_consumo")
        self.fiscal_type_informal = self.ref("l10n_do_ncf.fiscal_type_informal")
        self.fiscal_type_cn = self.ref("l10n_do_ncf.fiscal_type_credit_note")
        self.fiscal_type_cn_purchase = self.ref(
            "l10n_do_ncf.fiscal_type_purchase_credit_note"
        )
        self.fiscal_type_dn = self.ref("l10n_do_ncf.fiscal_type_debit_note")
        self.fiscal_type_dn_purchase = self.ref(
            "l10n_do_ncf.fiscal_type_purchase_debit_note"
        )

        # Invoice lines
        # Odoo 17+: `user_type_id` (m2o) -> `account_type` (Selection).
        # 'income' sustituye a la antigua xmlid account.data_account_type_revenue.
        account_id = (
            self.env["account.account"]
            .search(
                [("account_type", "=", "income")],
                limit=1,
            )
            .id
        )

        self.invoice_line_data = [
            (
                0,
                0,
                {
                    "product_id": self.env.ref("product.product_product_1").id,
                    "quantity": 40.0,
                    "account_id": account_id,
                    "name": "product test 1",
                    "price_unit": 2.27,
                },
            ),
            (
                0,
                0,
                {
                    "product_id": self.env.ref("product.product_product_2").id,
                    "quantity": 21.0,
                    "account_id": account_id,
                    "name": "product test 2",
                    "price_unit": 2.77,
                },
            ),
            (
                0,
                0,
                {
                    "product_id": self.env.ref("product.product_product_3").id,
                    "quantity": 21.0,
                    "account_id": account_id,
                    "name": "product test 3",
                    "price_unit": 2.77,
                },
            ),
        ]
