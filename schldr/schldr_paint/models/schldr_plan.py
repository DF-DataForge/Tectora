# -*- coding: utf-8 -*-
"""The plan of a painting project: the document the editor draws, the records
that mirror it, the quotation lines that follow it and the paint it takes."""
import io
import logging

from PIL import Image, ImageDraw, ImageFont

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare
from odoo.tools.binary import BinaryBytes
from odoo.tools.image import image_data_uri

from ..lib import document as plan_document
from ..lib import measure, packs
from .schldr_system import GROUP_LABELS

_logger = logging.getLogger(__name__)

SIZE_FIELDS = (
    "area_gross", "area_openings", "area_reveals", "area_net", "area_billed",
    "length", "paint_area", "height_max",
)
GROUP_TITLES = dict(GROUP_LABELS)


def _changed(record, values):
    """The values that differ from the record (sizes compared to the cm)."""
    changed = {}
    for name, value in values.items():
        current = record[name]
        if isinstance(current, models.BaseModel):
            current = current.id
        if isinstance(value, float) or isinstance(current, float):
            if float_compare(current or 0.0, value or 0.0, precision_digits=2):
                changed[name] = value
        elif (current or False) != (value or False):
            changed[name] = value
    return changed


class SchldrProject(models.Model):
    _inherit = "schldr.project"

    canvas_data = fields.Text(
        string="Plan (JSON)",
        default=lambda self: plan_document.dump(plan_document.empty_document()),
        help="Het plandocument: verdiepingen, ruimtes, muren, openingen en "
        "wat erop geschilderd wordt, in millimeters. De ruimtes, oppervlakken "
        "en offertelijnen hieronder zijn er een spiegel van.",
    )
    canvas_snapshot = fields.Binary(
        string="Plan (afbeelding)",
        attachment=True,
        help="PNG van het plan, bewaard door de editor en gebruikt op het "
        "meetblad.",
    )
    quote_grouping = fields.Selection(
        [("room", "Per ruimte"), ("system", "Per verfsysteem")],
        string="Offerte opbouwen",
        default="room",
        required=True,
        help="Per ruimte: elke ruimte is een sectie van de offerte met haar "
        "muren, plafond en houtwerk. Per verfsysteem: één lijn per systeem "
        "en kleur voor de hele woning.",
    )
    quote_notes = fields.Text(
        string="Algemene nota's",
        help="Tekst onderaan de offerte, na de werken.",
    )
    level_ids = fields.One2many("schldr.level", "project_id", string="Verdiepingen")
    room_ids = fields.One2many("schldr.room", "project_id", string="Ruimtes")
    surface_ids = fields.One2many("schldr.surface", "project_id", string="Oppervlakken")
    assignment_ids = fields.One2many(
        "schldr.assignment", "project_id", string="Verfsystemen op het plan"
    )
    line_ids = fields.One2many(
        "schldr.project.line", "project_id", string="Algemene werken", copy=True
    )
    room_count = fields.Integer(
        string="Aantal ruimtes", compute="_compute_plan_totals", store=True
    )
    total_floor_area = fields.Float(
        string="Vloeroppervlakte (m²)", compute="_compute_plan_totals", store=True,
        digits=(16, 2),
    )
    total_wall_area = fields.Float(
        string="Muren (m²)", compute="_compute_plan_totals", store=True, digits=(16, 2)
    )
    total_ceiling_area = fields.Float(
        string="Plafonds (m²)", compute="_compute_plan_totals", store=True, digits=(16, 2)
    )
    total_area = fields.Float(
        string="Muren en plafonds (m²)", compute="_compute_plan_totals", store=True,
        digits=(16, 2),
    )
    estimated_total = fields.Monetary(
        string="Geschat totaal (excl. btw)",
        compute="_compute_estimated_total",
        currency_field="currency_id",
        help="De werkposten aan catalogusprijs; de offerte rekent met de "
        "prijslijst van de klant.",
    )

    @api.depends("room_ids.floor_area", "room_ids.wall_area", "room_ids.ceiling_area")
    def _compute_plan_totals(self):
        for project in self:
            rooms = project.room_ids
            project.room_count = len(rooms)
            project.total_floor_area = sum(rooms.mapped("floor_area"))
            project.total_wall_area = sum(rooms.mapped("wall_area"))
            project.total_ceiling_area = sum(rooms.mapped("ceiling_area"))
            project.total_area = project.total_wall_area + project.total_ceiling_area

    @api.depends(
        "assignment_ids.quantity", "assignment_ids.system_id.product_id.lst_price",
        "line_ids.price_subtotal",
    )
    def _compute_estimated_total(self):
        for project in self:
            project.estimated_total = sum(
                assignment.quantity * assignment.system_id.product_id.lst_price
                for assignment in project.assignment_ids
            ) + sum(project.line_ids.mapped("price_subtotal"))

    # ------------------------------------------------------------- document
    def _schldr_document(self):
        """The plan document of this project, complete and clean."""
        self.ensure_one()
        try:
            return plan_document.load(self.canvas_data)
        except plan_document.DocumentError as error:
            raise UserError(_("Het plan kan niet gelezen worden: %s", error))

    @api.model
    def schldr_get_plan_options(self):
        """What the editor offers: the paint systems, colours and standard
        elements, and how the company measures."""
        company = self.env.company
        systems = self.env["schldr.paint.system"].search(
            [("company_id", "in", [False, company.id])]
        )
        colours = self.env["schldr.colour"].search([])
        types = self.env["schldr.element.type"].search([])
        currency = company.currency_id
        products = systems.layer_ids.product_id
        return {
            "products": {
                product.id: {
                    "name": product.display_name,
                    "uom": product.uom_id.name or "",
                    "packs": [
                        [size.volume, size.price]
                        for size in product.product_tmpl_id.schldr_pack_size_ids
                    ],
                }
                for product in products
            },
            "systems": [
                {
                    "id": system.id,
                    "name": system.name,
                    "groups": system.groups(),
                    "measure": system.sale_measure,
                    "price": system.product_id.lst_price,
                    "hours": system.prep_hours + system.paint_hours,
                    "layers": system._schldr_recipe()[system.id]["layers"],
                }
                for system in systems
            ],
            "colours": [
                {
                    "id": colour.id,
                    "name": colour.display_name,
                    "hex": colour.hex or "#FFFFFF",
                }
                for colour in colours
            ],
            "element_types": [element._schldr_preset() for element in types],
            "groups": GROUP_LABELS,
            "deduct_min_area": company.schldr_deduct_min_area,
            "currency": {"symbol": currency.symbol, "position": currency.position},
        }

    # ----------------------------------------------------------------- sync
    def action_sync_from_canvas(self):
        """Bring the records in line with the plan document: levels, rooms,
        surfaces and their paint systems, matched on their id in the document
        and only written when something changed. Then the quotation follows,
        if it is set to."""
        for project in self:
            doc = project._schldr_document()
            result = measure.measure_document(
                doc, project.company_id.schldr_deduct_min_area
            )
            assigned = measure.assignments(doc, result["surfaces"])
            project._schldr_write_plan(doc, result, assigned)
            project._schldr_store_snapshot()
            if project.state == "draft" and result["surfaces"]:
                project.with_context(schldr_sync=True).state = "measured"
        self._schldr_mirror_to_order()
        return True

    def _schldr_write_plan(self, doc, result, assigned):
        self.ensure_one()
        Level = self.env["schldr.level"]
        Room = self.env["schldr.room"]
        Surface = self.env["schldr.surface"]

        def upsert(model, existing, reference, values):
            record = existing.pop(reference, None)
            if record:
                changed = _changed(record, values)
                if changed:
                    record.write(changed)
                return record
            return model.create(dict(values, project_id=self.id, canvas_ref=reference))

        levels = {level.canvas_ref: level for level in self.level_ids}
        level_by_ref = {}
        for sequence, level in enumerate(doc["levels"], 1):
            level_by_ref[level["id"]] = upsert(Level, levels, level["id"], {
                "name": level["name"] or _("Verdieping %s", sequence),
                "sequence": sequence * 10,
            })

        rooms = {room.canvas_ref: room for room in self.room_ids}
        room_by_ref = {}
        for sequence, room in enumerate(result["rooms"], 1):
            room_by_ref[room["ref"]] = upsert(Room, rooms, room["ref"], {
                "name": room["name"] or _("Ruimte %s", sequence),
                "sequence": sequence * 10,
                "level_id": level_by_ref[room["level"]].id,
                "height": room["height"],
                "floor_area": room["floor_area"],
                "perimeter": room["perimeter"],
                "wall_area": room["wall_area"],
                "ceiling_area": room["ceiling_area"],
            })

        surfaces = {surface.canvas_ref: surface for surface in self.surface_ids}
        surface_by_ref = {}
        for sequence, surface in enumerate(result["surfaces"], 1):
            values = {name: surface[name] for name in SIZE_FIELDS}
            values.update({
                "name": surface["name"],
                "kind": surface["kind"],
                "group": surface["group"],
                "count": surface["count"],
                "sequence": sequence * 10,
                "room_id": room_by_ref[surface["room"]].id,
            })
            surface_by_ref[surface["ref"]] = upsert(Surface, surfaces, surface["ref"], values)

        # What is no longer on the plan goes, with what hangs under it.
        for stale in (surfaces, rooms, levels):
            for record in stale.values():
                record.unlink()

        self._schldr_write_assignments(surface_by_ref, assigned)

    def _schldr_write_assignments(self, surface_by_ref, assigned):
        """The paint systems per surface. A system or colour the document
        names but that no longer exists is left out, and said so."""
        self.ensure_one()
        Assignment = self.env["schldr.assignment"]
        system_ids = {entry["system"] for entries in assigned.values() for entry in entries}
        colour_ids = {
            entry["colour"] for entries in assigned.values() for entry in entries
            if entry["colour"]
        }
        systems = self.env["schldr.paint.system"].with_context(active_test=False).search(
            [("id", "in", list(system_ids))]
        )
        colours = self.env["schldr.colour"].with_context(active_test=False).search(
            [("id", "in", list(colour_ids))]
        )
        known_systems = set(systems.ids)
        known_colours = set(colours.ids)
        missing = (system_ids - known_systems) or (colour_ids - known_colours)

        for reference, surface in surface_by_ref.items():
            wanted = [
                (entry["system"], entry["colour"] if entry["colour"] in known_colours else False)
                for entry in assigned.get(reference, [])
                if entry["system"] in known_systems
            ]
            current = surface.assignment_ids.sorted(lambda a: (a.sequence, a.id))
            for index, (system_id, colour_id) in enumerate(wanted):
                values = {
                    "system_id": system_id,
                    "colour_id": colour_id,
                    "sequence": (index + 1) * 10,
                }
                if index < len(current):
                    changed = _changed(current[index], values)
                    if changed:
                        current[index].write(changed)
                else:
                    Assignment.create(dict(values, surface_id=surface.id))
            current[len(wanted):].unlink()
        if missing:
            self.message_post(body=_(
                "Het plan verwijst naar een verfsysteem of kleur die niet meer "
                "bestaat; die toewijzing is weggelaten."
            ))

    # ------------------------------------------------------------ quotation
    def _schldr_line_name(self, group, system, colour):
        parts = ["%s – %s" % (GROUP_TITLES.get(group, group), system.name)]
        if system.description:
            parts.append(system.description)
        if colour:
            parts.append(_("Kleur: %s", colour.display_name))
        return "\n".join(parts)

    def _schldr_quote_entries(self):
        """The lines the plan puts on a quotation, in order. Each has a key
        that stays the same as long as it is about the same thing, so the
        line on the quotation is updated instead of replaced."""
        self.ensure_one()
        entries = []

        def section(key, title):
            entries.append({
                "key": "section:%s" % key,
                "values": {"display_type": "line_section", "name": title},
            })

        if self.line_ids:
            section("general", _("ALGEMENE WERKEN"))
            for line in self.line_ids:
                entries.append({
                    "key": "line:%s" % line.id,
                    "values": {"product_id": line.product_id.id, "schldr_line_id": line.id},
                    "quantity": line.quantity,
                })

        def grouped(assignments):
            totals = {}
            for assignment in assignments:
                key = (assignment.group, assignment.system_id, assignment.colour_id)
                totals[key] = totals.get(key, 0.0) + assignment.quantity
            order = [group for group, _label in GROUP_LABELS]
            return sorted(
                totals.items(),
                key=lambda item: (order.index(item[0][0]), item[0][1].sequence, item[0][1].id, item[0][2].id),
            )

        def works(prefix, assignments):
            for (group, system, colour), quantity in grouped(assignments):
                entries.append({
                    "key": "%s|%s|%s|%s" % (prefix, group, system.id, colour.id or 0),
                    "values": {
                        "product_id": system.product_id.id,
                        "name": self._schldr_line_name(group, system, colour),
                        "schldr_colour_id": colour.id or False,
                    },
                    "quantity": round(quantity, 2),
                })

        if self.quote_grouping == "system":
            if self.assignment_ids:
                section("works", _("SCHILDERWERKEN"))
                works("works", self.assignment_ids)
        else:
            for room in self.room_ids:
                assignments = self.assignment_ids.filtered(lambda a: a.room_id == room)
                if not assignments:
                    continue
                section("room:%s" % room.canvas_ref, room._schldr_title().upper())
                works("room:%s" % room.canvas_ref, assignments)

        notes = (self.quote_notes or "").strip()
        if notes:
            section("notes", _("ALGEMENE NOTA'S"))
            entries.append({
                "key": "notes",
                "values": {"display_type": "line_note", "name": notes},
            })
        return entries

    def _schldr_mirror_to_order(self, order=None):
        """Plan -> open quotation.

        Only for a quotation that follows the measurement ("Offerte volgt de
        meting"), or when the user asked for it ("Offerte maken" / "Offerte
        bijwerken uit meting", context ``schldr_update_from_measurement``):
        a quotation is never changed by the plan behind the user's back.

        Every line the plan gives has a key. A line that is on the quotation
        already keeps its price, discount and taxes and only gets its new
        quantity; a new one is added in its place; one the plan no longer
        gives is removed. Lines the user added stay where they are, after
        the plan line they followed.
        """
        Line = self.env["sale.order.line"].with_context(schldr_sync=True)
        for project in self:
            target = order or project.sale_order_id
            if not target or target.state not in ("draft", "sent"):
                continue
            if target.schldr_locked:
                continue  # Zet offerte vast: the plan keeps off it.
            if not (
                target.schldr_follow_measurement
                or self.env.context.get("schldr_update_from_measurement")
            ):
                continue
            entries = project._schldr_quote_entries()
            wanted = {entry["key"] for entry in entries}

            by_key = {}
            followers = {}
            surplus = Line
            anchor = None
            for line in target.order_line.sorted(lambda l: (l.sequence, l.id)):
                key = line.schldr_line_key
                if not key:
                    followers.setdefault(anchor, []).append(line)
                elif key in by_key or key not in wanted:
                    surplus |= line
                else:
                    by_key[key] = line
                    anchor = key
            if surplus:
                surplus.unlink()

            final = list(followers.get(None, []))
            for entry in entries:
                line = by_key.get(entry["key"])
                values = dict(entry["values"])
                if line:
                    changed = {}
                    if "quantity" in entry and float_compare(
                        line.product_uom_qty, entry["quantity"], precision_digits=2
                    ):
                        changed["product_uom_qty"] = entry["quantity"]
                    if line.display_type and line.name != values["name"]:
                        changed["name"] = values["name"]
                    if not line.display_type and line.product_id.id != values["product_id"]:
                        changed["product_id"] = values["product_id"]
                    if changed:
                        line.with_context(schldr_sync=True).write(changed)
                else:
                    values.update({
                        "order_id": target.id,
                        "schldr_line_key": entry["key"],
                        "schldr_measurement_line": True,
                        "sequence": 100000,
                    })
                    if "quantity" in entry:
                        values["product_uom_qty"] = entry["quantity"]
                    line = Line.create(values)
                final.append(line)
                final.extend(followers.get(entry["key"], []))
            for index, line in enumerate(final, start=1):
                if line.sequence != index * 10:
                    line.with_context(schldr_sync=True).write({"sequence": index * 10})
        return True

    # ------------------------------------------------------------- materials
    def _schldr_plan_material_values(self, order):
        """Material requirement values for the paint of the plan: per product
        and colour what the layers of the assigned systems take, rounded up
        to the pots it comes in."""
        self.ensure_one()
        surfaces = [surface._schldr_sizes() for surface in self.surface_ids]
        assigned = {}
        for assignment in self.assignment_ids.sorted(lambda a: (a.sequence, a.id)):
            assigned.setdefault(assignment.surface_id.canvas_ref, []).append({
                "system": assignment.system_id.id,
                "colour": assignment.colour_id.id or False,
            })
        systems = self.assignment_ids.system_id
        needs = measure.material_needs(surfaces, assigned, systems._schldr_recipe())
        Product = self.env["product.product"]
        Colour = self.env["schldr.colour"]
        values = []
        for (product_id, colour_id), need in sorted(
            needs.items(), key=lambda item: (item[0][0], item[0][1] or 0)
        ):
            if need <= 1e-6:
                continue
            product = Product.browse(product_id)
            sizes = [
                (size.volume, size.price)
                for size in product.product_tmpl_id.schldr_pack_size_ids
            ]
            chosen = packs.choose_packs(need, sizes)
            quantity = packs.packed_volume(chosen) if chosen else round(need + 0.004999, 2)
            values.append({
                "project_id": self.id,
                "product_id": product.id,
                "product_uom_id": product.uom_id.id,
                "colour_id": Colour.browse(colour_id).id if colour_id else False,
                "quantity_needed": round(need, 2),
                "quantity": quantity,
                "pack_summary": packs.describe(chosen, product.uom_id.name or "") if chosen else False,
                "sale_order_id": order.id if order else False,
            })
        return values

    # ----------------------------------------------------------------- image
    def _get_drawing_png(self, level_ref=None):
        """PNG of the plan (of one level) for the measurement sheet, as raw
        bytes. Never raises: without a plan the sheet prints without image."""
        self.ensure_one()
        try:
            return self._schldr_render_plan_png(level_ref)
        except Exception:
            _logger.exception("Could not render the plan of %s", self.code)
            return False

    def _get_drawing_data_uri(self, level_ref=None):
        self.ensure_one()
        png = self._get_drawing_png(level_ref)
        return image_data_uri(png) if png else False

    def _schldr_store_snapshot(self):
        """Keep an image of the plan (its first level with rooms) on the
        record, for the project dashboard."""
        self.ensure_one()
        png = self._get_drawing_png()
        snapshot = BinaryBytes(png) if png else False
        if snapshot or self.canvas_snapshot:
            self.with_context(schldr_sync=True).canvas_snapshot = snapshot

    def _schldr_plans(self):
        """The plan per level that has rooms, for the measurement sheet and
        the customer portal: its title (empty with one level), its image
        and its rooms with their totals."""
        self.ensure_one()
        plans = []
        for level in self.level_ids:
            rooms = level.room_ids
            if not rooms:
                continue
            plans.append({
                "title": level.name if len(self.level_ids) > 1 else "",
                "image": self._get_drawing_data_uri(level.canvas_ref),
                "rooms": rooms,
                "floor_area": sum(rooms.mapped("floor_area")),
                "wall_area": sum(rooms.mapped("wall_area")),
                "ceiling_area": sum(rooms.mapped("ceiling_area")),
            })
        return plans

    def _schldr_render_plan_png(self, level_ref=None, width=1600):
        """A plain plan: every room with its name and floor area, doors and
        windows as gaps in the wall."""
        self.ensure_one()
        doc = self._schldr_document()
        levels = [
            level for level in doc["levels"]
            if (not level_ref or level["id"] == level_ref) and level["rooms"]
        ]
        if not levels:
            return False
        level = levels[0]
        points = [point for room in level["rooms"] for point in room["points"]]
        if len(points) < 3:
            return False
        min_x = min(p[0] for p in points)
        min_y = min(p[1] for p in points)
        span_x = max(max(p[0] for p in points) - min_x, 1)
        span_y = max(max(p[1] for p in points) - min_y, 1)
        margin = 60
        scale = (width - 2 * margin) / float(span_x)
        height = int(span_y * scale) + 2 * margin
        if height > 2200:
            scale = (2200 - 2 * margin) / float(span_y)
            height = 2200

        def place(point):
            return (margin + (point[0] - min_x) * scale, margin + (point[1] - min_y) * scale)

        image = Image.new("RGB", (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default(size=22)
        except TypeError:  # Pillow < 10.1 has no size parameter
            font = ImageFont.load_default()
        gap = {"door": (255, 255, 255), "passage": (255, 255, 255), "window": (120, 170, 220)}
        for room in level["rooms"]:
            if len(room["points"]) < 3:
                continue
            outline = [place(point) for point in room["points"]]
            draw.polygon(outline, fill=(240, 244, 248))
            count = len(outline)
            for index, wall in enumerate(room["walls"]):
                start, end = outline[index], outline[(index + 1) % count]
                if wall["virtual"]:
                    continue
                draw.line([start, end], fill=(40, 52, 64), width=5)
                length = max(
                    ((room["points"][(index + 1) % count][0] - room["points"][index][0]) ** 2
                     + (room["points"][(index + 1) % count][1] - room["points"][index][1]) ** 2) ** 0.5,
                    1.0,
                )
                for opening in room["openings"]:
                    if opening["wall"] != wall["id"] or opening["kind"] not in gap:
                        continue
                    first = min(opening["offset"] / length, 1.0)
                    last = min((opening["offset"] + opening["width"]) / length, 1.0)
                    draw.line(
                        [
                            (start[0] + (end[0] - start[0]) * first, start[1] + (end[1] - start[1]) * first),
                            (start[0] + (end[0] - start[0]) * last, start[1] + (end[1] - start[1]) * last),
                        ],
                        fill=gap[opening["kind"]], width=5,
                    )
            metres = [(x * measure.MM, y * measure.MM) for x, y in room["points"]]
            centre = place(tuple(c / measure.MM for c in measure.geometry.centroid(metres)))
            label = "%s\n%.1f m²" % (room["name"] or "", measure.geometry.area(metres))
            draw.multiline_text(
                centre, label.strip(), fill=(20, 30, 40), font=font, anchor="mm", align="center"
            )
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
