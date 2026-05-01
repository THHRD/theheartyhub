{
    'name': "Fiscal POS (Rep. Dominicana) (dev)",
    'summary': """Incorpora funcionalidades de facturación con NCF al POS.""",
    'author': "Kevin Cruz",
    'license': 'LGPL-3',
    'website': "https://github.com/odoo-dominicana",
    'category': 'Localization',
    'version': '19.0.1.0.0',
    'depends': [
        'base',
        'point_of_sale',
        'l10n_do_ncf',
        'l10n_do_ecf_pro'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/data.xml',
        'views/res_config_settings_views.xml',
        'views/pos_order_views.xml',
        'views/pos_payment_method_views.xml',
        'views/account_fiscal_type.xml',
        'views/pos_payment.xml',
        'views/ecf_modification_reason_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            #'l10n_do_pos/static/src/**/*',

            #vamos a ir depurando archivo por archivo
            #screens
            'l10n_do_pos/static/src/overrides/components/payment_screen/payment_screen.js',
            'l10n_do_pos/static/src/overrides/components/payment_screen/payment_screen.xml',
            #ticket
            'l10n_do_pos/static/src/overrides/components/ticket_screen/ticket_screen.js',
            'l10n_do_pos/static/src/overrides/components/ticket_screen/ticket_screen.xml',

            #models
            'l10n_do_pos/static/src/overrides/models/pos_store.js',
            'l10n_do_pos/static/src/overrides/models/pos_order.js',
            'l10n_do_pos/static/src/overrides/models/pos_payment.js',



            ('after', 'point_of_sale/static/src/scss/pos.scss', 'l10n_do_pos/static/src/scss/pos.scss'),
        ],
    },
    'installable': True,
}
