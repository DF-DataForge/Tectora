# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.tools import is_html_empty


class ResCompany(models.Model):
    _inherit = "res.company"

    # Next to "add as text" (the terms in the note of every quotation, order
    # and invoice) and "add a link to a web page": the terms on pages of their
    # own at the end of the PDF, in small print, with the header and footer of
    # the document layout (report/terms_report.xml).
    terms_type = fields.Selection(
        selection_add=[("pdf", "Als pdf toevoegen")],
        ondelete={"pdf": "set default"},
    )

    def _tectora_terms_pdf(self, lang=None):
        """The terms to print on their own pages after a quotation, order or
        invoice, in the language given; False when the company does not add
        its terms as a PDF or has none."""
        self.ensure_one()
        if self.terms_type != "pdf":
            return False
        if not self.env["ir.config_parameter"].sudo().get_bool("account.use_invoice_terms"):
            return False
        company = self.with_context(lang=lang) if lang else self
        terms = company.invoice_terms
        return False if is_html_empty(terms) else terms
