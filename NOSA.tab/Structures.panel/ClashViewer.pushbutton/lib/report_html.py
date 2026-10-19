# -*- coding: utf-8 -*-
"""Self-contained HTML clash report: the Navisworks picture next to the Revit one, per clash."""
import base64

_CSS = u"""
:root{--accent:#FF5F00;--ink:#333;--line:#E0E0E0;--ok:#2EAA4A;--bad:#D32F2F;--warn:#C77700;--mute:#8a8a8a}
*{box-sizing:border-box}
body{font-family:'Century Gothic','Segoe UI',Arial,sans-serif;color:var(--ink);margin:0;background:#fafafa}
header{background:#fff;border-bottom:4px solid var(--accent);padding:22px 32px}
h1{margin:0;color:var(--accent);font-size:24px;letter-spacing:.5px}
.sub{color:var(--mute);font-size:12px;margin-top:6px}
main{padding:24px 32px;max-width:1100px;margin:auto}
.summary{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}
.stat{background:#fff;border:1px solid var(--line);border-radius:8px;padding:10px 16px;min-width:120px}
.stat b{display:block;font-size:22px}.stat span{font-size:11px;color:var(--mute);text-transform:uppercase}
.card{background:#fff;border:1px solid var(--line);border-radius:10px;padding:16px 18px;margin-bottom:18px;break-inside:avoid;page-break-inside:avoid}
.card h2{margin:0 0 4px;font-size:17px}.card .path{color:var(--mute);font-size:12px;margin-bottom:10px}
.badges span{display:inline-block;border-radius:12px;padding:2px 10px;font-size:11px;margin:0 6px 6px 0;color:#fff;background:var(--mute)}
.badges .ok{background:var(--ok)}.badges .bad{background:var(--bad)}.badges .warn{background:var(--warn)}.badges .st{background:#555}
.pics{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:8px 0 12px;align-items:start}
figure{margin:0;border:1px solid var(--line);border-radius:8px;padding:6px;background:#fcfcfc;text-align:center}
figure img{max-width:100%;max-height:360px}figcaption{font-size:11px;color:var(--mute);margin-top:4px}
.none{color:var(--mute);font-size:12px;padding:60px 0}
.items{display:grid;grid-template-columns:1fr 1fr;gap:14px;font-size:12px}
.item{border-left:3px solid var(--line);padding-left:10px}.item b{display:block;margin-bottom:2px}
.k-ok{color:var(--ok)}.k-bad{color:var(--bad)}.k-warn{color:var(--warn)}.k-none{color:var(--mute)}
.note{margin-top:10px;background:#FFF4EB;border-left:3px solid var(--accent);padding:8px 12px;font-size:12px;white-space:pre-wrap}
.check{margin:6px 0;font-size:12px;font-weight:600}
footer{color:var(--mute);font-size:11px;padding:16px 32px;text-align:center}
@media print{body{background:#fff}main{max-width:none;padding:0 8px}header{padding:12px 8px}}
"""


def _esc(value):
    text = value if isinstance(value, type(u'')) else (u'%s' % (value,) if value is not None else u'')
    return (text.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')
            .replace(u'"', u'&quot;'))


def _data_uri(data):
    if not data:
        return None
    mime = u'image/png' if data[:4] == b'\x89PNG' else u'image/jpeg'
    encoded = base64.b64encode(data)
    if not isinstance(encoded, type(u'')):
        encoded = encoded.decode('ascii')
    return u'data:%s;base64,%s' % (mime, encoded)


def _figure(data, caption):
    uri = _data_uri(data)
    body = (u'<img src="%s" alt="%s">' % (uri, _esc(caption)) if uri
            else u'<div class="none">No image available</div>')
    return u'<figure>%s<figcaption>%s</figcaption></figure>' % (body, _esc(caption))


def _item(item):
    lines = u'<br>'.join(_esc(x) for x in item.get('info', []))
    return (u'<div class="item"><b>%s</b>%s<div class="k-%s">%s</div></div>'
            % (_esc(item.get('title', u'')), lines, _esc(item.get('kind', u'none')), _esc(item.get('state', u''))))


def _card(e, meta):
    badges = [u'<span class="st">%s</span>' % _esc(e.get('status', u''))]
    if e.get('done'):
        badges.append(u'<span class="ok">Done%s</span>' % (
            u' · %s, %s' % (_esc(e.get('done_by', u'')), _esc(e.get('done_at', u''))) if e.get('done_by') else u''))
    else:
        badges.append(u'<span class="bad">Open</span>')
    if e.get('assigned'):
        badges.append(u'<span>%s</span>' % _esc(e['assigned']))
    check = e.get('check_kind')
    check_html = u''
    if check:
        cls = {u'cleared': u'ok', u'still': u'bad'}.get(check, u'warn')
        check_html = u'<div class="check k-%s">Geometry re-check: %s</div>' % (cls, _esc(e.get('check_text', u'')))
    note = u''
    if e.get('note'):
        note = u'<div class="note"><b>Note</b> (%s, %s)<br>%s</div>' % (
            _esc(e.get('note_by', u'')), _esc(e.get('note_at', u'')), _esc(e['note']))
    return (u'<section class="card"><h2>%s</h2><div class="path">%s › %s%s</div>'
            u'<div class="badges">%s</div><div class="pics">%s%s</div>%s'
            u'<div class="items">%s%s</div>%s</section>' % (
                _esc(e.get('name', u'')), _esc(e.get('test', u'')), _esc(e.get('group', u'')),
                u'  ·  point %s' % _esc(e['point']) if e.get('point') else u'',
                u''.join(badges),
                _figure(e.get('before'), u'As reported · Navisworks · revision %s' % meta.get('revision', u'-')),
                _figure(e.get('after'), u'Now · Revit · %s' % meta.get('generated', u'')),
                check_html, _item(e['items'][0]), _item(e['items'][1]), note))


def build_report(meta, entries):
    """Return the whole report as one unicode HTML string."""
    done = sum(1 for e in entries if e.get('done'))
    cleared = sum(1 for e in entries if e.get('check_kind') == u'cleared')
    still = sum(1 for e in entries if e.get('check_kind') == u'still')
    stats = u''.join(u'<div class="stat"><b>%s</b><span>%s</span></div>' % (n, _esc(label)) for n, label in (
        (len(entries), u'Clashes in this report'), (done, u'Done'), (len(entries) - done, u'Open'),
        (cleared, u'No longer clashing'), (still, u'Still clashing')))
    cards = u''.join(_card(e, meta) for e in entries)
    return (u'<!DOCTYPE html><html lang="en-GB"><head><meta charset="utf-8"><title>%s</title><style>%s</style></head>'
            u'<body><header><h1>CLASH REPORT — BEFORE AND NOW</h1><div class="sub">%s · revision %s (%s) · '
            u'generated %s by %s · %s</div></header><main><div class="summary">%s</div>%s</main>'
            u'<footer>NOSA Clash Viewer. “As reported” images come from the Navisworks report; “Now” images are '
            u'taken from the Revit model when the report was generated. The geometry re-check is indicative.</footer>'
            u'</body></html>' % (
                _esc(meta.get('title', u'Clash report')), _CSS, _esc(meta.get('document_code', u'')),
                _esc(meta.get('revision', u'-')), _esc(meta.get('revision_date', u'')), _esc(meta.get('generated', u'')),
                _esc(meta.get('user', u'')), _esc(meta.get('scope', u'')), stats, cards))
