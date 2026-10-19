"""Export the four paper figures as SVG and, with rsvg-convert, PNG."""

from pathlib import Path
from html import escape
import argparse
import shutil
import subprocess
import textwrap

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


ROOT = Path(__file__).resolve().parents[1]
COLORS = {'Major City': '#253494', 'Urban': '#2c7fb8',
          'Suburban': '#168c83', 'Rural': '#bd8736'}
RAMP = ['#253494', '#41b6c4', '#fff7bc', '#dd1c77', '#7a0177']


def number(value, decimals=3):
    return f'{value:,.{decimals}f}'.rstrip('0').rstrip('.') if decimals else f'{value:,.0f}'


def text(x, y, value, size=16, anchor='start', color='#334155', weight=400, extra=''):
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{color}" font-weight="{weight}" {extra}>{escape(str(value))}</text>')


def line(x1, y1, x2, y2, color='#dbe1e8', width=1, extra=''):
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{color}" stroke-width="{width}" {extra}/>')


def svg(width, height, title, elements):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img"><title>{escape(title)}</title>'
            '<style>text{font-family:Arial,Helvetica,sans-serif}</style>'
            f'<rect width="{width}" height="{height}" fill="white"/>' + ''.join(elements) + '</svg>\n')


def category_legend(y, x=55):
    elements = []
    for i, (category, color) in enumerate(COLORS.items()):
        cx = x + i * 170
        elements += [f'<circle cx="{cx}" cy="{y-5}" r="6" fill="{color}"/>',
                     text(cx+14, y, category, 15)]
    return elements


def map_figure(summary):
    frame = gpd.read_file(ROOT / 'data/processed/ca_coc_organizations_boundaries_pit_hic_2024.geojson').to_crs(3310)
    values = summary.set_index('coc_number').mean_signed_percent_error
    assert len(frame) == 44 and set(frame.COCNUM) == set(values.index)
    stops = np.array([max(values.min(), -100), max(values.min(), -100)/2,
                      0, min(values.max(), 100)/2, min(values.max(), 100)])
    rgb = np.array([[int(c[i:i+2], 16) for i in (1, 3, 5)] for c in RAMP])

    def color(value):
        channels = [int(round(np.interp(value, stops, rgb[:, i]))) for i in range(3)]
        return '#'+''.join(f'{channel:02x}' for channel in channels)

    minx, miny, maxx, maxy = frame.total_bounds
    scale = min(750/(maxx-minx), 790/(maxy-miny))
    offset = (900-(maxx-minx)*scale)/2

    def point(x, y):
        return offset+(x-minx)*scale, 15+(maxy-y)*scale

    elements = []
    for row in frame.itertuples():
        geometry = row.geometry.simplify(100, preserve_topology=True)
        polygons = [geometry] if geometry.geom_type == 'Polygon' else geometry.geoms
        segments = []
        for polygon in polygons:
            for ring in [polygon.exterior, *polygon.interiors]:
                coordinates = [point(*p[:2]) for p in ring.coords]
                segments.append('M'+' L'.join(f'{x:.2f},{y:.2f}' for x, y in coordinates)+' Z')
        elements.append(f'<path d="{" ".join(segments)}" fill="{color(values[row.COCNUM])}" '
                        'fill-rule="evenodd" stroke="#526070" stroke-width="0.65"/>')
    for code, label in [('CA-501', 'San Francisco'), ('CA-503', 'Sacramento'),
                        ('CA-600', 'Los Angeles'), ('CA-601', 'San Diego')]:
        geometry = frame.loc[frame.COCNUM == code].geometry.iloc[0]
        center = geometry.representative_point()
        x, y = point(center.x, center.y)
        elements.append(text(x+5, y, label, 12, color='#172033', extra='paint-order="stroke" stroke="white" stroke-width="3" stroke-linejoin="round"'))
    elements += [text(105, 846, 'Mean signed percentage error', 16, weight=700)]
    # Equal-width segments match the dashboard's five legend labels.
    for i in range(300):
        position = i/299*4
        value = np.interp(position, range(5), stops)
        elements.append(f'<rect x="{105+i*2.3:.2f}" y="864" width="2.5" height="18" fill="{color(value)}"/>')
    for i, value in enumerate(stops):
        elements.append(text(105+i*172.5, 905, number(value, 2)+'%', 14, anchor='middle'))
    return svg(900, 925, 'Mean signed percentage error map', elements)


def gmd_figure(summary):
    ordered = summary.sort_values(['gmd_percent', 'coc_number'], ascending=[False, True])
    width, height, left, right, top, step = 1200, 1370, 590, 1090, 75, 29
    maximum = float(np.ceil(ordered.gmd_percent.max()/5)*5)
    x = lambda value: left+value/maximum*(right-left)
    bottom = top+44*step
    elements = category_legend(30, 45)
    elements.append(text(right, 30, 'Relative GMD (%)', 16, anchor='end'))
    for tick in np.arange(0, maximum+0.01, 5):
        elements += [line(x(tick), top-5, x(tick), bottom), text(x(tick), top-16, number(tick, 2)+'%', 13, anchor='middle')]
    for index, row in enumerate(ordered.itertuples()):
        y = top+index*step+step/2
        label = f'{row.coc_number}, {row.coc_name}'
        wrapped = textwrap.wrap(label, width=76)
        for j, part in enumerate(wrapped):
            elements.append(text(left-13, y+4+(j-(len(wrapped)-1)/2)*12, part, 11, anchor='end'))
        if row.gmd_percent:
            elements.append(f'<rect x="{left}" y="{y-8}" width="{x(row.gmd_percent)-left:.3f}" height="16" rx="2" fill="{COLORS[row.coc_category]}"/>')
        else:
            elements.append(f'<circle cx="{left}" cy="{y}" r="3" fill="{COLORS[row.coc_category]}"/>')
        elements.append(text(x(row.gmd_percent)+7, y+4, number(row.gmd_percent, 2)+'%', 12))
    return svg(width, height, 'Ranked relative GMD values for 44 CoCs', elements)


def correlation_figure(summary):
    xv = np.log1p(summary.gmd_percent.to_numpy())
    yv = np.log1p(summary.mean_absolute_percent_error.to_numpy())
    result = pearsonr(xv, yv)
    mantissa, exponent = f'{result.pvalue:.2e}'.split('e')
    slope, intercept = np.polyfit(xv, yv, 1)
    width, height, left, right, top, bottom = 1100, 670, 95, 1060, 105, 590
    xmax, ymax = np.ceil(xv.max()*2)/2, np.ceil(yv.max()*2)/2
    x = lambda value: left+value/xmax*(right-left)
    y = lambda value: bottom-value/ymax*(bottom-top)
    elements = [
        '<text x="40" y="32" font-size="22" fill="#334155">'
        f'Pearson r = {result.statistic:.3f}, p = {mantissa} × 10'
        f'<tspan dy="-9" font-size="18">{int(exponent)}</tspan>'
        '<tspan dy="9" font-size="22">, n = 44 CoCs</tspan></text>'
    ]
    elements += category_legend(65, 48)
    elements += [line(755, 60, 795, 60, '#172033', 2.5), text(804, 65, 'Linear best-fit line', 15)]
    for tick in np.arange(0, ymax+0.01, .5):
        elements += [line(left, y(tick), right, y(tick)), text(left-12, y(tick)+5, number(tick), 14, anchor='end')]
    for tick in np.arange(0, xmax+0.01, .5):
        elements += [line(x(tick), bottom, x(tick), bottom+6, '#526070'), text(x(tick), bottom+25, number(tick), 14, anchor='middle')]
    elements += [line(left, top, left, bottom, '#526070'), line(left, bottom, right, bottom, '#526070')]
    elements.append(line(x(xv.min()), y(intercept+slope*xv.min()), x(xv.max()), y(intercept+slope*xv.max()), '#172033', 2.5))
    for (_, row), px, py in zip(summary.iterrows(), xv, yv):
        elements.append(f'<circle cx="{x(px):.3f}" cy="{y(py):.3f}" r="6" fill="{COLORS[row.coc_category]}" fill-opacity="0.8" stroke="white"/>')
    elements += [text((left+right)/2, 648, 'ln(1 + relative GMD)', 18, anchor='middle'),
                 text(0, 0, 'ln(1 + mean absolute error %)', 18, anchor='middle', extra=f'transform="translate(26 {(top+bottom)/2}) rotate(-90)"')]
    return svg(width, height, 'Log-transformed GMD and mean absolute percentage error', elements)


def media_figure(summary):
    data = pd.read_csv(ROOT / 'data/processed/coc_media_regression_data_2024.csv')
    models = pd.read_csv(ROOT / 'data/processed/coc_media_regression_model_metrics_2024.csv')
    test = pd.read_csv(ROOT / 'data/processed/coc_media_regression_tests_2024.csv').iloc[0]
    assert len(models) == 2 and len(data) == 44
    assert set(data.coc_number) == set(summary.coc_number)
    observed = data.log1p_absolute_percent_error.to_numpy()
    predictions = []
    for model in models.itertuples():
        predicted = (model.intercept + model.log_population_coefficient * data.log_population
                     + model.log_pit_total_coefficient * data.log_pit_total
                     + model.log1p_article_count_coefficient * data.log1p_article_count).to_numpy()
        r_squared = 1 - np.sum((observed-predicted)**2)/np.sum((observed-observed.mean())**2)
        assert np.isclose(r_squared, model.r_squared)
        predictions.append(predicted)
    combined = np.concatenate([observed, *predictions])
    low, high = np.floor(combined.min()*2)/2, np.ceil(combined.max()*2)/2
    left, right = 100, 1060
    x = lambda value: left + (value-low)/(high-low)*(right-left)
    elements = []

    def term(coefficient, label):
        sign = '−' if coefficient < 0 else '+'
        return f' {sign} {number(abs(coefficient))} {label}'

    for index, (model, predicted) in enumerate(zip(models.itertuples(), predictions)):
        offset = index*575
        top, bottom = offset+135, offset+490
        y = lambda value: bottom-(value-low)/(high-low)*(bottom-top)
        label = 'Population and PIT' if index == 0 else 'Population, PIT and articles'
        elements.append(text(40, offset+32, f'{"AB"[index]}. {label}, R² = {number(model.r_squared)}', 22, weight=700))
        equation = (f'ln(1 + mean absolute error %) = {number(model.intercept)}'
                    + term(model.log_population_coefficient, 'ln(population)')
                    + term(model.log_pit_total_coefficient, 'ln(actual PIT)'))
        elements.append(text(40, offset+66, equation, 16))
        if index:
            elements.append(text(315, offset+92, term(model.log1p_article_count_coefficient, 'ln(1 + article count)'), 16))
        for tick in np.arange(low, high+0.01, 1):
            elements += [line(left, y(tick), right, y(tick)),
                         text(left-12, y(tick)+5, number(tick), 14, anchor='end'),
                         line(x(tick), bottom, x(tick), bottom+6, '#526070'),
                         text(x(tick), bottom+25, number(tick), 14, anchor='middle')]
        elements += [line(left, top, left, bottom, '#526070'), line(left, bottom, right, bottom, '#526070'),
                     line(x(low), y(low), x(high), y(high), '#168c83', 2.5, 'stroke-dasharray="8 5"')]
        for actual, estimate in zip(observed, predicted):
            elements.append(f'<circle cx="{x(actual):.3f}" cy="{y(estimate):.3f}" r="5" fill="#2563eb" fill-opacity="0.75" stroke="white"/>')
        elements += [text((left+right)/2, bottom+58, 'Observed ln(1 + mean absolute error %)', 17, anchor='middle'),
                     text(0, 0, 'Predicted ln(1 + mean absolute error %)', 17, anchor='middle',
                          extra=f'transform="translate(27 {(top+bottom)/2}) rotate(-90)"')]
    elements += [f'<circle cx="48" cy="1157" r="6" fill="#2563eb"/>', text(63, 1162, 'One CoC', 16),
                 line(200, 1157, 250, 1157, '#168c83', 3, 'stroke-dasharray="8 5"'),
                 text(262, 1162, 'Exact agreement (predicted = observed)', 16),
                 text(40, 1202, f'ΔR² = {number(test.change_in_r_squared)}, F({test.numerator_df}, {test.denominator_df}) = {number(test.f_statistic)}, p = {number(test.p_value)}', 19)]
    return svg(1100, 1225, 'Exploratory media analysis: models without and with article count', elements)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'figures')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(ROOT / 'data/processed/ai_estimate_coc_summary_2024.csv')
    assert len(summary) == 44 and summary.run_count.eq(50).all()
    figures = {'figure_1_signed_percentage_error_map': map_figure,
               'figure_2_gmd_by_coc': gmd_figure,
               'figure_3_consistency_accuracy': correlation_figure,
               'figure_4_exploratory_media_analysis': media_figure}
    renderer = shutil.which('rsvg-convert')
    for name, build in figures.items():
        target = args.output_dir / f'{name}.svg'
        target.write_text(build(summary))
        print(target)
        if renderer:
            png = target.with_suffix('.png')
            subprocess.run([renderer, '--zoom', '3', '--output', str(png), str(target)], check=True)
            print(png)
    if not renderer:
        print('PNG export skipped: install rsvg-convert to rasterize the SVG files.')


if __name__ == '__main__':
    main()
