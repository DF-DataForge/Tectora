# -*- coding: utf-8 -*-
from odoo import models

# What the letterhead prints on the right of its band when the company has no
# tagline (Settings -> Configure Document Layout -> Company Tagline).
LETTERHEAD_SERVICES = "EPDM - roofing - isolatie - onderhoud - herstellingen"


def _group_by_four(number):
    """An IBAN typed without spaces, printed in groups of four."""
    if not number or " " in number:
        return number
    return " ".join(number[i:i + 4] for i in range(0, len(number), 4))


class ResCompany(models.Model):
    _inherit = "res.company"

    def _tectora_letterhead_services(self):
        """The services on the right of the letterhead band, when the company
        has no tagline of its own."""
        return LETTERHEAD_SERVICES

    def _tectora_letterhead_vat(self):
        """The VAT number as the letterhead prints it: BE 1031.956.670."""
        self.ensure_one()
        vat = (self.vat or "").replace(" ", "").replace(".", "")
        if vat[:2].upper() == "BE" and len(vat) == 12 and vat[2:].isdigit():
            return "BE %s.%s.%s" % (vat[2:6], vat[6:9], vat[9:])
        return self.vat or ""

    def _tectora_letterhead_website(self):
        """The website without its scheme: www.tectora.be."""
        self.ensure_one()
        website = (self.website or "").strip()
        for scheme in ("https://", "http://"):
            if website.startswith(scheme):
                website = website[len(scheme):]
        return website.rstrip("/")

    def _tectora_letterhead_footer_lines(self):
        """The three lines of the letterhead footer, from the company data.

        The first names the company: name, address and VAT number. The second
        is the footer text of the document layout when there is one (on the
        letterhead: the office and workshop address with email and phone),
        otherwise the company's email and phone. The third lists the bank
        accounts. Empty lines are left out.
        """
        self.ensure_one()
        place = " ".join(part for part in (self.zip, self.city) if part)
        address = ", ".join(part for part in (self.street, place) if part)
        identity = [self.name, address, self._tectora_letterhead_vat()]
        contact = [self.email, self.phone]
        banks = [
            " ".join(part for part in (bank.bank_name, _group_by_four(bank.account_number)) if part)
            for bank in self.bank_ids
        ]
        return {
            "identity": " — ".join(part for part in identity if part),
            "contact": " — ".join(part for part in contact if part),
            "banks": " — ".join(part for part in banks if part),
        }
