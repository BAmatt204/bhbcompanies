# -*- coding: utf-8 -*-
{
    'name': "Better Air Mfg: Credit note details on check, payment report",

    'summary': """
        Allow credit notes to appear on several types of reports""",

    'description': """
        Task ID: 2611352
        1)Update the check format (from the payment)
        Include all the credit notes from all the bills attached to the payment in the check report
        One check is paying 3 bills (BILL/xxx, BILL/xxx, ). One bill has one credit note associated, hence the check report should have  an extra  line for  the credit note (RBILL) information
        2) ) Update the payment receipt format (from the payment) In the payment receipt pdf report, check all the bills attached in the payment with the credit note. Include all the credit notes information into the pdf report.
        3) Update the bill, invoice format
        On the bill, all the paid on information is including payment and refund. Add payment information details to the bill pdf report. Currently shows only ‘paid on date with amount’. For the bank payment, add BNK/xxx/ information, for the credit note add ‘credit note, RBILL/xxxx/ (xxxx bill reference)’
        4) Update the refund, invoice formatOn the refund, all the paid on with the payment info is applied to multiple bills. In the refund pdf report, add payment info details (BILL/xxx/ (xxx))to the pdf report on each record respectively. Currently, each record shows only ‘paid on date and amount’.
    """,

    'author': "Odoo Inc.",
    'website': "http://www.odoo.com",
    'category': 'Customizations/Studio',
    'license': 'OEEL-1',
    'version': '0.1',
    'depends': ['account_accountant', 'account_check_printing', 'account', 'l10n_us_check_printing'],
    'data': [
        'views/report_invoice.xml',
        'views/report_payment_receipt_templates.xml',
        'views/assets.xml',
    ],
}
