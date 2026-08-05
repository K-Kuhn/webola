import io
from pathlib import Path
from dataclasses import dataclass

from PyQt5.QtCore import QSettings
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import fitz

from webola.database import Team
from webola.statistik import collect_data
from webola.utils import time2str

# Blank content zone measured directly from resources/Urkunde_empty.pdf (a single
# flattened raster scan with no separate text/image objects to read positions from):
# scanned the rendered page pixel-row by pixel-row for a large gap between the
# printed "URKUNDE" stencil and the two signature images at the bottom.
TEXT_ONLY_TOP    = 521
TEXT_ONLY_BOTTOM = 223

MM           = 72 / 25.4
MARGIN       = 20 * MM
HEAD_WIDTH   = 55 * MM
BOTTOM_WIDTH = 38 * MM

FONT         = 'Helvetica'
FONT_BOLD    = 'Helvetica-Bold'

LINE_HEIGHT  = 1.25      # multiple of font size used as line height
MIN_SCALE    = 0.7
MAX_SCALE    = 2.2
FILL_FACTOR  = 0.90      # fraction of available space the scaled block should target


@dataclass
class UrkundeImages:
    head:  str
    left:  str
    right: str

    def valid(self):
        return all(p and Path(p).is_file() for p in (self.head, self.left, self.right))


def load_saved_images():
    s = QSettings('webola', 'webola')
    return UrkundeImages(
        head  = s.value('urkunde/head' , ''),
        left  = s.value('urkunde/left' , ''),
        right = s.value('urkunde/right', ''))


def save_images(images):
    s = QSettings('webola', 'webola')
    s.setValue('urkunde/head' , images.head )
    s.setValue('urkunde/left' , images.left )
    s.setValue('urkunde/right', images.right)


def load_saved_template():
    return QSettings('webola', 'webola').value('urkunde/template_pdf', '')


def save_template(path):
    QSettings('webola', 'webola').setValue('urkunde/template_pdf', path)


def _draw_image(c, path, x, y, width, anchor='left'):
    img    = ImageReader(str(path))
    iw, ih = img.getSize()
    height = width * ih / iw
    if anchor == 'center':
        x -= width / 2
    elif anchor == 'right':
        x -= width
    c.drawImage(img, x, y, width=width, height=height, mask='auto')
    return height


def _centered(c, text, y, font, size, color=(0, 0, 0)):
    c.setFont(font, size)
    c.setFillColorRGB(*color)
    c.drawCentredString(A4[0] / 2, y, text)


def _row(c, y, columns, font, size, color=(0, 0, 0)):
    # columns: list of (x_center, text)
    c.setFont(font, size)
    c.setFillColorRGB(*color)
    for x, text in columns:
        c.drawCentredString(x, y, text)


def _draw_header(c, images):
    top = A4[1] - MARGIN
    head_h = _draw_image(c, images.head, A4[0] / 2, top - HEAD_WIDTH * 676 / 897, HEAD_WIDTH, anchor='center')
    y = top - head_h - 16 * MM
    _centered(c, 'URKUNDE', y, FONT_BOLD, 36)
    y -= 13 * MM
    return y


def _draw_wettkampf_info(c, y, wettkampf):
    _centered(c, wettkampf.name or '', y, FONT_BOLD, 15)
    y -= 6 * MM
    info = wettkampf.datum
    if wettkampf.ort:
        info += f'  --  {wettkampf.ort}'
    _centered(c, info, y, FONT, 10)
    return y - 10 * MM


def _draw_bottom_images(c, images):
    y = MARGIN
    left_h  = _draw_image(c, images.left,  MARGIN,          y, BOTTOM_WIDTH, anchor='left')
    right_h = _draw_image(c, images.right, A4[0] - MARGIN,  y, BOTTOM_WIDTH, anchor='right')
    return y + max(left_h, right_h) + 12 * MM


def _treffer_oder_fehler(schuss, fehler, mode):
    if mode == 'Treffer':
        return f'{schuss - fehler} / {schuss} Treffer'
    else:
        return f'{fehler} Fehler'


def _team_result(team):
    schuss = team.lauf.anzahl_schiessen * team.lauf.anzahl_pfeile
    return schuss, team.fehler() or 0


def _strafen_text(entity):
    if hasattr(entity, 'liste'):  # Team
        return entity.strafen()
    else:                          # Starter
        return '' if not entity.strafen else f'{entity.strafen}x{entity.einheit()}s'


# -- content block: build a list of items, measure, scale to fill available space -------

def _item(kind, **kw):
    return dict(kind=kind, **kw)

def _text_item(text, font, size, gap_after=6, color=(0, 0, 0)):
    return _item('text', text=text, font=font, size=size, gap_after=gap_after, color=color)

def _row_item(cells, font, size, gap_after=2, color=(0, 0, 0)):
    return _item('row', cells=cells, font=font, size=size, gap_after=gap_after, color=color)


def _natural_height(items):
    total = 0
    for it in items:
        total += it['size'] * LINE_HEIGHT + it['gap_after'] * MM
    return total


def _render_block(c, items, top_y, bottom_y):
    available = top_y - bottom_y
    natural   = _natural_height(items)
    if natural <= 0:
        return
    scale = max(MIN_SCALE, min(MAX_SCALE, (available * FILL_FACTOR) / natural))

    y = top_y - (available - natural * scale) / 2 - items[0]['size'] * scale * 0.8
    for it in items:
        size = it['size'] * scale
        if it['kind'] == 'text':
            _centered(c, it['text'], y, it['font'], size, it.get('color', (0, 0, 0)))
        else:
            _row(c, y, [(x, t) for x, t in it['cells']], it['font'], size, it.get('color', (0, 0, 0)))
        y -= size * LINE_HEIGHT + it['gap_after'] * MM * scale


def _platz_und_klasse_items(pos, klasse):
    items = []
    if pos is None:
        items.append(_text_item('außer Konkurrenz', FONT, 13, gap_after=3))
        items.append(_text_item(klasse, FONT, 15, gap_after=8))
    else:
        items.append(_text_item(f'{pos}. Platz', FONT_BOLD, 22, gap_after=3))
        items.append(_text_item(klasse, FONT, 15, gap_after=8))
    return items


def _result_items(schuss, fehler, modus, penalty_text):
    items = [_text_item(_treffer_oder_fehler(schuss, fehler, modus.mode), FONT, 13, gap_after=6)]
    if modus.strafen == 'mit Strafen' and penalty_text:
        items.append(_text_item(f'inkl. {penalty_text}', FONT, 9, gap_after=6, color=(0.4, 0.4, 0.4)))
    return items


def _wettkampf_info_items(wettkampf):
    info = wettkampf.datum
    if wettkampf.ort:
        info += f'  --  {wettkampf.ort}'
    return [_text_item(wettkampf.name or '', FONT_BOLD, 13, gap_after=3),
            _text_item(info, FONT, 9, gap_after=8)]


def draw_einzel_urkunde(c, wettkampf, team, pos, klasse, modus, images):
    y = _draw_header(c, images)
    y = _draw_wettkampf_info(c, y, wettkampf)
    bottom_y = _draw_bottom_images(c, images)

    name, verein = team.get_name_verein()
    schuss, fehler = _team_result(team)

    items  = _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(name, FONT_BOLD, 20, gap_after=5)]
    if verein:
        items += [_text_item(verein, FONT, 13, gap_after=8)]
    items += [_text_item(time2str(team.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, fehler, modus, _strafen_text(team))

    _render_block(c, items, y, bottom_y)


def draw_starter_urkunde(c, wettkampf, starter, team, pos, klasse, modus, images):
    y = _draw_header(c, images)
    y = _draw_wettkampf_info(c, y, wettkampf)
    bottom_y = _draw_bottom_images(c, images)

    schuss = team.lauf.anzahl_schiessen * team.lauf.anzahl_pfeile

    items  = _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(starter.get_name(), FONT_BOLD, 20, gap_after=5)]
    if starter.verein:
        items += [_text_item(starter.verein, FONT, 13, gap_after=8)]
    items += [_text_item(time2str(starter.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, starter.fehler or 0, modus, _strafen_text(starter))

    _render_block(c, items, y, bottom_y)


def draw_team_urkunde(c, wettkampf, team, pos, klasse, modus, images):
    y = _draw_header(c, images)
    y = _draw_wettkampf_info(c, y, wettkampf)
    bottom_y = _draw_bottom_images(c, images)

    name, vereine = team.get_name_verein()
    zeigen = name if modus.teamname == 'mit Teamname' else vereine
    schuss, fehler = _team_result(team)

    items  = _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(zeigen, FONT_BOLD, 18, gap_after=8)]
    items += [_text_item(time2str(team.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, fehler, modus, _strafen_text(team))

    items.append(_text_item('', FONT, 6, gap_after=4))  # small breathing gap before roster

    cx = A4[0] / 2
    for starter in team.liste():
        cells = [(cx - 60 * MM, starter.get_name()),
                 (cx,           starter.verein or ''),
                 (cx + 60 * MM, time2str(starter.zeit()))]
        items.append(_row_item(cells, FONT, 11, gap_after=3))

    _render_block(c, items, y, bottom_y)


def draw_einzel_text_only(c, wettkampf, team, pos, klasse, modus):
    name, verein = team.get_name_verein()
    schuss, fehler = _team_result(team)

    items  = _wettkampf_info_items(wettkampf)
    items += _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(name, FONT_BOLD, 20, gap_after=5)]
    if verein:
        items += [_text_item(verein, FONT, 13, gap_after=8)]
    items += [_text_item(time2str(team.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, fehler, modus, _strafen_text(team))

    _render_block(c, items, TEXT_ONLY_TOP, TEXT_ONLY_BOTTOM)


def draw_starter_text_only(c, wettkampf, starter, team, pos, klasse, modus):
    schuss = team.lauf.anzahl_schiessen * team.lauf.anzahl_pfeile

    items  = _wettkampf_info_items(wettkampf)
    items += _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(starter.get_name(), FONT_BOLD, 20, gap_after=5)]
    if starter.verein:
        items += [_text_item(starter.verein, FONT, 13, gap_after=8)]
    items += [_text_item(time2str(starter.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, starter.fehler or 0, modus, _strafen_text(starter))

    _render_block(c, items, TEXT_ONLY_TOP, TEXT_ONLY_BOTTOM)


def draw_team_text_only(c, wettkampf, team, pos, klasse, modus):
    name, vereine = team.get_name_verein()
    zeigen = name if modus.teamname == 'mit Teamname' else vereine
    schuss, fehler = _team_result(team)

    items  = _wettkampf_info_items(wettkampf)
    items += _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(zeigen, FONT_BOLD, 18, gap_after=8)]
    items += [_text_item(time2str(team.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, fehler, modus, _strafen_text(team))

    items.append(_text_item('', FONT, 6, gap_after=4))

    cx = A4[0] / 2
    for starter in team.liste():
        cells = [(cx - 60 * MM, starter.get_name()),
                 (cx,           starter.verein or ''),
                 (cx + 60 * MM, time2str(starter.zeit()))]
        items.append(_row_item(cells, FONT, 11, gap_after=3))

    _render_block(c, items, TEXT_ONLY_TOP, TEXT_ONLY_BOTTOM)


def draw_sample_text_only(c):
    class _Wettkampf:
        name = '13. Werderaner Bogenlauf'
        datum = '4. August 2026'
        ort   = 'Werder (Havel)'

    items  = _wettkampf_info_items(_Wettkampf())
    items += _platz_und_klasse_items(1, 'Cadet (M) standard')
    items += [_text_item('Max Mustermann', FONT_BOLD, 20, gap_after=5)]
    items += [_text_item('SV Werder', FONT, 13, gap_after=8)]
    items += [_text_item('01:57.3', FONT_BOLD, 18, gap_after=5)]
    items += [_text_item('10 / 12 Treffer', FONT, 13, gap_after=6)]

    _render_block(c, items, TEXT_ONLY_TOP, TEXT_ONLY_BOTTOM)


def _overlay_pdf_bytes(draw_fn):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    draw_fn(c)
    c.showPage()
    c.save()
    return buf.getvalue()


def generate_urkunden_text_pdf(wettkampf, out_path, maxres, modus):
    """Text-only certificates, meant to be printed onto the pre-printed paper
    (head/bottom images, "URKUNDE" title) directly -- no template/images are
    read or embedded here, the printed sheet already has them."""
    c = canvas.Canvas(str(out_path), pagesize=A4)

    for team, pos, klasse in collect_urkunden(wettkampf, maxres):
        if team.ist_staffel():
            if modus.staffel in ('Team', 'Einzeln+Team'):
                draw_team_text_only(c, wettkampf, team, pos, klasse, modus)
                c.showPage()
            if modus.staffel in ('Einzeln', 'Einzeln+Team'):
                for starter in team.liste():
                    draw_starter_text_only(c, wettkampf, starter, team, pos, klasse, modus)
                    c.showPage()
        else:
            draw_einzel_text_only(c, wettkampf, team, pos, klasse, modus)
            c.showPage()

    c.save()
    return out_path


def render_text_on_template_preview(template_path, zoom=2.0):
    """Composite the sample text-only certificate onto the (local-only, never
    embedded in generated output) template PDF for a WYSIWYG preview -- pure
    raster compositing via Pillow's multiply blend (works cleanly for black
    text on a light background, no PDF-level merging involved)."""
    from PIL import Image, ImageChops

    template_doc = fitz.open(str(template_path))
    template_pix = template_doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    template_img = Image.frombytes('RGB', (template_pix.width, template_pix.height), template_pix.samples)
    template_doc.close()

    text_doc = fitz.open(stream=_overlay_pdf_bytes(draw_sample_text_only), filetype='pdf')
    text_pix = text_doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    text_img = Image.frombytes('RGB', (text_pix.width, text_pix.height), text_pix.samples)
    text_doc.close()

    if text_img.size != template_img.size:
        text_img = text_img.resize(template_img.size)

    return ImageChops.multiply(template_img, text_img)


def draw_sample_urkunde(c, images):
    """A representative placeholder certificate, used for the layout preview
    before any results necessarily exist."""
    class _Wettkampf:
        name = '13. Werderaner Bogenlauf'
        datum = '4. August 2026'
        ort   = 'Werder (Havel)'

    y = _draw_header(c, images)
    y = _draw_wettkampf_info(c, y, _Wettkampf())
    bottom_y = _draw_bottom_images(c, images)

    items  = _platz_und_klasse_items(1, 'Cadet (M) standard')
    items += [_text_item('Max Mustermann', FONT_BOLD, 20, gap_after=5)]
    items += [_text_item('SV Werder', FONT, 13, gap_after=8)]
    items += [_text_item('01:57.3', FONT_BOLD, 18, gap_after=5)]
    items += [_text_item('10 / 12 Treffer', FONT, 13, gap_after=6)]

    _render_block(c, items, y, bottom_y)


def collect_urkunden(wettkampf, maxres):
    for klasse in collect_data(wettkampf):
        if not klasse.is_wertung_done():
            continue
        pos, sieger = 1, None
        for team in Team.sortiere(klasse.teams()):
            if team.platz and not team.is_dsq() and maxres.valid(team, pos):
                yield team, (pos if team.is_ranked() else None), klasse
                pos += 1 if team.is_ranked() else 0


def generate_preview_pdf(out_path, images):
    c = canvas.Canvas(str(out_path), pagesize=A4)
    draw_sample_urkunde(c, images)
    c.showPage()
    c.save()
    return out_path


def generate_urkunden_pdf(wettkampf, out_path, maxres, modus, images):
    c = canvas.Canvas(str(out_path), pagesize=A4)

    for team, pos, klasse in collect_urkunden(wettkampf, maxres):
        if team.ist_staffel():
            if modus.staffel in ('Team', 'Einzeln+Team'):
                draw_team_urkunde(c, wettkampf, team, pos, klasse, modus, images)
                c.showPage()
            if modus.staffel in ('Einzeln', 'Einzeln+Team'):
                for starter in team.liste():
                    draw_starter_urkunde(c, wettkampf, starter, team, pos, klasse, modus, images)
                    c.showPage()
        else:
            draw_einzel_urkunde(c, wettkampf, team, pos, klasse, modus, images)
            c.showPage()

    c.save()
    return out_path
