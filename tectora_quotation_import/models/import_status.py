# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Stage names looked for when a status does not name its stage itself.
OPEN_STAGE_NAMES = ("Lopende offerte", "Offerte verzonden", "Proposition")
WON_STAGE_NAMES = ("Gewonnen", "Won")


class QuotationImportStatus(models.Model):
    """How a status of the old system lands in Odoo: the state of the order
    and the outcome (and stage) of its opportunity."""

    _name = "tectora.quotation.import.status"
    _description = "Status oud systeem (offerte-import)"
    _order = "sequence, id"

    sequence = fields.Integer(default=10)
    name = fields.Char(
        string="Status oud systeem",
        required=True,
        help="De status zoals ze in de kolom 'status' van de export staat "
        "(hoofdletters en spaties tellen niet).",
    )
    active = fields.Boolean(default=True)
    order_state = fields.Selection(
        [
            ("draft", "Offerte (concept)"),
            ("sent", "Offerte verzonden"),
            ("sale", "Bevestigde order"),
            ("cancel", "Geannuleerd"),
        ],
        string="Verkooporder",
        required=True,
        default="sent",
    )
    lead_outcome = fields.Selection(
        [("open", "Lopend"), ("won", "Gewonnen"), ("lost", "Verloren")],
        string="Verkoopkans",
        required=True,
        default="open",
    )
    stage_id = fields.Many2one(
        "crm.stage",
        string="Fase verkoopkans",
        help="Leeg: 'Lopende offerte' voor een lopende verkoopkans, de "
        "gewonnen fase ('Gewonnen') voor een gewonnen.",
    )
    create_roof_project = fields.Boolean(
        string="Dakproject en project",
        default=True,
        help="Maakt het dakproject van de offerte aan en, bij een bevestigde "
        "order, het plannebare project met zijn dashboard (zoals een "
        "bevestiging in Odoo). Uit voor afgewerkte, gefactureerde werven.",
    )
    invoiced_legacy = fields.Selection(
        [
            ("no", "Niet gefactureerd"),
            ("partial", "Deels gefactureerd"),
            ("invoiced", "Volledig gefactureerd"),
        ],
        string="Facturatie in oud systeem",
        required=True,
        default="no",
        help="Volledig gefactureerd: de order staat in Odoo als gefactureerd "
        "en verschijnt niet bij 'Te factureren' (de facturen zitten in het "
        "oude systeem). Deels: de order blijft te factureren; het resterende "
        "deel factureer je in Odoo.",
    )

    @api.constrains("order_state", "lead_outcome")
    def _check_coherent(self):
        for status in self:
            if status.order_state == "sale" and status.lead_outcome != "won":
                raise ValidationError(_(
                    "Status '%s': een bevestigde order hoort bij een gewonnen "
                    "verkoopkans.", status.name))
            if status.lead_outcome == "won" and status.order_state != "sale":
                raise ValidationError(_(
                    "Status '%s': een gewonnen verkoopkans hoort bij een "
                    "bevestigde order.", status.name))

    @api.model
    def _key(self, name):
        return " ".join((name or "").split()).lower()

    def _resolve_stage(self, team=None):
        """The stage of the opportunity for this status."""
        self.ensure_one()
        if self.stage_id:
            return self.stage_id
        Stage = self.env["crm.stage"]
        team_domain = [("team_id", "in", [team.id, False])] if team else []
        if self.lead_outcome == "won":
            for name in WON_STAGE_NAMES:
                stage = Stage.search(
                    team_domain + [("name", "=ilike", name), ("is_won", "=", True)], limit=1
                )
                if stage:
                    return stage
            return Stage.search(team_domain + [("is_won", "=", True)], limit=1)
        for name in OPEN_STAGE_NAMES:
            stage = Stage.search(
                team_domain + [("name", "=ilike", name), ("is_won", "=", False)], limit=1
            )
            if stage:
                return stage
        # Without such a stage: the last stage before the won one.
        return Stage.search(team_domain + [("is_won", "=", False)], order="sequence desc", limit=1)
