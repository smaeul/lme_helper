#!/usr/bin/env python3
#
# Copyright © 2021 Samuel Holland <samuel@sholland.org>
# SPDX-License-Identifier: BSD-2-Clause
#

import re
import sys
import wikitextparser as wtp
import xml.etree.ElementTree as ET

from enum import IntEnum
from peewee import *

db = SqliteDatabase(None)


class IntEnumField(IntegerField):
    def __init__(self, enum: IntEnum, *args, **kwargs):
        self.__enum = enum
        super().__init__(self, *args, **kwargs)

    def db_value(self, python_value):
        if not isinstance(python_value, self.__enum):
            raise TypeError(f'{python_value!r} is not a {__enum.__name__}')
        return super().adapt(python_value.value)

    def python_value(self, db_value):
        return self.__enum(db_value)


class BaseModel(Model):
    class Meta:
        database = db


class Category(BaseModel):
    name = TextField(unique=True)
    page = TextField(null=True)


class Feature(BaseModel):
    category = ForeignKeyField(Category)
    name = TextField(unique=True)
    page = TextField(null=True)


class Chip(BaseModel):
    order = IntegerField(null=True)


class ChipInfoKind(IntEnum):
    INTERNAL    = 1
    MARKETING   = 2


class ChipInfo(BaseModel):
    chip = ForeignKeyField(Chip)
    kind = IntEnumField(ChipInfoKind)
    name = TextField(unique=True)
    page = TextField(null=True)


class SupportLevel(IntEnum):
    UNAVAILABLE = 1
    UNKNOWN     = 2
    UNPLANNED   = 3
    UNSUPPORTED = 4
    WIP         = 5
    COMPATIBLE  = 6
    SUPPORTED   = 7


class Status(BaseModel):
    chip = ForeignKeyField(Chip)
    feature = ForeignKeyField(Feature)
    support = IntEnumField(SupportLevel)
    note = TextField(null=True)
    page = TextField(null=True)
    symbol = TextField(null=True)
    version = TextField(null=True)


def parse_cell(cell):
    # Exclude tags from the cell contents
    # This is ugly, but there is no method to get the top-level text span
    # It also works around cell attributes being included in cell.plain_text()
    wikitext = cell.value
    for tag in cell.get_tags():
        wikitext = wikitext.replace(tag.string, '')
    cell = wtp.parse(wikitext)
    text = cell.plain_text()
    if cell.wikilinks:
        link = cell.wikilinks[0]
        text = link.text or link.title
        page = link.target
    elif cell.external_links:
        page = cell.external_links[0].url
    else:
        page = None
    return text.replace('\n', ' ').strip(), page


def parse_status_cell(cell):
    text, page = parse_cell(cell)
    for tag in cell.get_tags():
        if tag.name == 'ref':
            note = tag.string
            break
    else:
        note = None
    symbol = None
    version = None

    try:
        bg = re.search(r'background: ([^;]+)', cell.attrs['style'])[1]
    except KeyError:
        bg = None
    if text == 'N/A' and bg is None:
        support = SupportLevel.UNAVAILABLE
    elif text == '?' and bg == 'grey':
        support = SupportLevel.UNKNOWN
    elif text == 'NO' and bg == 'black':
        support = SupportLevel.UNPLANNED
    elif text == 'NO' and bg == 'red':
        support = SupportLevel.UNSUPPORTED
    elif text == 'WIP' and bg == 'orange':
        support = SupportLevel.WIP
    elif bg == 'darkgreen':
        support = SupportLevel.COMPATIBLE
        version = text
    elif bg == 'lightgreen':
        support = SupportLevel.SUPPORTED
        version = text

    return support, note, page, symbol, version


def import_table(table):
    cells = table.cells()
    chips = []

    for heading in cells[0][2:]:
        chip = Chip.create()
        chips.append(chip)
        # Assume every name is a link to the chip's wiki page
        for link in heading.wikilinks:
            ChipInfo.create(
                chip=chip,
                kind=ChipInfoKind.MARKETING,
                name=link.text or link.title,
                page=link.target
            )

    for row in cells[1:-1]:
        name, page = parse_cell(row[0])
        category = Category.get_or_create(name=name, page=page)[0]

        name, page = parse_cell(row[1])
        feature = Feature.create(category=category, name=name, page=page)

        for chip, cell in zip(chips, row[2:]):
            support, note, page, symbol, version = parse_status_cell(cell)
            Status.create(
                chip=chip,
                feature=feature,
                support=support,
                note=note,
                page=page,
                symbol=symbol,
                version=version
            )


def format_link(page, text):
    if not page:
        return text
    if page == text:
        return f'[[{page}]]'
    if page.startswith('http'):
        return f'[{page} {text}]'
    return f'[[{page}|{text}]]'


def write_heading(o, chips):
    o.write('|-\n')
    o.write('! colspan="2" style="text-align: left; width: 13%" | Model\n')
    for chip in chips:
        o.write('! ')
        infos = chip.chipinfo_set.order_by(ChipInfo.name.collate('NOCASE'))
        for idx, info in enumerate(infos):
            if idx > 0:
                o.write('<br>')
            o.write(format_link(info.page, info.name))
        o.write('\n')


def write_cell(o, attrs, style, page, text, note=None):
    o.write('| ')
    if style:
        style = '; '.join(f'{k}: {v}' for k, v in sorted(style.items()))
        style = f'style="{style};"'
        if attrs:
            attrs = style + ' ' + attrs
        else:
            attrs = style
    if attrs:
        o.write(attrs.ljust(45))
        o.write('| ')
    o.write(format_link(page, text))
    if note:
        o.write(' ')
        o.write(note)
    o.write('\n')


def export_table(o):
    o.write('{| class="wikitable" style="text-align: center; width: 100%"\n')

    chips = tuple(Chip.select().order_by(Chip.order))
    write_heading(o, chips)
    o.write('\n')

    left_align = {'text-align': 'left'}
    for category in Category.select().order_by(Category.name.collate('NOCASE')):
        features = tuple(category.feature_set.order_by(Feature.name.collate('NOCASE')))
        for idx, feature in enumerate(features):
            o.write('|-\n')

            if idx == 0 and len(features) > 1:
                attrs = f'rowspan="{len(features)}"'
                write_cell(o, attrs, left_align, category.page, category.name)

            attrs = 'colspan="2"' if len(features) == 1 else None
            write_cell(o, attrs, left_align, feature.page, feature.name)

            for chip in chips:
                status = Status.get(chip=chip, feature=feature)
                if status.support == SupportLevel.UNAVAILABLE:
                    style = {}
                    text = 'N/A'
                elif status.support == SupportLevel.UNKNOWN:
                    style = {'background': 'grey', 'color': 'white'}
                    text = '?'
                elif status.support == SupportLevel.UNPLANNED:
                    style = {'background': 'black', 'color': 'white'}
                    text = 'NO'
                elif status.support == SupportLevel.UNSUPPORTED:
                    style = {'background': 'red'}
                    text = 'NO'
                elif status.support == SupportLevel.WIP:
                    style = {'background': 'orange'}
                    text = 'WIP'
                elif status.support == SupportLevel.COMPATIBLE:
                    style = {'background': 'darkgreen', 'color': 'white'}
                    text = status.version
                elif status.support == SupportLevel.SUPPORTED:
                    style = {'background': 'lightgreen'}
                    text = status.version
                write_cell(o, None, style, status.page, text, status.note)

            o.write('\n')

    write_heading(o, chips)

    o.write('|}\n')


def main(action, infile, outfile):
    if action == 'import':
        db.init(outfile, pragmas={
            'foreign_keys': 1,
            'journal_mode': 'wal',
        })
        db.create_tables([Category, Feature, Chip, ChipInfo, Status])

        root = ET.parse(infile)
        wikitext = root.findtext('.//{*}text')
        page = wtp.parse(wikitext)
        table = page.tables[0]

        import_table(table)
    elif action == 'export':
        db.init(infile, pragmas={
            'foreign_keys': 1,
            'journal_mode': 'wal',
        })

        with open(outfile, 'w') as output:
            export_table(output)

if __name__ == '__main__':
    main(*sys.argv[1:])
