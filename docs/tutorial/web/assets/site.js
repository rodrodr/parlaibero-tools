/* ParlaIbero con un agente — language switch, contents rail, copy buttons and the charts (d3 7.8.5). */
(() => {
  const KEY = 'parlaibero-tutorial-lang';
  const blocks = { es: document.getElementById('lang-es'), en: document.getElementById('lang-en') };
  const buttons = document.querySelectorAll('[data-set-lang]');
  const narrow = matchMedia('(max-width: 959px)');
  let lang = null, current = null;

  function heads() { return blocks[lang].querySelectorAll('h2[id], h3[id]'); }
  function track() {
    let found = null;
    for (const h of heads()) { if (h.getBoundingClientRect().top < 150) found = h; else break; }
    current = found;
    blocks[lang].querySelectorAll('.toc a').forEach(a => a.classList.toggle('active', !!found && a.getAttribute('href') === '#' + found.id));
  }
  function setLang(l, keepPlace) {
    const place = keepPlace && current ? current.id.slice(3) : null;
    lang = l;
    for (const k in blocks) blocks[k].hidden = k !== l;
    document.documentElement.lang = l;
    document.title = document.documentElement.dataset['title' + (l === 'es' ? 'Es' : 'En')] || document.title;
    buttons.forEach(b => b.setAttribute('aria-pressed', String(b.dataset.setLang === l)));
    document.querySelectorAll('[data-href-es]').forEach(a => { a.href = a.dataset['href' + (l === 'es' ? 'Es' : 'En')]; });
    try { localStorage.setItem(KEY, l); } catch (e) {}
    drawAll();
    if (place) { const t = document.getElementById(l + '-' + place); if (t) t.scrollIntoView({ block: 'start', behavior: 'instant' }); }
    track();
  }

  /* ---------- charts ---------- */
  const fmtNum = (v, d = 1) => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = Math.abs(v) >= 1000 ? Math.round(v).toString() : v.toFixed(d);
    const [i, f] = s.split('.');
    const g = i.replace(/\B(?=(\d{3})+(?!\d))/g, lang === 'es' ? '.' : ',');
    return f ? g + (lang === 'es' ? ',' : '.') + f : g;
  };
  const col = c => `var(--${c || 'c1'})`;

  function tipFor(body) {
    let t = body.querySelector('.viz-tip');
    if (!t) { t = document.createElement('div'); t.className = 'viz-tip'; body.appendChild(t); }
    return {
      show(html, x, y) {
        t.innerHTML = html; t.classList.add('on');
        const w = body.clientWidth, tw = t.offsetWidth;
        t.style.left = Math.max(4, Math.min(w - tw - 4, x + 12)) + 'px';
        t.style.top = Math.max(4, y - 10) + 'px';
      },
      hide() { t.classList.remove('on'); }
    };
  }

  function multiples(el, s) {
    const grid = document.createElement('div'); grid.className = 'multiples'; el.appendChild(grid);
    const all = s.panels.flatMap(p => [...p.points, ...(p.points2 || [])].map(q => q[1]).filter(v => v !== null));
    const yMaxShared = d3.max(all) || 1;
    s.panels.forEach(p => {
      const box = document.createElement('div'); grid.appendChild(box);
      const peak = d3.max(p.points, q => q[1]) || 0, top = d3.max([...p.points, ...(p.points2 || [])], q => q[1]) || 0;
      box.innerHTML = `<div class="panel-h"><b>${p.label}</b><span>${p.sub || (s.peak_label ? s.peak_label + ' ' + fmtNum(peak, s.digits ?? 1) : '')}</span></div>`;
      const W = 200, H = 74, m = { t: 6, r: 4, b: 16, l: 4 };
      const x = d3.scaleLinear().domain(s.x_domain).range([m.l, W - m.r]);
      const y = d3.scaleLinear().domain([0, s.y_shared ? yMaxShared : (top || 1)]).range([H - m.b, m.t]);
      const svg = d3.select(box).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img')
        .attr('aria-label', `${p.label}: ${s.aria || ''}`);
      svg.append('line').attr('class', 'grid').attr('x1', m.l).attr('x2', W - m.r).attr('y1', H - m.b).attr('y2', H - m.b).style('stroke', 'var(--axis)');
      (s.y_grid || []).forEach(g => {
        if (g > y.domain()[1]) return;
        svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', y(g)).attr('y2', y(g)).style('stroke', 'var(--grid)');
        svg.append('text').attr('x', m.l).attr('y', y(g) - 2).text(fmtNum(g, 0) + (s.y_grid_unit || '')).style('font-size', '8px').attr('class', 'muted');
      });
      if (s.ref_x !== undefined) svg.append('line').attr('x1', x(s.ref_x)).attr('x2', x(s.ref_x)).attr('y1', m.t).attr('y2', H - m.b).style('stroke', 'var(--axis)').style('stroke-dasharray', '2 3');
      const ok = q => q[1] !== null && q[1] !== undefined;
      const area = d3.area().defined(ok).x(q => x(q[0])).y0(H - m.b).y1(q => y(q[1])).curve(s.step ? d3.curveStepAfter : d3.curveMonotoneX);
      const line = d3.line().defined(ok).x(q => x(q[0])).y(q => y(q[1])).curve(s.step ? d3.curveStepAfter : d3.curveMonotoneX);
      if (p.points2) svg.append('path').attr('d', line(p.points2)).style('fill', 'none').style('stroke', 'var(--fg3)').style('stroke-width', 1.2).style('stroke-dasharray', '3 2');
      if (!s.no_area) svg.append('path').attr('d', area(p.points)).style('fill', col(p.color || s.color || 'c1')).style('opacity', .14);
      svg.append('path').attr('d', line(p.points)).style('fill', 'none').style('stroke', col(p.color || s.color || 'c1')).style('stroke-width', 1.6);
      p.points.forEach((q, i) => {   // isolated points (a gap on both sides) would not show as a line
        const prev = p.points[i - 1], next = p.points[i + 1];
        if (ok(q) && !(prev && ok(prev)) && !(next && ok(next))) svg.append('circle').attr('cx', x(q[0])).attr('cy', y(q[1])).attr('r', 1.6).style('fill', col(p.color || s.color || 'c1'));
      });
      (p.marks || []).forEach(mk => {
        svg.append('circle').attr('cx', x(mk.x)).attr('cy', H - m.b).attr('r', 3).style('fill', 'var(--fg)').style('stroke', 'var(--sheet)').style('stroke-width', 1.5);
      });
      svg.append('text').attr('x', m.l).attr('y', H - 3).text(s.x_ticks ? s.x_ticks[0] : s.x_domain[0]).style('font-size', '9px');
      svg.append('text').attr('x', W - m.r).attr('y', H - 3).attr('text-anchor', 'end').text(s.x_ticks ? s.x_ticks[1] : s.x_domain[1]).style('font-size', '9px');
      const tip = tipFor(el), hair = svg.append('line').style('stroke', 'var(--fg3)').style('opacity', 0).attr('y1', m.t).attr('y2', H - m.b);
      svg.append('rect').attr('x', m.l).attr('y', 0).attr('width', W - m.l - m.r).attr('height', H - m.b).style('fill', 'transparent')
        .on('mousemove', ev => {
          const [mx] = d3.pointer(ev); const xv = Math.round(x.invert(mx));
          const q = p.points.find(r => r[0] === xv); if (!q) return;
          hair.attr('x1', x(xv)).attr('x2', x(xv)).style('opacity', .6);
          const er = el.getBoundingClientRect(), br = ev.target.getBoundingClientRect();
          const q2 = p.points2 ? p.points2.find(r => r[0] === xv) : null;
          const mk = (p.marks || []).find(r => r.x === xv);
          const val = ok(q) ? `${fmtNum(q[1], s.digits ?? 1)} ${s.unit || ''}` : (s.empty || '—');
          tip.show(`<b>${p.label} · ${s.x_fmt ? s.x_fmt.replace('{x}', xv) : xv}</b><br>${val}`
            + (q2 && ok(q2) && s.label2 ? `<br>${s.label2}: ${fmtNum(q2[1], s.digits ?? 1)} ${s.unit || ''}` : '')
            + (q[2] !== undefined && q[2] !== null && s.extra ? '<br>' + s.extra.replace('{v}', fmtNum(q[2], 0)) : '')
            + (mk && mk.label ? `<br><i>${mk.label}</i>` : ''),
            br.left - er.left + (mx / W) * br.width, br.top - er.top);
        })
        .on('mouseleave', () => { hair.style('opacity', 0); tip.hide(); });
    });
  }

  function lines(el, s) {
    const W = Math.max(320, el.clientWidth - 28), H = s.height || 300, m = { t: 12, r: 96, b: 28, l: 44 };
    const all = s.series.flatMap(r => r.points);
    const x = d3.scaleLinear().domain(s.x_domain || d3.extent(all, q => q[0])).range([m.l, W - m.r]);
    const y = d3.scaleLinear().domain([0, d3.max(all, q => q[1]) * 1.05]).nice().range([H - m.b, m.t]);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', s.aria || '');
    svg.append('g').attr('class', 'grid').selectAll('line').data(y.ticks(5)).join('line')
      .attr('x1', m.l).attr('x2', W - m.r).attr('y1', d => y(d)).attr('y2', d => y(d));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(Math.min(10, W / 70)).tickFormat(d => s.x_fmt ? s.x_fmt.replace('{x}', d) : d).tickSizeOuter(0));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(d => fmtNum(d, 0)).tickSize(0)).call(g => g.selectAll('text').attr('dx', -4));
    if (s.ref_x !== undefined) {
      svg.append('line').attr('x1', x(s.ref_x)).attr('x2', x(s.ref_x)).attr('y1', m.t).attr('y2', H - m.b).style('stroke', 'var(--fg3)').style('stroke-dasharray', '3 3');
      if (s.ref_label) svg.append('text').attr('x', x(s.ref_x) + 4).attr('y', m.t + 10).text(s.ref_label).attr('class', 'muted');
    }
    const line = d3.line().defined(q => q[1] !== null).x(q => x(q[0])).y(q => y(q[1])).curve(d3.curveMonotoneX);
    const ends = [];
    s.series.forEach(r => {
      svg.append('path').attr('d', line(r.points)).style('fill', 'none').style('stroke', col(r.color)).style('stroke-width', r.muted ? 1.2 : 2)
        .style('opacity', r.muted ? .7 : 1);
      const last = [...r.points].reverse().find(q => q[1] !== null);
      if (last && !r.muted) ends.push({ y: y(last[1]), x: x(last[0]), label: r.label, color: r.color });
    });
    ends.sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 13) ends[i].y = ends[i - 1].y + 13;
    ends.forEach(e => {
      svg.append('circle').attr('cx', e.x).attr('cy', e.y).attr('r', 3.2).style('fill', col(e.color));
      svg.append('text').attr('x', e.x + 7).attr('y', e.y + 4).attr('class', 'lab').text(e.label);
    });
    const tip = tipFor(el), hair = svg.append('line').attr('y1', m.t).attr('y2', H - m.b).style('stroke', 'var(--fg3)').style('opacity', 0);
    const xs = [...new Set(all.map(q => q[0]))].sort((a, b) => a - b);
    svg.append('rect').attr('x', m.l).attr('y', m.t).attr('width', W - m.l - m.r).attr('height', H - m.t - m.b).style('fill', 'transparent')
      .on('mousemove', ev => {
        const [mx, my] = d3.pointer(ev); const xv = xs[d3.bisectCenter(xs, x.invert(mx))];
        hair.attr('x1', x(xv)).attr('x2', x(xv)).style('opacity', .5);
        const rows = s.series.map(r => { const q = r.points.find(p => p[0] === xv); return q && q[1] !== null ? `<span style="color:${col(r.color)}">●</span> ${r.label}: ${fmtNum(q[1], s.digits ?? 1)}` : null; }).filter(Boolean);
        const rect = svg.node().getBoundingClientRect(), k = rect.width / W;
        tip.show(`<b>${s.x_fmt ? s.x_fmt.replace('{x}', xv) : xv}</b><br>${rows.join('<br>')}`, x(xv) * k + 14, my * k);
      })
      .on('mouseleave', () => { hair.style('opacity', 0); tip.hide(); });
  }

  function timeline(el, s) {
    const rowH = 26, W = Math.max(320, el.clientWidth - 28), m = { t: s.ref_label ? 24 : 8, r: 16, b: 26, l: 112 };
    const H = m.t + m.b + rowH * s.rows.length;
    const x = d3.scaleTime().domain(s.x_domain.map(d => new Date(d))).range([m.l, W - m.r]).clamp(true);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', s.aria || '');
    // a domain of a few months gets month ticks, named in the page's language
    const every = s.months ? d3.timeMonth.every(W < 560 ? 4 : 2) : d3.timeYear.every(W < 560 ? 4 : 2);
    const fmt = s.months ? d => s.months[d.getMonth()] + (d.getMonth() === 0 || W >= 560 ? ' ' + String(d.getFullYear()).slice(2) : '') : null;
    svg.append('g').attr('class', 'grid').selectAll('line').data(x.ticks(every)).join('line')
      .attr('x1', d => x(d)).attr('x2', d => x(d)).attr('y1', m.t).attr('y2', H - m.b);
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).ticks(every).tickFormat(fmt).tickSizeOuter(0));
    const tip = tipFor(el);
    if (s.ref_date) {
      const rx = x(new Date(s.ref_date));
      svg.append('line').attr('x1', rx).attr('x2', rx).attr('y1', 18).attr('y2', H - m.b).style('stroke', 'var(--fg3)').style('stroke-dasharray', '3 3');
      if (s.ref_label) svg.append('text').attr('x', rx).attr('y', 14).attr('text-anchor', rx > W * .6 ? 'end' : 'start').attr('dx', rx > W * .6 ? -4 : 4).attr('class', 'muted').text(s.ref_label);
    }
    s.rows.forEach((r, i) => {
      const cy = m.t + rowH * i + rowH / 2, cx = x(new Date(r.date));
      if (r.gap) {      // weeks without sittings
        const g0 = x(new Date(r.gap[0])), g1 = x(new Date(r.gap[1]));
        svg.append('rect').attr('x', g0).attr('y', cy - 5).attr('width', Math.max(1, g1 - g0)).attr('height', 10).attr('rx', 2)
          .style('fill', 'var(--grid)').style('stroke', 'var(--axis)').style('stroke-width', .5)
          .on('mousemove', () => { const k = svg.node().getBoundingClientRect().width / W; tip.show(r.gap_tip || '', g1 * k + 10, cy * k); })
          .on('mouseleave', () => tip.hide());
      }
      if (r.wrong) {
        const wx = x(new Date(r.wrong));
        svg.append('line').attr('x1', wx).attr('x2', cx).attr('y1', cy).attr('y2', cy).style('stroke', 'var(--fg3)').style('stroke-dasharray', '2 2');
        svg.append('circle').attr('cx', wx).attr('cy', cy).attr('r', 4.5).style('fill', 'var(--sheet)').style('stroke', 'var(--fg3)').style('stroke-width', 1.5)
          .on('mousemove', () => { const k = svg.node().getBoundingClientRect().width / W; tip.show(r.wrong_tip || '', wx * k + 10, cy * k); })
          .on('mouseleave', () => tip.hide());
      }
      svg.append('text').attr('x', m.l - 10).attr('y', cy + 4).attr('text-anchor', 'end').attr('class', 'lab').text(r.label);
      if (!r.wrong) svg.append('line').attr('x1', m.l).attr('x2', cx).attr('y1', cy).attr('y2', cy).style('stroke', 'var(--rule)');
      const rad = s.size ? 3 + 7 * Math.sqrt(r.value / s.size) : 5;
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', rad).style('fill', col(r.color || 'c1')).style('fill-opacity', .85).style('stroke', 'var(--sheet)').style('stroke-width', 1.5)
        .on('mousemove', ev => { const k = svg.node().getBoundingClientRect().width / W; tip.show(r.tip, cx * k + 10, cy * k); })
        .on('mouseleave', () => tip.hide());
      if (r.note) svg.append('text').attr('x', cx + rad + 6).attr('y', cy + 4).attr('class', 'muted').text(r.note);
    });
  }

  function dumbbell(el, s) {
    const rowH = 26, W = Math.max(320, el.clientWidth - 28), m = { t: 22, r: 64, b: 26, l: 112 };
    const H = m.t + m.b + rowH * s.rows.length;
    const x = (s.log ? d3.scaleLog() : d3.scaleLinear()).domain(s.domain).range([m.l, W - m.r]);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', s.aria || '');
    let ticks = s.ticks || x.ticks(W < 520 ? 3 : 6);
    if (s.ticks && W < 520) ticks = ticks.filter((_, i) => i % 2 === 0);   // room for every other label on a phone
    svg.append('g').attr('class', 'grid').selectAll('line').data(ticks).join('line').attr('x1', d => x(d)).attr('x2', d => x(d)).attr('y1', m.t - 6).attr('y2', H - m.b);
    svg.append('g').attr('class', 'axis').attr('transform', `translate(0,${H - m.b})`).call(d3.axisBottom(x).tickValues(ticks).tickFormat(d => s.pct ? Math.round(d * 100) + ' %' : fmtNum(d, d < 1 ? 1 : 0)).tickSizeOuter(0));
    svg.append('text').attr('x', W - m.r + 8).attr('y', m.t - 8).attr('class', 'muted').text(s.ratio_label || '');
    const tip = tipFor(el);
    s.rows.forEach((r, i) => {
      const cy = m.t + rowH * i + rowH / 2;
      svg.append('text').attr('x', m.l - 10).attr('y', cy + 4).attr('text-anchor', 'end').attr('class', 'lab').text(r.label);
      svg.append('line').attr('x1', x(r.a)).attr('x2', x(r.b)).attr('y1', cy).attr('y2', cy).style('stroke', 'var(--axis)').style('stroke-width', 3).style('stroke-linecap', 'round');
      svg.append('circle').attr('cx', x(r.a)).attr('cy', cy).attr('r', 5).style('fill', 'var(--sheet)').style('stroke', col(s.a_color || 'c0')).style('stroke-width', 2);
      svg.append('circle').attr('cx', x(r.b)).attr('cy', cy).attr('r', 5.5).style('fill', col(s.b_color || 'c1')).style('stroke', 'var(--sheet)').style('stroke-width', 1.5);
      if (r.ratio !== undefined) svg.append('text').attr('x', W - m.r + 8).attr('y', cy + 4).attr('class', r.ratio >= (s.ratio_ref ?? 1) ? 'lab-strong' : 'lab').text(fmtNum(r.ratio, s.ratio_digits ?? 2));
      svg.append('rect').attr('x', 0).attr('y', cy - rowH / 2).attr('width', W).attr('height', rowH).style('fill', 'transparent')
        .on('mousemove', ev => { const k = svg.node().getBoundingClientRect().width / W; tip.show(r.tip, Math.max(x(r.a), x(r.b)) * k + 10, cy * k); })
        .on('mouseleave', () => tip.hide());
    });
  }

  function diverging(el, s) {
    const W = Math.max(320, el.clientWidth - 28), rowH = 22, n = Math.max(s.left.items.length, s.right.items.length);
    const m = { t: 26, b: 8 }, H = m.t + m.b + rowH * n, mid = W / 2;
    const zmax = d3.max([...s.left.items, ...s.right.items], d => Math.abs(d[1]));
    const scale = items => d3.scaleLinear().domain([0, s.independent ? d3.max(items, d => Math.abs(d[1])) : zmax]).range([0, mid * 0.42]);
    const tip = tipFor(el);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', s.aria || '');
    svg.append('text').attr('x', mid - 8).attr('y', 14).attr('text-anchor', 'end').attr('class', 'lab-strong').text(s.left.title);
    svg.append('text').attr('x', mid + 8).attr('y', 14).attr('class', 'lab-strong').text(s.right.title);
    svg.append('line').attr('x1', mid).attr('x2', mid).attr('y1', m.t - 4).attr('y2', H - m.b).style('stroke', 'var(--axis)');
    const side = (items, dir, color) => { const len = scale(items); items.forEach((d, i) => {
      const cy = m.t + rowH * i + rowH / 2, L = len(Math.abs(d[1]));
      svg.append('rect').attr('x', dir < 0 ? mid - L : mid).attr('y', cy - 6).attr('width', L).attr('height', 12).attr('rx', 2).style('fill', col(color)).style('opacity', .8);
      svg.append('text').attr('x', dir < 0 ? mid - L - 6 : mid + L + 6).attr('y', cy + 4).attr('text-anchor', dir < 0 ? 'end' : 'start').attr('class', 'lab').text(d[0]);
      svg.append('rect').attr('x', dir < 0 ? 0 : mid).attr('y', cy - rowH / 2).attr('width', mid).attr('height', rowH).style('fill', 'transparent')
        .on('mousemove', () => { const k = svg.node().getBoundingClientRect().width / W; tip.show(`<b>${d[0]}</b><br>${s.value_label || ''} ${fmtNum(d[1], 1)}${d[2] ? '<br>' + d[2] : ''}`, (dir < 0 ? mid - L : mid + L) * k + 8, cy * k); })
        .on('mouseleave', () => tip.hide());
    }); };
    side(s.left.items, -1, s.left.color || 'c1');
    side(s.right.items, 1, s.right.color || 'c2');
  }

  function bars(el, s) {      // one bar per period: [label, value, extra]
    const W = Math.max(320, el.clientWidth - 28), H = s.height || 220, m = { t: 12, r: 8, b: 26, l: 40 };
    const x = d3.scaleBand().domain(s.bars.map(b => b[0])).range([m.l, W - m.r]).paddingInner(.18);
    const y = d3.scaleLinear().domain([0, d3.max(s.bars, b => b[1]) * 1.05]).nice().range([H - m.b, m.t]);
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('role', 'img').attr('aria-label', s.aria || '');
    svg.append('g').attr('class', 'grid').selectAll('line').data(y.ticks(4)).join('line')
      .attr('x1', m.l).attr('x2', W - m.r).attr('y1', d => y(d)).attr('y2', d => y(d));
    svg.append('g').attr('class', 'axis').attr('transform', `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickFormat(d => fmtNum(d, 0)).tickSize(0)).call(g => g.selectAll('text').attr('dx', -4));
    const ticks = s.ticks || {};
    Object.keys(ticks).forEach(k => {
      if (!x(k) && x(k) !== 0) return;
      svg.append('line').attr('x1', x(k) - 1).attr('x2', x(k) - 1).attr('y1', H - m.b).attr('y2', H - m.b + 5).style('stroke', 'var(--axis)');
      svg.append('text').attr('x', x(k) + 2).attr('y', H - 8).attr('class', 'muted').text(ticks[k]);
    });
    svg.append('line').attr('x1', m.l).attr('x2', W - m.r).attr('y1', H - m.b).attr('y2', H - m.b).style('stroke', 'var(--axis)');
    const tip = tipFor(el), bw = x.bandwidth(), r = Math.min(3, bw / 2);
    s.bars.forEach(b => {
      const bx = x(b[0]), by = y(b[1]), h = H - m.b - by;
      if (h > 0) svg.append('path').style('fill', col(s.color || 'c1'))
        .attr('d', `M${bx},${H - m.b}V${by + r}a${r},${r} 0 0 1 ${r},${-r}H${bx + bw - r}a${r},${r} 0 0 1 ${r},${r}V${H - m.b}Z`);
      svg.append('rect').attr('x', bx - 1).attr('y', m.t).attr('width', bw + 2).attr('height', H - m.t - m.b).style('fill', 'transparent')
        .on('mousemove', () => { const k = svg.node().getBoundingClientRect().width / W;
          tip.show(`<b>${b[0]}</b><br>${fmtNum(b[1], s.digits ?? 0)} ${s.unit || ''}` + (s.extra && b[2] ? '<br>' + s.extra.replace('{v}', fmtNum(b[2], 0)) : ''), (bx + bw) * k + 8, by * k); })
        .on('mouseleave', () => tip.hide());
    });
  }

  const RENDER = { multiples, lines, timeline, dumbbell, diverging, bars };
  function draw(v) {
    const body = v.querySelector('.viz-mount'); if (!body || !v.offsetParent) return;
    const spec = JSON.parse(v.querySelector('script[type="application/json"]').textContent);
    const w = body.clientWidth; if (body.dataset.w === String(w)) return;
    body.dataset.w = String(w); body.innerHTML = '';
    if (spec.legend) {
      const lg = document.createElement('div'); lg.className = 'viz-legend';
      lg.innerHTML = spec.legend.map(l => `<span><i class="${l.dot ? 'dot' : l.dash ? 'dash' : ''}" style="${l.hollow ? `border:2px solid ${col(l.color)};background:var(--sheet)` : l.dash ? `border-top-color:${col(l.color)}` : `background:${col(l.color)}`}"></i>${l.label}</span>`).join('');
      body.appendChild(lg);
    }
    try { RENDER[spec.type](body, spec); } catch (e) { body.textContent = ''; console.error(e); }
  }
  function drawAll() { if (window.d3) blocks[lang].querySelectorAll('.viz').forEach(draw); }
  let rt; addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(drawAll, 150); });

  /* ---------- start ---------- */
  const hash = decodeURIComponent(location.hash.slice(1));
  let start = /^(es|en)(-|$)/.test(hash) ? hash.slice(0, 2) : null;
  if (!start) { try { start = localStorage.getItem(KEY); } catch (e) {} }
  if (start !== 'es' && start !== 'en') start = /^en\b/i.test(navigator.language || '') ? 'en' : 'es';
  document.querySelectorAll('details.toc').forEach(d => { d.open = !narrow.matches; });
  setLang(start, false);
  const card = id => { const t = document.getElementById(id); if (t && t.tagName === 'DETAILS') t.open = true; return t; };   // a link to a card opens it
  if (hash.length > 2) { const t = card(hash); if (t) t.scrollIntoView({ block: 'start', behavior: 'instant' }); }
  addEventListener('hashchange', () => card(decodeURIComponent(location.hash.slice(1))));
  buttons.forEach(b => b.addEventListener('click', () => setLang(b.dataset.setLang, true)));
  let ticking = false;
  addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { ticking = false; track(); }); } }, { passive: true });
  document.querySelectorAll('details.toc a').forEach(a => a.addEventListener('click', () => { if (narrow.matches) a.closest('details').open = false; }));
  document.addEventListener('click', e => {
    const b = e.target.closest('.copy'); if (!b) return;
    const src = b.parentElement.querySelector('pre, .ex-q');
    const label = b.textContent;
    const done = () => { b.textContent = b.dataset.done; setTimeout(() => { b.textContent = label; }, 1600); };
    const select = () => { const r = document.createRange(); r.selectNodeContents(src); const s = getSelection(); s.removeAllRanges(); s.addRange(r); };
    try { navigator.clipboard.writeText(src.innerText).then(done, select); } catch (err) { select(); }
  });
  const nav = document.querySelector('.nav'), here = nav && [...nav.querySelectorAll('[aria-current]')].find(a => a.offsetParent);
  if (nav && here && nav.scrollWidth > nav.clientWidth) {   // on a phone, start the bar with this page in view
    nav.scrollLeft = here.offsetLeft - (nav.clientWidth - here.offsetWidth) / 2;
  }
  if (nav) {
    const edge = () => {   // fade whichever side has more links
      nav.style.setProperty('--fl', nav.scrollLeft > 2 ? '28px' : '0px');
      nav.style.setProperty('--fr', nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 2 ? '28px' : '0px');
    };
    nav.addEventListener('scroll', edge, { passive: true }); window.addEventListener('resize', edge); edge();
  }
  const filter = document.querySelectorAll('.ref-filter input');
  filter.forEach(inp => inp.addEventListener('input', () => {
    const q = inp.value.trim().toLowerCase();
    const root = inp.closest('.lang');
    root.querySelectorAll('.tool-card').forEach(c => {
      c.hidden = q && !c.textContent.toLowerCase().includes(q);
      if (q && !c.hidden && !c.open) { c.open = true; c.dataset.filterOpened = '1'; }   // show where the match is
      if (!q && c.dataset.filterOpened) { c.open = false; delete c.dataset.filterOpened; }
    });
    let any = false;
    root.querySelectorAll('.ref-group').forEach(h => {   // a heading stays only while one of its cards does
      let n = h.nextElementSibling, shown = false;
      while (n && !n.classList.contains('ref-group')) { if (n.classList.contains('tool-card') && !n.hidden) shown = true; n = n.nextElementSibling; }
      h.hidden = !shown; any = any || shown;
    });
    root.querySelector('.ref-none').hidden = any;
  }));
})();
