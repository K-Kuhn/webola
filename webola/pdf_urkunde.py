from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from webola.database import Team
from webola.statistik import collect_data
from webola.utils import time2str

RESOURCES    = Path(__file__).parent.parent / 'resources'
HEAD_IMAGE   = RESOURCES / 'head.png'
LEFT_IMAGE   = RESOURCES / 'bottom left.png'
RIGHT_IMAGE  = RESOURCES / 'bottom right.png'

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


def _draw_header(c):
    top = A4[1] - MARGIN
    head_h = _draw_image(c, HEAD_IMAGE, A4[0] / 2, top - HEAD_WIDTH * 676 / 897, HEAD_WIDTH, anchor='center')
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


def _draw_bottom_images(c):
    y = MARGIN
    _draw_image(c, LEFT_IMAGE,  MARGIN,          y, BOTTOM_WIDTH, anchor='left')
    right_h = _draw_image(c, RIGHT_IMAGE, A4[0] - MARGIN, y, BOTTOM_WIDTH, anchor='right')
    left_h  = BOTTOM_WIDTH * 518 / 618
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


def draw_einzel_urkunde(c, wettkampf, team, pos, klasse, modus):
    y = _draw_header(c)
    y = _draw_wettkampf_info(c, y, wettkampf)
    bottom_y = _draw_bottom_images(c)

    name, verein = team.get_name_verein()
    schuss, fehler = _team_result(team)

    items  = _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(name, FONT_BOLD, 20, gap_after=5)]
    if verein:
        items += [_text_item(verein, FONT, 13, gap_after=8)]
    items += [_text_item(time2str(team.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, fehler, modus, _strafen_text(team))

    _render_block(c, items, y, bottom_y)


def draw_starter_urkunde(c, wettkampf, starter, team, pos, klasse, modus):
    y = _draw_header(c)
    y = _draw_wettkampf_info(c, y, wettkampf)
    bottom_y = _draw_bottom_images(c)

    schuss = team.lauf.anzahl_schiessen * team.lauf.anzahl_pfeile

    items  = _platz_und_klasse_items(pos, klasse.name)
    items += [_text_item(starter.get_name(), FONT_BOLD, 20, gap_after=5)]
    if starter.verein:
        items += [_text_item(starter.verein, FONT, 13, gap_after=8)]
    items += [_text_item(time2str(starter.zeit()), FONT_BOLD, 18, gap_after=5)]
    items += _result_items(schuss, starter.fehler or 0, modus, _strafen_text(starter))

    _render_block(c, items, y, bottom_y)


def draw_team_urkunde(c, wettkampf, team, pos, klasse, modus):
    y = _draw_header(c)
    y = _draw_wettkampf_info(c, y, wettkampf)
    bottom_y = _draw_bottom_images(c)

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


def collect_urkunden(wettkampf, maxres):
    for klasse in collect_data(wettkampf):
        if not klasse.is_wertung_done():
            continue
        pos, sieger = 1, None
        for team in Team.sortiere(klasse.teams()):
            if team.platz and not team.is_dsq() and maxres.valid(team, pos):
                yield team, (pos if team.is_ranked() else None), klasse
                pos += 1 if team.is_ranked() else 0


def generate_urkunden_pdf(wettkampf, out_path, maxres, modus):
    c = canvas.Canvas(str(out_path), pagesize=A4)

    for team, pos, klasse in collect_urkunden(wettkampf, maxres):
        if team.ist_staffel():
            if modus.staffel in ('Team', 'Einzeln+Team'):
                draw_team_urkunde(c, wettkampf, team, pos, klasse, modus)
                c.showPage()
            if modus.staffel in ('Einzeln', 'Einzeln+Team'):
                for starter in team.liste():
                    draw_starter_urkunde(c, wettkampf, starter, team, pos, klasse, modus)
                    c.showPage()
        else:
            draw_einzel_urkunde(c, wettkampf, team, pos, klasse, modus)
            c.showPage()

    c.save()
    return out_path
