{
    "name": "NCF Management",
    "summary": """
        This module implements the administration and management of fiscal
        receipt numbers for compliance with norm 06-18 of the Dominican
        Republic Internal Revenue Service.
    """,
    "author": "Marcos, Guavana, Indexa, Iterativo SRL, Neotec, Jenrax SRL",
    "license": "LGPL-3",
    'website': "https://github.com/Jenrax-git/l10n-do",
    "category": "Localization",
    'countries': ['do'],
    "version": "19.0.2.2.9",
    # any module necessary for this one to work correctly
    "depends": [
        "base",
        "web",
        "account",
        "l10n_do",
    ],
    # always loaded
    "data": [
        "data/ir_config_parameters.xml",
        "data/ir_cron_data.xml",
        "data/account_fiscal_type_data.xml",
        # "data/report_layout_data.xml",
        "data/mail_template_data.xml",
        "data/update_sequences.xml",

        "security/ir_rule.xml",
        "security/ir.model.access.csv",
        "security/res_groups.xml",

        "wizard/account_fiscal_sequence_validate_wizard_views.xml",
        "wizard/account_move_reversal_views.xml",

        # "views/account_report.xml",
        "views/account_move_views.xml",
        "views/account_journal_views.xml",
        "views/res_partner_views.xml",
        "views/account_fiscal_sequence_views.xml",
        'views/res_company_views.xml',
        'views/account_move_cancel_views.xml',
        # "views/backend_js.xml",

        "views/report_templates.xml",
        "views/report_invoice.xml",
        "views/layouts.xml",
    ],
    # only loaded in demonstration mode
    "demo": [
        "demo/res_partner_demo.xml",
        "demo/account_fiscal_sequence_demo.xml",
    ],
}
