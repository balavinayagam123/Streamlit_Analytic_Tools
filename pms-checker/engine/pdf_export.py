"""
pdf_export.py
Generates a PDF report from analysis results using Jinja2 + WeasyPrint.
Anglo-Eastern brand colours: Blue #003963, Gold #F3AD1C, Teal #00B098
"""
from jinja2 import Template
import io

AE_BLUE  = "#003963"
AE_GOLD  = "#F3AD1C"
AE_TEAL  = "#00B098"
AE_GREEN = "#00B050"
AE_RED   = "#FF0000"
AE_GREY  = "#A5A5A5"
AE_LGREY = "#D8D8D8"

CSS = f"""
@page {{
  size: A4;
  margin: 15mm 15mm 20mm 15mm;
  @bottom-center {{
    content: "Anglo-Eastern Ship Management Ltd  |  PMS Data Sufficiency Report  |  Page " counter(page) " of " counter(pages);
    font-size: 8pt; font-family: Arial; color: {AE_GREY};
  }}
  @top-right {{
    content: "CONFIDENTIAL";
    font-size: 7pt; font-family: Arial; color: {AE_GREY};
  }}
}}
body {{ font-family: Arial; font-size: 9pt; color: #000; margin: 0; }}
h1 {{ font-size: 16pt; color: {AE_BLUE}; margin: 0 0 4pt 0; border-bottom: 2pt solid {AE_BLUE}; padding-bottom: 4pt; }}
h2 {{ font-size: 12pt; color: {AE_BLUE}; margin: 12pt 0 4pt 0; }}
h3 {{ font-size: 10pt; color: {AE_BLUE}; margin: 8pt 0 3pt 0; }}
.header-block {{ background: {AE_BLUE}; color: white; padding: 10pt 14pt; margin-bottom: 12pt; }}
.header-block .vessel {{ font-size: 14pt; font-weight: bold; }}
.header-block .meta {{ font-size: 9pt; opacity: .85; margin-top: 2pt; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8pt; margin-bottom: 8pt; }}
th {{ background: {AE_BLUE}; color: white; padding: 4pt 6pt; text-align: left; font-size: 8pt; }}
td {{ padding: 3pt 6pt; border-bottom: 0.5pt solid {AE_LGREY}; }}
tr.tot td {{ background: {AE_LGREY}; font-weight: bold; }}
.col-gen {{ color: #185FA5; font-weight: bold; }}
.col-sms {{ color: #3B6D11; font-weight: bold; }}
.col-mak {{ color: #534AB7; font-weight: bold; }}
.anom {{ background: #FAEEDA !important; color: #854F0B !important; font-weight: bold; }}
.good {{ color: {AE_GREEN}; font-weight: bold; }}
.warn {{ color: {AE_GOLD}; font-weight: bold; }}
.bad  {{ color: {AE_RED};  font-weight: bold; }}
.kpi-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 6pt; margin-bottom: 10pt; }}
.kpi {{ border: 1pt solid {AE_LGREY}; padding: 6pt 8pt; }}
.kpi .lbl {{ font-size: 7pt; color: {AE_GREY}; }}
.kpi .val {{ font-size: 18pt; font-weight: bold; margin: 1pt 0; }}
.kpi .sub {{ font-size: 7pt; color: {AE_GREY}; }}
.chip {{ display: inline-block; padding: 1pt 5pt; border-radius: 3pt; font-size: 7pt; font-weight: bold; }}
.chip-r {{ background: #FCEBEB; color: #A32D2D; }}
.chip-a {{ background: #FAEEDA; color: #854F0B; }}
.chip-g {{ background: #EAF3DE; color: #3B6D11; }}
.chip-b {{ background: #E6F1FB; color: #185FA5; }}
.missing-chips {{ display: flex; flex-wrap: wrap; gap: 3pt; margin: 3pt 0; }}
.missing-chip {{ background: #FCEBEB; color: #A32D2D; padding: 2pt 6pt; border-radius: 3pt; font-size: 7pt; font-weight: bold; }}
.anom-banner {{ background: #FAEEDA; border: 0.5pt solid #EF9F27; padding: 5pt 8pt; margin-top: 4pt; font-size: 8pt; color: #633806; }}
.footer-note {{ font-size: 7pt; color: {AE_GREY}; margin-top: 4pt; }}
.page-break {{ page-break-after: always; }}
.legend {{ background: #F5F5F5; border: 0.5pt solid {AE_LGREY}; padding: 5pt 8pt; margin-bottom: 8pt; font-size: 7.5pt; }}
"""

TEMPLATE_SRC = """
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>{{ css }}</style></head><body>

<div class="header-block">
  <div class="vessel">PMS Data Sufficiency Report — {{ vessel_name }}</div>
  <div class="meta">Generated: {{ report_date }}  ·  Total jobs analysed: {{ total_jobs }}  ·  Anglo-Eastern Ship Management Ltd</div>
</div>

<h1>Go-Live Readiness Scorecard</h1>
<div class="kpi-grid">
  <div class="kpi"><div class="lbl">Overall readiness</div>
    <div class="val {% if sc.overall >= 90 %}good{% elif sc.overall >= 75 %}warn{% else %}bad{% endif %}">{{ sc.overall }}%</div></div>
  <div class="kpi"><div class="lbl">Equipment completeness</div>
    <div class="val {% if sc.equipment_completeness >= 90 %}good{% elif sc.equipment_completeness >= 75 %}warn{% else %}bad{% endif %}">{{ sc.equipment_completeness }}%</div>
    <div class="sub">{{ missing_count }} missing machineries</div></div>
  <div class="kpi"><div class="lbl">SMS job coverage</div>
    <div class="val {% if sc.sms_coverage >= 90 %}good{% elif sc.sms_coverage >= 75 %}warn{% else %}bad{% endif %}">{{ sc.sms_coverage }}%</div></div>
  <div class="kpi"><div class="lbl">Rank compliance</div>
    <div class="val {% if sc.rank_compliance >= 99 %}good{% elif sc.rank_compliance >= 95 %}warn{% else %}bad{% endif %}">{{ sc.rank_compliance }}%</div></div>
  <div class="kpi"><div class="lbl">Duplicate ratio</div>
    <div class="val {% if sc.duplicate_ratio >= 98 %}good{% elif sc.duplicate_ratio >= 90 %}warn{% else %}bad{% endif %}">{{ sc.duplicate_ratio }}%</div></div>
  <div class="kpi"><div class="lbl">Critical jobs configured</div>
    <div class="val good">{{ sc.critical_jobs_configured }}</div></div>
</div>

<h2>System Coverage Overview</h2>
<table>
  <tr><th>System</th><th>Coverage</th><th>Missing</th><th>Status</th></tr>
  {% for row in system_coverage %}
  <tr>
    <td>{{ row.system }}</td>
    <td>{{ row.coverage_pct }}%</td>
    <td>{{ row.missing }}</td>
    <td><span class="chip {% if row.status == 'Good' %}chip-g{% elif row.status == 'Review' %}chip-a{% else %}chip-r{% endif %}">{{ row.status }}</span></td>
  </tr>
  {% endfor %}
</table>

{% if include_raw %}
<h2>Critical Machinery Jobs ({{ crit_total }} total)</h2>
<div class="legend">Column key: <span style="color:#185FA5;font-weight:bold">Generic</span> · <span style="color:#3B6D11;font-weight:bold">SMS</span> · <span style="color:#534AB7;font-weight:bold">Maker/IM</span></div>
<table>
  <tr><th>Machinery</th><th>Generic</th><th>SMS</th><th>Maker</th><th>Total</th></tr>
  {% for row in critical_jobs %}
  <tr>
    <td>{{ row.machinery }}</td>
    <td class="col-gen">{{ row.generic or '—' }}</td>
    <td class="col-sms">{{ row.sms or '—' }}</td>
    <td class="col-mak">{{ row.maker or '—' }}</td>
    <td><strong>{{ row.total }}</strong></td>
  </tr>
  {% endfor %}
  <tr class="tot"><td>Total</td>
    <td class="col-gen">{{ crit_generic }}</td>
    <td class="col-sms">{{ crit_sms }}</td>
    <td class="col-mak">{{ crit_maker }}</td>
    <td>{{ crit_total }}</td>
  </tr>
</table>
{% endif %}

<h2>ME Cylinder Unit Completeness ({{ n_cylinders }} × 8 = {{ n_cylinders * 8 }} jobs)</h2>
<table>
  <tr><th>Unit</th>{% for sc in me.sub_components %}<th>{{ sc[:8] }}</th>{% endfor %}<th>Total</th></tr>
  {% for unit in me.units %}
  <tr>
    <td>{{ unit.replace('Cylinder Unit#', '#') }}</td>
    {% for sc in me.sub_components %}
    <td class="{% if unit in me.anomalies[sc] %}anom{% endif %}">{{ me.table[unit][sc] }}</td>
    {% endfor %}
    <td class="{% if me.table[unit]['Total'] != me.grand_total // me.units|length %}anom{% else %}good{% endif %}">
      {{ me.table[unit]['Total'] }}</td>
  </tr>
  {% endfor %}
  <tr class="tot"><td>Total</td>
    {% for sc in me.sub_components %}
    <td class="{% if me.anomalies[sc] %}anom{% endif %}">{{ me.totals[sc] }}</td>
    {% endfor %}
    <td>{{ me.grand_total }}</td>
  </tr>
</table>
{% if include_anomalies %}
{% for sc, units in me.anomalies.items() %}{% if units %}
<div class="anom-banner">⚠ {{ sc }}: inconsistent counts across {{ units|join(', ') }}</div>
{% endif %}{% endfor %}
{% endif %}

<h2>AE Sub-component Completeness ({{ ae.engines|length }} engines)</h2>
<table>
  <tr><th>Sub-component</th>{% for e in ae.engines %}<th>{{ e.replace('Auxiliary Engine#','AE #') }}</th>{% endfor %}<th>Total</th></tr>
  {% for sc in ae.sub_components %}
  <tr>
    <td>{{ sc }}</td>
    {% for e in ae.engines %}
    <td class="{% if e in ae.anomalies[sc] %}anom{% endif %}">{{ ae.table[e][sc] }}</td>
    {% endfor %}
    <td class="{% if ae.anomalies[sc] %}anom{% else %}good{% endif %}">{{ ae.totals[sc] }}</td>
  </tr>
  {% endfor %}
  <tr class="tot"><td>Grand total</td>
    {% for e in ae.engines %}
    <td>{{ ae.table[e]['Total'] }}</td>
    {% endfor %}
    <td>{{ ae.grand_total }}</td>
  </tr>
</table>

<div class="page-break"></div>

<h2>19 Missing Machineries</h2>
<div class="missing-chips">
{% for m in missing_machineries %}<span class="missing-chip">{{ m }}</span>{% endfor %}
</div>

<h2>Performing Rank Violations</h2>
<table>
  <tr><th>Violation type</th><th>Count</th></tr>
  <tr><td>Engine dept jobs → Chief Officer</td><td>{{ rank.engine_to_co }}</td></tr>
  <tr><td>Engine dept jobs → Master</td><td>{{ rank.engine_to_master }}</td></tr>
  <tr><td>Engine dept jobs → 3rd Officer</td><td>{{ rank.engine_to_3o }}</td></tr>
  <tr><td>Electrical jobs → Deck Officers</td><td>{{ rank.electrical_to_deck }}</td></tr>
  <tr class="tot"><td>Total violations</td><td>{{ rank.total }}</td></tr>
</table>

{% if include_raw %}
<h2>Duplicate Job Analysis ({{ dup_total }} total)</h2>
<table>
  <tr><th>Machinery</th><th>Duplicates</th><th>Severity</th></tr>
  {% for row in duplicate_jobs %}
  <tr>
    <td>{{ row.machinery }}</td>
    <td>{{ row.duplicates }}</td>
    <td><span class="chip {% if row.severity == 'Critical' %}chip-r{% elif row.severity == 'High' %}chip-a{% elif row.severity == 'Medium' %}chip-b{% else %}chip-g{% endif %}">{{ row.severity }}</span></td>
  </tr>
  {% endfor %}
</table>
{% endif %}

<div class="footer-note">This report was automatically generated by the PMS Data Sufficiency Check tool · Anglo-Eastern Digital Solutions · {{ report_date }}</div>

</body></html>
"""


def build_pdf(
    results: dict,
    vessel_name: str,
    report_date: str,
    include_raw: bool = True,
    include_anomalies: bool = True,
) -> bytes:
    """Render results to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint not installed. Run: pip install weasyprint --break-system-packages")

    sc = results["scorecard"]
    me = results["me_unit_completeness"]
    ae = results["ae_subcomponent_completeness"]
    crit = results["critical_machinery_jobs"]
    rank = results["rank_violations"]
    dups = results["duplicate_jobs"]
    missing = results["missing_machineries"]
    sys_cov = results["system_coverage"]

    crit_generic = sum(r["generic"] for r in crit)
    crit_sms     = sum(r["sms"]     for r in crit)
    crit_maker   = sum(r["maker"]   for r in crit)
    crit_total   = sum(r["total"]   for r in crit)
    dup_total    = sum(r["duplicates"] for r in dups)
    n_cylinders  = len(me.get("units", []))

    html_str = Template(TEMPLATE_SRC).render(
        css=CSS,
        vessel_name=vessel_name,
        report_date=report_date,
        total_jobs=sc.get("total_jobs", 0),
        sc=sc,
        me=me,
        ae=ae,
        critical_jobs=crit,
        crit_generic=crit_generic,
        crit_sms=crit_sms,
        crit_maker=crit_maker,
        crit_total=crit_total,
        missing_machineries=missing,
        missing_count=len(missing),
        rank=rank,
        duplicate_jobs=dups,
        dup_total=dup_total,
        system_coverage=sys_cov,
        n_cylinders=n_cylinders,
        include_raw=include_raw,
        include_anomalies=include_anomalies,
    )

    pdf_bytes = HTML(string=html_str).write_pdf()
    return pdf_bytes
