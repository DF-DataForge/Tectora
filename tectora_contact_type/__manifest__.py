# -*- coding: utf-8 -*-
{
    "name": "Data Forge Dakmeting — Contacttype",
    "summary": "Deelt de contacten in: particulieren, energiehuizen, "
    "bouwondernemingen, architecten, syndici, niet-particulieren, steden en gemeentes",
    "description": """
Data Forge Dakmeting — Contacttype
==================================
A Contacttype on every contact (Contacts): Particulieren, Energiehuizen,
Bouwonderneming, Architect, Syndicus, Niet particulieren, Steden en
gemeentes. It sits above the tags on the contact form, is a column of the
contact list, and can be searched and grouped on. Changes are tracked in the
chatter.

A module of its own, installed by hand: a field on ``res.partner`` is read on
every request, so a deploy that served it without the database column took
the whole instance down before (DF-DataForge/Tectora#55). Until this module
is installed its code does nothing; installing it adds the column and the
views in one go, and the other Tectora modules never touch the contacts.
    """,
    "version": "20.0.1.0.0",
    "category": "Sales",
    "license": "Other proprietary",
    "author": "Data Forge",
    "website": "https://www.data-forge.be",
    "depends": ["contacts"],
    "data": [
        "views/res_partner_views.xml",
    ],
    # Installed by hand (see the description): never as a side effect of a
    # deploy or of another module's upgrade.
    "auto_install": False,
    "installable": True,
}
