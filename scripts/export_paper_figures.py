"""Export the six paper figures as SVG and, with rsvg-convert, PNG."""

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
POINT_COLOR = '#2c7fb8'
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


def point_legend(y, x=55):
    return [f'<circle cx="{x}" cy="{y-5}" r="6" fill="{POINT_COLOR}"/>',
            text(x+14, y, 'One CoC', 15)]


def population_data(summary):
    data = summary[['coc_number', 'coc_name', 'run_count',
                    'total_population_2024', 'pit_total_2024',
                    'mean_absolute_percent_error', 'gmd_percent']].copy()
    data = data.rename(columns={'gmd_percent': 'relative_gmd_percent'})
    data['ln_population'] = np.log(data.total_population_2024)
    data['ln1p_mean_absolute_percent_error'] = np.log1p(data.mean_absolute_percent_error)
    data['ln1p_relative_gmd'] = np.log1p(data.relative_gmd_percent)
    return data.sort_values('coc_number')


def heatmap_figure(summary):
    runs = pd.read_csv(ROOT / 'data/processed/ai_estimate_run_errors_2024.csv')
    assert len(runs) == 2200 and set(runs.coc_number) == set(summary.coc_number)
    ordered = summary.sort_values('coc_number')
    width, top, step, tile_left, tile_width = 1525, 155, 48, 780, 14
    bottom = top + len(ordered)*step

    def color(error):
        if error == 0:
            return RAMP[2]
        stops = RAMP[2::-1] if error < 0 else RAMP[2:]
        position = np.sqrt(min(abs(error), 100)/100)*2
        index = min(int(position), 1)
        fraction = position-index
        start, end = stops[index:index+2]
        channels = [int(np.floor(int(start[i:i+2], 16)*(1-fraction)
                                 + int(end[i:i+2], 16)*fraction + .5))
                    for i in (1, 3, 5)]
        return '#'+''.join(f'{channel:02x}' for channel in channels)

    elements = []
    for label, sign, left in [('Underestimate', -1, 40), ('Overestimate', 1, 410)]:
        elements.append(text(left, 25, label, 28, weight=700))
        for i in range(200):
            fraction = i/199
            elements.append(f'<rect x="{left+i*1.4:.2f}" y="35" width="1.6" height="15" '
                            f'fill="{color(sign*fraction**2*100)}"/>')
        for value in (0, 25, 100):
            elements.append(text(left+np.sqrt(value/100)*280, 71,
                                 f'{sign*value}%', 25, anchor='middle'))
    elements += [f'<rect x="780" y="35" width="16" height="16" fill="{RAMP[2]}"/>',
                 text(805, 49, 'Exact match', 27)]
    for x, label, anchor in [(40, 'CoC', 'start'), (240, 'Actual PIT', 'end'),
                             (430, 'Mean estimate', 'end'), (540, 'Under', 'end'),
                             (640, 'Exact', 'end'), (740, 'Over', 'end')]:
        elements.append(text(x, 120, label, 26, anchor=anchor, weight=700))
    elements.append(text(tile_left, 110, '50 responses, sorted from lowest to highest error →', 27, weight=700))
    for rank in (1, 10, 25, 50):
        elements.append(text(tile_left+(rank-.5)*tile_width, 137, rank, 24, anchor='middle'))
    for index, row in enumerate(ordered.itertuples()):
        responses = runs.loc[runs.coc_number == row.coc_number].copy()
        assert len(responses) == 50 and responses.run.nunique() == 50
        assert responses.pit_total_2024.eq(row.pit_total_2024).all()
        responses['error'] = 100*(responses.estimated_pit_total_2024-row.pit_total_2024)/row.pit_total_2024
        responses = responses.sort_values(['error', 'run'])
        assert np.isfinite(responses.error).all()
        under = 100*responses.error.lt(0).mean()
        over = 100*responses.error.gt(0).mean()
        exact = 100*responses.error.eq(0).mean()
        y = top+index*step
        elements.append(f'<g class="heatmap-row" data-coc="{row.coc_number}">')
        if index % 2 == 0:
            elements.append(f'<rect x="30" y="{y}" width="1465" height="{step}" fill="#f8fafc"/>')
        wrapped = [row.coc_number]
        for j, part in enumerate(wrapped):
            elements.append(text(40, y+step/2+4+(j-(len(wrapped)-1)/2)*12, part, 23))
        for x, value in [(240, number(row.pit_total_2024)), (430, number(row.mean_estimate)),
                         (540, number(under, 2)+'%'), (640, number(exact, 2)+'%'),
                         (740, number(over, 2)+'%')]:
            elements.append(text(x, y+step/2+4, value, 24, anchor='end'))
        for rank, response in enumerate(responses.itertuples()):
            tooltip = (f'{row.coc_number}, original run {response.run}, '
                       f'estimate {number(response.estimated_pit_total_2024)}, '
                       f'signed error {number(response.error, 2)}%')
            elements.append(f'<rect class="error-tile" x="{tile_left+rank*tile_width}" '
                            f'y="{y+12}" width="12" height="24" rx="1" '
                            f'fill="{color(response.error)}" data-error="{response.error}" '
                            f'data-run="{response.run}"><title>{escape(tooltip)}</title></rect>')
        elements += [line(30, y+step, 1495, y+step, '#e5eaf0'), '</g>']
    return svg(width, bottom+15, 'Sorted percentage-error heatmap for 44 CoCs and 50 runs per CoC', elements)


def population_figure(summary):
    data = population_data(summary)
    xv = data.ln_population.to_numpy()
    xmin, xmax = np.floor(xv.min()*2)/2, np.ceil(xv.max()*2)/2
    left, right = 100, 1060
    x = lambda value: left+(value-xmin)/(xmax-xmin)*(right-left)
    elements = []
    panels = [('Population and accuracy', 'ln1p_mean_absolute_percent_error',
               'ln(1 + mean absolute error %)'),
              ('Population and consistency', 'ln1p_relative_gmd',
               'ln(1 + relative GMD)')]
    for index, (label, column, ylabel) in enumerate(panels):
        offset = index*620
        top, bottom = offset+125, offset+535
        yv = data[column].to_numpy()
        ymax = np.ceil(yv.max()*2)/2
        y = lambda value: bottom-value/ymax*(bottom-top)
        result = pearsonr(xv, yv)
        slope, intercept = np.polyfit(xv, yv, 1)
        mantissa, exponent = f'{result.pvalue:.2e}'.split('e')
        elements.append(text(40, offset+30, f'{"AB"[index]}. {label}', 22, weight=700))
        elements.append(f'<text x="40" y="{offset+62}" font-size="20" fill="#334155">'
                        f'Pearson r = {result.statistic:.3f}, p = {mantissa} × 10'
                        f'<tspan dy="-8" font-size="17">{int(exponent)}</tspan>'
                        '<tspan dy="8" font-size="20">, n = 44 CoCs</tspan></text>')
        elements += point_legend(offset+95, 48)
        elements += [line(755, offset+90, 795, offset+90, '#172033', 2.5),
                     text(804, offset+95, 'Linear best-fit line', 15)]
        for tick in np.arange(0, ymax+.01, .5):
            elements += [line(left, y(tick), right, y(tick)),
                         text(left-12, y(tick)+5, number(tick), 14, anchor='end')]
        for tick in np.arange(xmin, xmax+.01, .5):
            elements += [line(x(tick), bottom, x(tick), bottom+6, '#526070'),
                         text(x(tick), bottom+25, number(tick), 14, anchor='middle')]
        elements += [line(left, top, left, bottom, '#526070'),
                     line(left, bottom, right, bottom, '#526070'),
                     line(x(xv.min()), y(intercept+slope*xv.min()),
                          x(xv.max()), y(intercept+slope*xv.max()), '#172033', 2.5)]
        for row, px, py in zip(data.itertuples(), xv, yv):
            elements.append(f'<circle cx="{x(px):.3f}" cy="{y(py):.3f}" r="6" '
                            f'fill="{POINT_COLOR}" fill-opacity="0.8" stroke="white"/>')
        elements += [text((left+right)/2, bottom+60, 'ln(population)', 18, anchor='middle'),
                     text(0, 0, ylabel, 18, anchor='middle',
                          extra=f'transform="translate(26 {(top+bottom)/2}) rotate(-90)"')]
    return svg(1100, 1230, 'Population, accuracy, and consistency across 44 CoCs', elements)


def map_figure(summary):
    frame = gpd.read_file(ROOT / 'data/processed/ca_coc_organizations_boundaries_pit_hic_2024.geojson').to_crs(3310)
    indexed = summary.set_index('coc_number')
    assert len(frame) == 44 and set(frame.COCNUM) == set(indexed.index)
    minx, miny, maxx, maxy = frame.total_bounds
    scale = min(750/(maxx-minx), 790/(maxy-miny))
    offset = (900-(maxx-minx)*scale)/2

    def point(x, y):
        return offset+(x-minx)*scale, 15+(maxy-y)*scale

    panels = [
        ('mean_signed_percent_error', 'A. Mean signed percentage error', RAMP),
        ('mean_absolute_percent_error', 'B. Mean absolute percentage error',
         ['#fff7bc', '#7fcdbb', '#41b6c4', '#2c7fb8', '#253494'])
    ]
    elements = []
    for panel, (metric, label, ramp) in enumerate(panels):
        values = indexed[metric]
        if metric == 'mean_signed_percent_error':
            low, high = max(values.min(), -100), min(values.max(), 100)
            stops = np.array([low, low/2, 0, high/2, high])
        else:
            stops = np.quantile(values, [0, .25, .5, .75, 1])
        rgb = np.array([[int(c[i:i+2], 16) for i in (1, 3, 5)] for c in ramp])

        def color(value):
            channels = [int(round(np.interp(value, stops, rgb[:, i]))) for i in range(3)]
            return '#'+''.join(f'{channel:02x}' for channel in channels)

        elements.append(f'<g data-metric="{metric}" transform="translate({panel*900} 0)">')
        for row in frame.itertuples():
            geometry = row.geometry.simplify(100, preserve_topology=True)
            polygons = [geometry] if geometry.geom_type == 'Polygon' else geometry.geoms
            segments = []
            for polygon in polygons:
                for ring in [polygon.exterior, *polygon.interiors]:
                    coordinates = [point(*p[:2]) for p in ring.coords]
                    segments.append('M'+' L'.join(f'{x:.2f},{y:.2f}' for x, y in coordinates)+' Z')
            elements.append(f'<path data-coc="{row.COCNUM}" data-value="{values[row.COCNUM]}" '
                            f'd="{" ".join(segments)}" fill="{color(values[row.COCNUM])}" '
                            'fill-rule="evenodd" stroke="#526070" stroke-width="0.65"/>')
        for code, city in [('CA-501', 'San Francisco'), ('CA-503', 'Sacramento'),
                           ('CA-600', 'Los Angeles'), ('CA-601', 'San Diego')]:
            geometry = frame.loc[frame.COCNUM == code].geometry.iloc[0]
            center = geometry.representative_point()
            x, y = point(center.x, center.y)
            elements.append(text(x+5, y, city, 12, color='#172033', extra='paint-order="stroke" stroke="white" stroke-width="3" stroke-linejoin="round"'))
        elements.append(text(105, 846, label, 18, weight=700))
        # Each panel uses its own labeled scale, matching the dashboard map.
        for i in range(300):
            value = np.interp(i/299*4, range(5), stops)
            elements.append(f'<rect x="{105+i*2.3:.2f}" y="864" width="2.5" height="18" fill="{color(value)}"/>')
        for i, value in enumerate(stops):
            elements.append(text(105+i*172.5, 905, number(value, 2)+'%', 14, anchor='middle'))
        elements.append('</g>')
    return svg(1800, 925, 'Geographic distribution of mean signed and absolute percentage error', elements)

def gmd_figure(summary):
    ordered = summary.sort_values(['gmd_percent', 'coc_number'], ascending=[False, True])
    width, height, left, right, top, step = 710, 1370, 110, 610, 75, 29
    maximum = float(np.ceil(ordered.gmd_percent.max()/5)*5)
    x = lambda value: left+value/maximum*(right-left)
    bottom = top+44*step
    elements = point_legend(30, 45)
    elements.append(text(right, 30, 'Relative GMD (%)', 23, anchor='end'))
    for tick in np.arange(0, maximum+0.01, 5):
        elements += [line(x(tick), top-5, x(tick), bottom), text(x(tick), top-16, number(tick, 2)+'%', 20, anchor='middle')]
    for index, row in enumerate(ordered.itertuples()):
        y = top+index*step+step/2
        label = row.coc_number
        wrapped = textwrap.wrap(label, width=76)
        for j, part in enumerate(wrapped):
            elements.append(text(left-13, y+4+(j-(len(wrapped)-1)/2)*12, part, 18, anchor='end'))
        if row.gmd_percent:
            elements.append(f'<rect x="{left}" y="{y-8}" width="{x(row.gmd_percent)-left:.3f}" height="16" rx="2" fill="{POINT_COLOR}"/>')
        else:
            elements.append(f'<circle cx="{left}" cy="{y}" r="3" fill="{POINT_COLOR}"/>')
        elements.append(text(x(row.gmd_percent)+7, y+4, number(row.gmd_percent, 2)+'%', 19))
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
    elements += point_legend(65, 48)
    elements += [line(755, 60, 795, 60, '#172033', 2.5), text(804, 65, 'Linear best-fit line', 15)]
    for tick in np.arange(0, ymax+0.01, .5):
        elements += [line(left, y(tick), right, y(tick)), text(left-12, y(tick)+5, number(tick), 14, anchor='end')]
    for tick in np.arange(0, xmax+0.01, .5):
        elements += [line(x(tick), bottom, x(tick), bottom+6, '#526070'), text(x(tick), bottom+25, number(tick), 14, anchor='middle')]
    elements += [line(left, top, left, bottom, '#526070'), line(left, bottom, right, bottom, '#526070')]
    elements.append(line(x(xv.min()), y(intercept+slope*xv.min()), x(xv.max()), y(intercept+slope*xv.max()), '#172033', 2.5))
    for (_, row), px, py in zip(summary.iterrows(), xv, yv):
        elements.append(f'<circle cx="{x(px):.3f}" cy="{y(py):.3f}" r="6" fill="{POINT_COLOR}" fill-opacity="0.8" stroke="white"/>')
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
    figures = {'figure_1_signed_absolute_percentage_error_maps': map_figure,
               'figure_2_gmd_by_coc': gmd_figure,
               'figure_3_sorted_error_heatmap': heatmap_figure,
               'figure_4_population_accuracy_consistency': population_figure,
               'figure_5_consistency_accuracy': correlation_figure,
               'figure_6_exploratory_media_analysis': media_figure}
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
