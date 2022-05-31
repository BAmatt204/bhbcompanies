# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError, RedirectWarning
from odoo.tools.misc import formatLang, format_date
import logging
INV_LINES_PER_STUB = 9
_logger = logging.getLogger(__name__)
class AccountPayment(models.Model):
    _inherit = "account.payment"
    # Modified to allow credit to show on printed check document
    def _check_make_stub_pages(self):
        """ The stub is the summary of paid invoices. It may spill on several pages, in which case only the check on
            first page is valid. This function returns a list of stub lines per page.
        """
        self.ensure_one()
        def prepare_vals(invoice, partials):
            number = ' - '.join([invoice.name, invoice.ref] if invoice.ref else [invoice.name])
            if invoice.is_outbound():
                invoice_sign = 1
                partial_field = 'debit_amount_currency'
            else:
                invoice_sign = -1
                partial_field = 'credit_amount_currency'
            if invoice.currency_id.is_zero(invoice.amount_residual):
                amount_residual_str = '-'
            else:
                amount_residual_str = formatLang(self.env, invoice_sign * invoice.amount_residual, currency_obj=invoice.currency_id)
            return {
                'due_date': format_date(self.env, invoice.invoice_date_due),
                'number': number,
                'amount_total': formatLang(self.env, invoice_sign * invoice.amount_total, currency_obj=invoice.currency_id),
                'amount_residual': amount_residual_str,
                'amount_paid': formatLang(self.env, invoice_sign * sum(partials.mapped(partial_field)), currency_obj=self.currency_id),
                'currency': invoice.currency_id,
            }
        # Decode the reconciliation to keep only invoices.
        term_lines = self.line_ids.filtered(lambda line: line.account_id.internal_type in ('receivable', 'payable'))
        invoices = (term_lines.matched_debit_ids.debit_move_id.move_id + term_lines.matched_credit_ids.credit_move_id.move_id)\
            .filtered(lambda x: x.is_outbound())
        credits = self.env['account.move']
        amount_map = {}
        for inv in invoices:
            for partial, amount, counterpart_line in inv._get_reconciled_invoices_partials():
                credits += counterpart_line.move_id
                amount_map[counterpart_line.move_id] = amount
        invoices += credits
        invoices = invoices.sorted(lambda x: x.invoice_date_due or x.date)
        # Group partials by invoices.
        invoice_map = {invoice: self.env['account.partial.reconcile'] for invoice in invoices}
        for partial in term_lines.matched_debit_ids:
            invoice = partial.debit_move_id.move_id
            if invoice in invoice_map:
                invoice_map[invoice] |= partial
        for partial in term_lines.matched_credit_ids:
            invoice = partial.credit_move_id.move_id
            if invoice in invoice_map:
                invoice_map[invoice] |= partial

        # Prepare stub_lines.
        if 'out_refund' in invoices.mapped('move_type'):
            stub_lines = [{'header': True, 'name': "Bills"}]
            stub_lines += [prepare_vals(invoice, partials)
                           for invoice, partials in invoice_map.items()
                           if invoice.move_type == 'in_invoice']
            stub_lines += [prepare_vals(invoice, partials)
                           for invoice, partials in invoice_map.items()
                           if invoice.move_type == 'out_invoice']
            stub_lines += [{'header': True, 'name': "Refund"}]
            stub_lines += [prepare_vals(invoice, partials)
                           for invoice, partials in invoice_map.items()
                           if invoice.move_type == 'out_refund']
        else:
            stub_lines = [prepare_vals(invoice, partials)
                          for invoice, partials in invoice_map.items()
                          if invoice.move_type == 'in_invoice']
            if 'in_refund' in invoices.mapped('move_type'):
                # Add Credit Notes to stub_lines
                stub_lines += [{'header': True, 'name': "Credit Summary"}]
                for invoice, partials in invoice_map.items():
                    if invoice.move_type == 'in_refund' and invoice.state == 'posted':
                        amount = amount_map[invoice]
                        stub_line = prepare_vals(invoice, partials)
                        stub_line['amount_paid'] = formatLang(self.env, -amount, currency_obj=self.currency_id)
                        stub_lines += [stub_line]
        # Crop the stub lines or split them on multiple pages
        if not self.company_id.account_check_printing_multi_stub:
            # If we need to crop the stub, leave place for an ellipsis line
            num_stub_lines = len(stub_lines) > INV_LINES_PER_STUB and INV_LINES_PER_STUB - 1 or INV_LINES_PER_STUB
            stub_pages = [stub_lines[:num_stub_lines]]
        else:
            stub_pages = []
            i = 0
            while i < len(stub_lines):
                # Make sure we don't start the credit section at the end of a page
                if len(stub_lines) >= i + INV_LINES_PER_STUB and stub_lines[i + INV_LINES_PER_STUB - 1].get('header'):
                    num_stub_lines = INV_LINES_PER_STUB - 1 or INV_LINES_PER_STUB
                else:
                    num_stub_lines = INV_LINES_PER_STUB
                stub_pages.append(stub_lines[i:i + num_stub_lines])
                i += num_stub_lines
        return stub_pages
    # Modified to add credit notes to list view of paid invoices
    @api.depends('move_id.line_ids.matched_debit_ids', 'move_id.line_ids.matched_credit_ids')
    def _compute_stat_buttons_from_reconciliation(self):
        ''' Retrieve the invoices reconciled to the payments through the reconciliation (account.partial.reconcile). '''
        stored_payments = self.filtered('id')
        if not stored_payments:
            self.reconciled_invoice_ids = False
            self.reconciled_invoices_count = 0
            self.reconciled_invoices_type = ''
            self.reconciled_bill_ids = False
            self.reconciled_bills_count = 0
            self.reconciled_statement_ids = False
            self.reconciled_statements_count = 0
            return
        self.env['account.move'].flush()
        self.env['account.move.line'].flush()
        self.env['account.partial.reconcile'].flush()
        self._cr.execute('''
            SELECT
                payment.id,
                ARRAY_AGG(DISTINCT invoice.id) AS invoice_ids,
                invoice.move_type
            FROM account_payment payment
            JOIN account_move move ON move.id = payment.move_id
            JOIN account_move_line line ON line.move_id = move.id
            JOIN account_partial_reconcile part ON
                part.debit_move_id = line.id
                OR
                part.credit_move_id = line.id
            JOIN account_move_line counterpart_line ON
                part.debit_move_id = counterpart_line.id
                OR
                part.credit_move_id = counterpart_line.id
            JOIN account_move invoice ON invoice.id = counterpart_line.move_id
            JOIN account_account account ON account.id = line.account_id
            WHERE account.internal_type IN ('receivable', 'payable')
                AND payment.id IN %(payment_ids)s
                AND line.id != counterpart_line.id
                AND invoice.move_type in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund', 'out_receipt', 'in_receipt')
            GROUP BY payment.id, invoice.move_type
        ''', {
            'payment_ids': tuple(stored_payments.ids)
        })
        query_res = self._cr.dictfetchall()
        self.reconciled_invoice_ids = self.reconciled_invoices_count = False
        self.reconciled_bill_ids = self.reconciled_bills_count = False
        for res in query_res:
            pay = self.browse(res['id'])
            if res['move_type'] in self.env['account.move'].get_sale_types(True):
                invoices = self.env['account.move']
                # Instead of browse, search through moves to get specific invoices and associated credit notes
                pay.reconciled_invoice_ids += self.env['account.move'].browse(res.get('invoice_ids', []))
                for invoice in pay.reconciled_invoice_ids:
                    for partial, amount, counterpart_line in invoice._get_reconciled_invoices_partials():
                        if counterpart_line.move_id and counterpart_line.move_id.move_type == 'out_refund':
                            invoices += counterpart_line.move_id
                pay.reconciled_invoice_ids += invoices 
                pay.reconciled_invoices_count = len(pay.reconciled_invoice_ids)
            else:
                bills = self.env['account.move']
                # Instead of browse, search through moves to get specific invoices and associated credit notes
                pay.reconciled_bill_ids += self.env['account.move'].browse(res.get('invoice_ids', []))
                for bill in pay.reconciled_bill_ids:
                    for partial, amount, counterpart_line in bill._get_reconciled_invoices_partials():
                        if counterpart_line.move_id and counterpart_line.move_id.move_type == 'in_refund':
                            bills += counterpart_line.move_id
                pay.reconciled_bill_ids += bills 
                pay.reconciled_bills_count = len(pay.reconciled_bill_ids)
        self._cr.execute('''
            SELECT
                payment.id,
                ARRAY_AGG(DISTINCT counterpart_line.statement_id) AS statement_ids
            FROM account_payment payment
            JOIN account_move move ON move.id = payment.move_id
            JOIN account_journal journal ON journal.id = move.journal_id
            JOIN account_move_line line ON line.move_id = move.id
            JOIN account_account account ON account.id = line.account_id
            JOIN account_partial_reconcile part ON
                part.debit_move_id = line.id
                OR
                part.credit_move_id = line.id
            JOIN account_move_line counterpart_line ON
                part.debit_move_id = counterpart_line.id
                OR
                part.credit_move_id = counterpart_line.id
            WHERE account.id = payment.outstanding_account_id
                AND payment.id IN %(payment_ids)s
                AND line.id != counterpart_line.id
                AND counterpart_line.statement_id IS NOT NULL
            GROUP BY payment.id
        ''', {
            'payment_ids': tuple(stored_payments.ids)
        })
        query_res = dict((payment_id, statement_ids) for payment_id, statement_ids in self._cr.fetchall())
        for pay in self:
            statement_ids = query_res.get(pay.id, [])
            pay.reconciled_statement_ids = [(6, 0, statement_ids)]
            pay.reconciled_statements_count = len(statement_ids)
            if len(pay.reconciled_invoice_ids.mapped('move_type')) == 1 and pay.reconciled_invoice_ids[0].move_type == 'out_refund':
                pay.reconciled_invoices_type = 'credit_note'
            else:
                pay.reconciled_invoices_type = 'invoice'