from __future__ import annotations

import json
import math
import os
import subprocess
from typing import ClassVar

from visidata import Column, EscapeException, Sheet, clipstr_middle, vd

from .session import kind_of


def cell_text(value):
    return value if type(value) is str else json.dumps(value, allow_nan=False, ensure_ascii=False)


def parse_value(kind, raw):
    if kind == 'string':
        return raw
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate object key')
            result[key] = value
        return result
    def nonfinite(_value):
        raise ValueError('Numbers must be finite')
    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)
    if kind_of(value) != kind:
        # A numeric Field may consume an integral numeric literal without becoming an int Field.
        if kind == 'number' and type(value) is int:
            return float(value)
        raise ValueError('Value does not match the selected native type')
    if type(value) is float and not math.isfinite(value):
        raise ValueError('Numbers must be finite')
    json.dumps(value, allow_nan=False)
    return value


class DataspaceSheet(Sheet):
    columns: ClassVar[list] = [
        Column('key', width=25, getter=lambda c, r: r['key']),
        Column('kind', width=10, getter=lambda c, r: r['kind']),
        Column('contract', width=15, getter=lambda c, r: r.get('contract', r.get('dataset', ''))),
        Column('operations', width=18, getter=lambda c, r: ','.join(r.get('operations', []))),
        Column('effective', width=18, getter=lambda c, r: ','.join(r.get('effective_operations', []))),
        Column('default', width=8, getter=lambda c, r: 'yes' if r.get('has_default') else 'no' if r['kind'] == 'field' else ''),
        Column('value', width=60, getter=lambda c, r: display(r)),
    ]

    def __init__(self, browser, values, *, logo='dix'):
        self.browser, self.values, self.logo = browser, values, logo
        super().__init__('Dataspace')
        self.value_sample = values.require('create_sheet')(
            values.require('create_draft')({}), logo=logo, title='Local Dataspace value')
        vd.options.set('disp_rstatus_fmt', '{sheet.nRows} rows', obj=type(self))

    @property
    def nHeaderRows(self):
        return 2

    def drawColHeader(self, scr, y, h, vcolidx):
        col = self.availCols[vcolidx]
        original = col._name
        label = self.browser.error or self.browser.notice or self.browser.breadcrumb
        text = f'{self.logo.upper()} Dataspace' if vcolidx == 0 else label if vcolidx == 6 else ''
        col._name = clipstr_middle(text, max(self._visibleColLayout[vcolidx][1]-1, 0))[0] + '\n' + original
        try:
            super().drawColHeader(scr, y, h, vcolidx)
        finally:
            col._name = original

    def reload(self):
        self.browser.reload()
        self.render()

    def render(self):
        self.rows = self.browser.rows()
        self.cursorRowIndex = min(max(self.cursorRowIndex, 0), max(len(self.rows)-1, 0))
        self.name = f'{self.logo.upper()} Dataspace | {self.browser.breadcrumb}'
        if self.browser.error:
            vd.status(self.browser.error)

    def enter(self):
        row = self.cursorRow
        if row is None:
            return
        if row['kind'] != 'field':
            self.browser.enter(row['key'])
            self.cursorRowIndex = self.cursorVisibleColIndex = 0
            self.render()
        elif not row['loaded'] or self.cursorCol.name != 'value':
            self.browser.load(row['set'], row['key'])
            self.render()
            self.cursorVisibleColIndex = 6
        else:
            self.edit_value()

    def parent(self):
        self.browser.parent()
        self.cursorRowIndex = self.cursorVisibleColIndex = 0
        self.render()

    def edit_value(self):
        row = self.cursorRow
        if row is None or row['kind'] != 'field':
            raise ValueError('Select a Field')
        if 'set' not in row['effective_operations']:
            raise PermissionError('Field does not offer set')
        self.cursorVisibleColIndex = 6
        if row['loaded']:
            value, kind = row['value'], kind_of(row['value'])
        else:
            kind = vd.input('Value type (string/integer/number/boolean/null/array/object): ',
                            value='string', record=False)
            if kind not in {'string', 'integer', 'number', 'boolean', 'null', 'array', 'object'}:
                raise ValueError('Choose a native value type')
            value = {'string': '', 'integer': 0, 'number': 0.0, 'boolean': False,
                     'null': None, 'array': [], 'object': {}}[kind]
        if kind in {'array', 'object'}:
            draft = self.values.require('create_draft')(value)
            def commit(changed):
                if not self.browser.set_value(row['set'], row['key'], changed):
                    vd.fail(self.browser.error)
                # Return to the canonical provider-returned Field value, without a hidden Get.
                while vd.sheets and getattr(vd.sheets[0], 'draft', None) is draft:
                    vd.remove(vd.sheets[0])
                self.render()
            editor = self.values.require('create_sheet')(
                draft, logo=self.logo, title='Whole Dataspace Field value', on_commit=commit)
            editor.reload()
            vd.push(editor)
        else:
            raw = self.editCell(value=cell_text(value), record=False)
            self.browser.set_value(row['set'], row['key'], parse_value(kind, raw))
            self.render()

    def dispatch(self, token):
        try:
            if token == 'g' and self.cursorRow is not None and self.cursorRow['kind'] == 'field':
                row = self.cursorRow
                self.browser.load(row['set'], row['key'])
                self.render()
            elif token == 's':
                self.edit_value()
            elif token == 'd':
                row = self.cursorRow
                if row is None or row['kind'] != 'field':
                    raise ValueError('Select a Field')
                if vd.confirm('Delete this whole stored Field value? '):
                    self.browser.delete_value(row['set'], row['key'])
                    self.render()
            elif token == 'r':
                self.reload()
            elif token == 'q':
                vd.remove(self)
            else:
                raise ValueError('Use g, s, d, r or q')
        except EscapeException:
            self.browser.error = ''
            self.browser.notice = 'Cancelled; no new write'
        except Exception as exc:  # noqa: BLE001 - do not expose exception payloads from opaque targets
            self.browser.failure('Action', exc)
            vd.status(self.browser.error)

    def command(self):
        self.dispatch(vd.input(':', record=False).strip())

    def copy_cell(self):
        row = self.cursorRow
        if row is None:
            return
        try:
            if self.cursorCol.name == 'value':
                if not row.get('loaded'):
                    raise ValueError('Load the Field explicitly before copying its value')
                text = cell_text(row['value'])
            else:
                text = str(self.cursorCol.getValue(row))
            adapter = os.environ.get('DIX_COCKPIT_CLIPBOARD_COPY', '')
            if not adapter or not os.path.isabs(adapter):
                raise RuntimeError('clipboard adapter is not configured')
            result = subprocess.run([adapter], input=text, text=True, capture_output=True, check=False)
            if result.returncode:
                raise RuntimeError('clipboard adapter failed')
            vd.status('Full selected value copied')
        except Exception as exc:  # noqa: BLE001 - clipboard failures never echo payloads
            self.browser.failure('Copy', exc)
            vd.status(self.browser.error)


def display(row):
    if row['kind'] != 'field' or not row.get('loaded'):
        return ''
    value = row['value']
    if type(value) is dict:
        return f'{{{len(value)} fields}}'
    if type(value) is list:
        return f'[{len(value)} items]'
    return cell_text(value)


for name, expr in [
    ('dataspace-enter', 'sheet.enter()'), ('edit-cell', 'sheet.edit_value()'),
    ('dataspace-parent', 'sheet.parent()'), ('dataspace-prompt', 'sheet.command()'),
    ('dataspace-reload', 'sheet.reload()'), ('dataspace-copy', 'sheet.copy_cell()'),
]:
    DataspaceSheet.addCommand(None, name, expr, name, replay=False)
