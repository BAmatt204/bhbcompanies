# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from odoo.tools.misc import formatLang, format_date

import logging

_logger = logging.getLogger(__name__)

class AccountMove(models.Model):
    _inherit = "account.move"

    # Modified to include credit note information on payment reciept and account.move report
    def _get_reconciled_invoices_partials(self):
        ''' Helper to retrieve the details about reconciled invoices.
        :return A list of tuple (partial, amount, invoice_line).
        '''
        self.ensure_one()
        pay_term_lines = self.line_ids\
            .filtered(lambda line: line.account_internal_type in ('receivable', 'payable'))
        invoice_partials = []
        credits = []
        refunds = []

        for partial in pay_term_lines.matched_debit_ids:
            invoice_partials.append((partial, partial.credit_amount_currency, partial.debit_move_id))
            if self.move_type == 'entry':
                invoice_partials += partial.debit_move_id.move_id._get_reconciled_invoices_partials()
            credits.append(partial.full_reconcile_id.id)
        for partial in pay_term_lines.matched_credit_ids:
            invoice_partials.append((partial, partial.debit_amount_currency, partial.credit_move_id))
            if self.move_type == 'entry':
                invoice_partials += partial.credit_move_id.move_id._get_reconciled_invoices_partials()
            refunds.append(partial.full_reconcile_id.id)

        return invoice_partials

    # Modified to include credit note information on bill report
    def _get_reconciled_info_JSON_values(self):
        self.ensure_one()

        reconciled_vals = []
        for partial, amount, counterpart_line in self._get_reconciled_invoices_partials():
            if counterpart_line.move_id.ref:
                reconciliation_ref = '%s (%s)' % (counterpart_line.move_id.name, counterpart_line.move_id.ref)
            else:
                reconciliation_ref = counterpart_line.move_id.name

            reconciled_vals.append({
                'name': counterpart_line.name,
                'journal_name': counterpart_line.journal_id.name,
                'amount': amount,
                'currency': self.currency_id.symbol,
                'digits': [69, self.currency_id.decimal_places],
                'position': self.currency_id.position,
                'date': counterpart_line.date,
                'payment_id': counterpart_line.id,
                'partial_id': partial.id,
                'account_payment_id': counterpart_line.payment_id.id,
                'payment_method_name': counterpart_line.payment_id.payment_method_id.name if counterpart_line.journal_id.type == 'bank' else None,
                'move_id': counterpart_line.move_id.id,
                'move_name': counterpart_line.move_id.name,
                'move_ref': counterpart_line.move_id.ref,
                'ref': reconciliation_ref,
            })
        return reconciled_vals