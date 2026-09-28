/* 매물레이더 — 데이터(JSON)를 읽어 화면 5개를 그리는 작은 앱 */
(function () {
  'use strict';

  // ---------- 도구 ----------
  const $app = document.getElementById('app');
  const $tip = document.getElementById('tip');
  const cache = {};
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const load = (p) => cache[p] || (cache[p] = fetch('data/' + p, { cache: 'no-cache' }).then((r) => { if (!r.ok) throw new Error(p); return r.json(); }));
  const won = (man) => {
    if (man == null || isNaN(man)) return '–';
    man = Math.round(man);
    const e = Math.floor(man / 10000), r = man % 10000;
    if (e > 0) return e + '억' + (r ? ' ' + r.toLocaleString('ko-KR') : '');
    return r.toLocaleString('ko-KR') + '만';
  };
  const wonMan = (man) => { const s = won(man); return /억$/.test(s) || /만$/.test(s) ? s : s + '만'; };
  const pct = (x, d = 0) => (x == null ? '–' : (x * 100).toFixed(d) + '%');
  const ymLabel = (ym) => `${ym.slice(2, 4)}.${ym.slice(4, 6)}`;
  const dateLabel = (d) => d.replace(/-/g, '.');
  const store = {
    get(k, d) { try { const v = localStorage.getItem('radar:' + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem('radar:' + k, JSON.stringify(v)); } catch (e) { /* 저장 불가 환경 */ } },
  };
  const favs = () => store.get('favs', {});

  // ---------- 툴팁 ----------
  document.addEventListener('mousemove', (e) => {
    const t = e.target.closest && e.target.closest('[data-tip]');
    if (!t) { $tip.style.display = 'none'; return; }
    $tip.innerHTML = t.getAttribute('data-tip');
    $tip.style.display = 'block';
    const w = $tip.offsetWidth;
    $tip.style.left = Math.min(window.innerWidth - w - 8, e.clientX + 14) + 'px';
    $tip.style.top = (e.clientY + 16) + 'px';
  });

  // ---------- 차트 ----------
  function niceTicks(min, max, n = 4) {
    const span = max - min || 1;
    const raw = span / n, mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw);
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
    const out = [];
    for (let v = lo; v <= hi + step / 2; v += step) out.push(v);
    return out;
  }

  /* xs: x 라벨 배열(칸 수), series: [{vals, color, dash, width}], bars: {vals, color, dim:[idx]},
     dots: [{x(실수 인덱스), y, tip, r, color}], refs: [{y, label, color, dash}], band: {y1, y2, label} */
  function chart(o) {
    const W = o.w || 860, H = o.h || 280, L = o.left || 56, R = 16, T = 14, B = 30;
    const n = o.xs.length;
    const vals = [];
    (o.series || []).forEach((s) => s.vals.forEach((v) => v != null && vals.push(v)));
    (o.dots || []).forEach((d) => vals.push(d.y));
    (o.refs || []).forEach((r) => vals.push(r.y));
    if (o.band) vals.push(o.band.y1, o.band.y2);
    let lo = o.bars ? 0 : Math.min(...vals), hi = Math.max(...(o.bars ? o.bars.vals : vals));
    if (!o.bars) { const pad = (hi - lo) * 0.08 || hi * 0.05; lo -= pad; hi += pad; }
    const ticks = niceTicks(lo, hi);
    lo = ticks[0]; hi = ticks[ticks.length - 1];
    const x = (i) => L + (n <= 1 ? 0 : (i / (n - 1)) * (W - L - R));
    const bw = (W - L - R) / n;
    const xb = (i) => L + i * bw;
    const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
    const f = o.yFmt || ((v) => v);
    let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(o.label || '차트')}">`;
    ticks.forEach((t) => {
      s += `<line x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}" stroke="#E5E5EA"/>`;
      s += `<text x="${L - 8}" y="${y(t) + 4}" text-anchor="end" font-size="12" fill="#6C6C70">${esc(f(t))}</text>`;
    });
    if (o.band) {
      s += `<rect x="${L}" y="${y(o.band.y2)}" width="${W - L - R}" height="${y(o.band.y1) - y(o.band.y2)}" fill="#E0EFFF"/>`;
    }
    const step = Math.max(1, Math.ceil(n / (o.maxLabels || 8)));
    o.xs.forEach((lab, i) => {
      if (o.labelAll ? lab : (i % step === 0 || i === n - 1)) {
        const cx = o.bars ? xb(i) + bw / 2 : x(i);
        s += `<text x="${cx}" y="${H - 8}" text-anchor="middle" font-size="12" fill="#6C6C70">${esc(lab)}</text>`;
      }
    });
    if (o.bars) {
      o.bars.vals.forEach((v, i) => {
        const h = y(lo) - y(v || 0);
        const dim = o.bars.dim && o.bars.dim.includes(i);
        const col = dim ? '#C7C7CC' : (o.bars.color || '#007AFF');
        s += `<path d="M${xb(i) + 1},${y(lo)} v${-Math.max(0, h - 3)} q0,-3 3,-3 h${bw - 8} q3,0 3,3 v${Math.max(0, h - 3)} z" fill="${col}"/>`;
      });
    }
    (o.refs || []).forEach((r) => {
      s += `<line x1="${L}" x2="${W - R}" y1="${y(r.y)}" y2="${y(r.y)}" stroke="${r.color || '#000'}" stroke-width="1.2" stroke-dasharray="${r.dash || '4 4'}"/>`;
      if (r.label) s += `<text x="${W - R}" y="${y(r.y) - 6}" text-anchor="end" font-size="12" font-weight="${r.bold ? 700 : 500}" fill="${r.textColor || r.color || '#000'}">${esc(r.label)}</text>`;
    });
    (o.series || []).forEach((sr) => {
      let d = '', pen = false;
      sr.vals.forEach((v, i) => {
        if (v == null) { pen = false; return; }
        d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ',' + y(v).toFixed(1) + ' ';
        pen = true;
      });
      s += `<path d="${d}" fill="none" stroke="${sr.color}" stroke-width="${sr.width || 2}" stroke-linejoin="round" stroke-linecap="round" ${sr.dash ? `stroke-dasharray="${sr.dash}"` : ''}/>`;
    });
    (o.dots || []).forEach((d) => {
      s += `<circle cx="${x(d.x).toFixed(1)}" cy="${y(d.y).toFixed(1)}" r="${d.r || 4}" fill="${d.color || '#000'}" ${d.ring ? 'stroke="#fff" stroke-width="2"' : ''}/>`;
    });
    // 마우스 올리면 값이 보이는 투명 영역
    if (o.tip) {
      for (let i = 0; i < n; i++) {
        const t = o.tip(i);
        if (!t) continue;
        const cx = o.bars ? xb(i) : x(i) - bw / 2;
        s += `<rect x="${cx}" y="${T}" width="${bw}" height="${H - T - B}" fill="transparent" data-tip="${esc(t)}"/>`;
      }
    }
    (o.dots || []).forEach((d) => {
      if (d.tip) s += `<circle cx="${x(d.x).toFixed(1)}" cy="${y(d.y).toFixed(1)}" r="9" fill="transparent" data-tip="${esc(d.tip)}"/>`;
    });
    return s + '</svg>';
  }

  // ---------- 돈 계산 ----------
  function calc(p, rules) {
    const price = p.price;
    const cap = rules.loanCaps.find((c) => c.upto == null || price <= c.upto).cap;
    const loanMax = Math.min(price * (p.first ? rules.ltv.firstHome : rules.ltv.default), cap);
    const loan = Math.min(p.loan == null ? loanMax : p.loan, loanMax);
    const a = rules.acqTax;
    let r = price <= a.low.upto ? a.low.rate : price > a.high.from ? a.high.rate : ((price / 10000) * 2 / 3 - 3) / 100;
    let tax = price * r * (1 + a.eduTaxRatio);
    if (p.first && price <= rules.firstHomeRelief.maxPrice) tax = Math.max(0, tax - rules.firstHomeRelief.amount);
    const b = rules.brokerage.find((x) => x.upto == null || price < x.upto);
    let broker = price * b.rate; if (b.limit) broker = Math.min(broker, b.limit);
    broker *= 1 + rules.brokerageVat;
    const bond = price * rules.bond.publicPriceRatio * rules.bond.buyRate * rules.bond.discount;
    const stamp = rules.stampTax.find((x) => x.upto == null || price <= x.upto).amount;
    const legal = rules.legalFee;
    const cost = tax + broker + bond + stamp + legal + p.moving + p.interior;
    const down = price - loan;
    const mr = p.rate / 100 / 12, nper = rules.defaults.years * 12;
    const monthly = loan > 0 ? (loan * mr) / (1 - Math.pow(1 + mr, -nper)) : 0;
    return { loan, loanMax, tax, taxRate: r, broker, bond, stamp, legal, cost, down, total: down + cost, monthly };
  }

  // ---------- 공통 조각 ----------
  const dot = (tone) => `<span class="dot ${tone}" aria-hidden="true"></span>`;
  const badge = (drop) => {
    if (drop == null) return '<span class="badge b0">–</span>';
    const d = Math.round(drop * 100);
    const cls = d >= 20 ? 'b20' : d >= 10 ? 'b10' : 'b0';
    return `<span class="badge ${cls}">${drop > 0 ? '-' : '+'}${Math.abs(Math.round(drop * 100))}%</span>`;
  };
  const checkIcon = (ok, na) => na
    ? '<svg class="ico" viewBox="0 0 24 24" aria-label="자료 없음"><circle cx="12" cy="12" r="10" fill="none" stroke="#C7C7CC" stroke-width="2" stroke-dasharray="3 3"/></svg>'
    : ok
    ? '<svg class="ico" viewBox="0 0 24 24" aria-label="충족"><circle cx="12" cy="12" r="11" fill="#34C759"/><path d="M7 12.5l3.2 3.2L17 9" fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    : '<svg class="ico" viewBox="0 0 24 24" aria-label="아직"><circle cx="12" cy="12" r="10" fill="none" stroke="#C7C7CC" stroke-width="2"/></svg>';
  const sampleNote = (meta) => meta.sample
    ? '<span class="pill warn">테스트 데이터 · 단지 이름과 숫자는 모두 가짜예요</span>'
    : `<span class="pill">국토교통부 실거래가 · ${ymLabel(meta.lastMonth)}까지 신고분 반영</span>`;

  function favChanges(units) {
    const f = favs();
    const byId = Object.fromEntries(units.map((u) => [u.id, u]));
    return Object.entries(f).map(([id, saved]) => {
      const u = byId[id];
      if (!u) return { id, saved, u: null, changed: false };
      const changed = u.last && u.last.date > saved.lastDate;
      return { id, saved, u, changed, diff: u.recent != null && saved.recent != null ? u.recent - saved.recent : null };
    });
  }

  // ---------- 화면: 오늘의 추천 ----------
  async function home() {
    const [meta, rec, regions, units] = await Promise.all([load('meta.json'), load('recommend.json'), load('regions.json'), load('units.json')]);
    const changes = favChanges(units);
    const changed = changes.filter((c) => c.changed);
    const w = rec.weights;
    const order = [['growth', '오를 가능성 (동네 흐름 · 전세)'], ['price_drop', '전고점보다 싼지'], ['commute', '출퇴근'], ['school', '학군'], ['condition', '단지 컨디션 (연식)']]
      .sort((a, b) => w[b[0]] - w[a[0]]);
    $app.innerHTML = `
    <section class="head">
      <div>${sampleNote(meta)}
        <h1 class="h1">오늘의 추천 ${rec.top.length}</h1>
        <p class="sub">내 조건에 맞는 단지·평형 ${rec.candidateCount}곳 중 지금 사기 좋은 순서로 골랐어요.</p>
      </div>
      <div class="chips">
        <span class="chip on" style="display:inline-flex;align-items:center">${esc(rec.regions.join(' · '))}</span>
        <span class="chip" style="display:inline-flex;align-items:center">전용 ${rec.filters.area_min_m2}~${rec.filters.area_max_m2}㎡</span>
        <span class="chip" style="display:inline-flex;align-items:center">${won(rec.filters.max_price_manwon)} 이하</span>
        <a class="chip" href="#/setting" style="display:inline-flex;align-items:center;border-style:dashed;color:#6C6C70">조건 바꾸기</a>
      </div>
    </section>
    <section class="grid g3">
      <div class="card"><div class="muted">어제보다 새로 들어온 추천</div>
        <div class="big">${rec.newCount == null ? '–' : rec.newCount + '개'}</div>
        <div class="small muted">${rec.newCount == null ? '매일 쌓이면 어제와 비교해 드려요' : `나머지 ${rec.top.length - rec.newCount}개는 어제도 추천했던 곳`}</div></div>
      <div class="card"><div class="muted">찜한 매물 중 새 거래가 생긴 곳</div>
        <div class="big ${changed.length ? 'accent' : ''}">${changes.length ? changed.length + '곳' : '–'}</div>
        <div class="small muted">${changes.length ? (changed[0] ? esc(changed[0].u.name) + ' 새 실거래 ' + wonMan(changed[0].u.last.price) : '찜한 곳에 새 거래 없음') : '단지 상세에서 찜하면 여기서 알려드려요'}</div></div>
      <div class="card"><div class="muted">전고점보다 많이 싼 단지·평형</div>
        <div style="display:flex;gap:20px;align-items:baseline;flex-wrap:wrap">
          <div class="big">${rec.drop10}곳 <span class="small muted" style="font-weight:500">10% 이상</span></div>
          <div class="big accent">${rec.drop20}곳 <span class="small muted" style="font-weight:500">20% 이상</span></div></div>
        <div class="small muted">같은 단지 · 같은 평형의 가장 비싼 거래 기준</div></div>
    </section>
    <section class="row">
      <div class="grow list">
        <div class="list-h"><div>순위</div><div>단지</div><div>최근 거래가</div><div>전고점 대비</div><div>추천 이유</div><div style="text-align:right">점수</div></div>
        ${rec.top.map((u) => `
        <a class="list-r" href="#/unit/${encodeURIComponent(u.id)}">
          <div class="rank">${u.rank}</div>
          <div><div class="name">${esc(u.name)}${u.isNew ? '<span class="new">NEW</span>' : ''}</div>
            <div class="small muted">${esc(u.region)} ${esc(u.dong)} · ${u.pyeong}평 · ${u.built || '?'}년</div></div>
          <div><div style="font-weight:600;font-size:16px">${won(u.recent)}</div>
            <div class="small muted">최고 ${won(u.peak && u.peak.price)}</div></div>
          <div>${badge(u.drop)}</div>
          <div style="display:flex;flex-direction:column;gap:8px;min-width:0"><div style="font-size:14px">${esc(u.reason)}</div>
            <div class="tags">${u.tags.map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div></div>
          <div class="score">${u.score}</div>
        </a>`).join('') || '<div class="empty">조건에 맞는 단지가 없어요. 조건을 넓혀 보세요.</div>'}
      </div>
      <aside class="side">
        <div class="card"><div class="card-head"><h2>동네 시세 신호</h2><a class="small" href="#/region">자세히</a></div>
          ${regions.map((g) => `<a class="sig" href="#/region/${g.lawd}" style="color:inherit">${dot(g.tone)}
            <div><div style="font-weight:600">${esc(g.name)} · ${esc(g.status)}</div>
            <div class="small muted">${esc(g.summary)}</div></div></a>`).join('')}
        </div>
        <div class="card"><div class="card-head"><h2>찜한 매물 변화</h2><a class="small" href="#/watch">전체 보기</a></div>
          ${changes.length ? changes.slice(0, 3).map((c) => c.u ? `<a class="kv" href="#/unit/${encodeURIComponent(c.id)}" style="color:inherit">
            <div><div style="font-weight:600">${esc(c.u.name)}</div><div class="small muted">최근 거래 ${wonMan(c.u.last.price)} · ${dateLabel(c.u.last.date)}</div></div>
            <div class="small" style="font-weight:700;${c.changed ? 'color:#007AFF' : 'color:#6C6C70'}">${c.changed ? '새 거래' : '그대로'}</div></a>` : '').join('')
            : '<div class="small muted">아직 찜한 곳이 없어요.</div>'}
        </div>
        <div class="card blue"><h2>점수는 이렇게 매겨요</h2>
          <div class="small" style="line-height:1.8;color:#D6E9FF">${order.map((o, i) => `${i + 1}. ${o[1]} · ${w[o[0]]}점`).join('<br>')}</div>
          <a class="btn white" href="#/setting">비중 바꾸는 법</a></div>
      </aside>
    </section>`;
  }

  // ---------- 화면: 단지 상세 ----------
  async function unit(id) {
    const [meta, rec, regions, rules] = await Promise.all([load('meta.json'), load('recommend.json'), load('regions.json'), load('rules.json')]);
    let u;
    try { u = await load('units/' + id + '.json'); } catch (e) { $app.innerHTML = '<div class="empty">이 단지 정보를 찾지 못했어요. <a href="#/">돌아가기</a></div>'; return; }
    const top = rec.top.find((t) => t.id === u.id);
    const region = regions.find((g) => g.lawd === u.lawd);
    const isFav = !!favs()[u.id];
    const money = calc({ price: u.recent || u.last.price, first: false, rate: rules.defaults.rate, interior: rules.defaults.interior, moving: rules.defaults.moving }, rules);
    const age = new Date().getFullYear() - (u.built || new Date().getFullYear());

    // 차트: 첫 거래 달부터 지난달까지
    const first = u.trades[0].d.slice(0, 7).replace('-', '');
    const months = [];
    for (let cur = first; cur <= meta.lastMonth;) { months.push(cur); const yy = +cur.slice(0, 4), mm = +cur.slice(4); cur = mm === 12 ? `${yy + 1}01` : `${yy}${String(mm + 1).padStart(2, '0')}`; }
    const mi = Object.fromEntries(months.map((m, i) => [m, i]));
    const monthlyMap = Object.fromEntries(u.monthly.map((m) => [m.ym, m.p]));
    const smooth = months.map((m, i) => {
      const xs = [months[i - 1], m, months[i + 1]].map((k) => monthlyMap[k]).filter((v) => v != null);
      return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
    });
    const jMap = Object.fromEntries(u.jmonthly.map((m) => [m.ym, m.p]));
    const jline = months.map((m, i) => {
      const xs = [months[i - 2], months[i - 1], m, months[i + 1], months[i + 2]].map((k) => jMap[k]).filter((v) => v != null);
      return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
    });
    const valid = u.trades.filter((t) => !t.x);
    const dots = valid.map((t) => {
      const ym = t.d.slice(0, 7).replace('-', '');
      return mi[ym] == null ? null : { x: mi[ym] + (+t.d.slice(8, 10) - 15) / 31, y: t.p, r: 4, color: '#000', tip: `${dateLabel(t.d)} · ${t.f}층<br><b>${wonMan(t.p)}</b>` };
    }).filter(Boolean);
    if (dots.length) { const l = dots[dots.length - 1]; l.r = 6; l.color = '#007AFF'; l.ring = true; }
    const pk = u.peak ? u.peak.price : null;
    const priceChart = chart({
      xs: months.map((m) => (m.endsWith('01') ? m.slice(0, 4) : '')), labelAll: true,
      series: [{ vals: jline, color: '#8E8E93', dash: '6 4', width: 2 }, { vals: smooth, color: '#007AFF', width: 2.5 }],
      dots, yFmt: (v) => won(v),
      band: pk ? { y1: pk * 0.8, y2: pk * 0.9 } : null,
      refs: pk ? [{ y: pk, label: `전고점 ${won(pk)}`, bold: true }, { y: pk * 0.9, label: `10% 낮은 선 ${won(pk * 0.9)}`, color: 'transparent', textColor: '#0062CC' }, { y: pk * 0.8, label: `20% 낮은 선 ${won(pk * 0.8)}`, color: 'transparent', textColor: '#0062CC' }] : [],
      label: '가격 흐름', h: 300,
    });

    const cons = [];
    if (u.trades6m < 2) cons.push('최근 거래가 적어서 가격이 정확하지 않을 수 있어요.');
    if (age >= 25) cons.push('오래된 아파트라 주차·배관 상태를 꼭 확인해야 해요.');
    if (u.jratio != null && u.jratio < 0.45) cons.push('전세가가 집값의 절반이 안 돼 받쳐주는 힘이 약해요.');
    if (region && region.tone !== 'good') cons.push(`${region.name} 흐름이 아직 '${region.status}' 상태예요.`);
    const recentTrades = u.trades.slice(-12).reverse();

    $app.innerHTML = `
    <section class="head">
      <div><a class="back" href="#/">← 오늘의 추천으로</a>
        <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
          ${top ? `<span class="badge b20" style="font-size:13px;padding:4px 10px">오늘 ${top.rank}위 · ${top.score}점</span>` : ''}${sampleNote(meta)}</div>
        <h1 class="h1">${esc(u.name)}</h1>
        <p class="sub">${esc(u.region)} ${esc(u.dong)} ${esc(u.jibun)} · 약 ${u.pyeong}평 (전용 ${u.area}㎡) · ${u.built || '?'}년 준공</p></div>
      <div style="display:flex;gap:8px;flex-direction:row">
        <button class="btn ${isFav ? 'on' : ''}" id="fav">${isFav ? '찜 해제' : '찜하기'}</button>
        <a class="btn primary" href="#/calc/${encodeURIComponent(u.id)}">돈 계산해 보기</a></div>
    </section>
    <section class="grid g5 tiles">
      <div class="tile"><div class="small muted">최근 거래가</div><div class="v">${won(u.recent)}</div><div class="small muted">${esc(u.recentBasis || '')}</div></div>
      <div class="tile"><div class="small muted">지금 나온 매물 최저가</div><div class="soon">2단계에서 연결</div><div class="small muted">네이버·KB 호가</div></div>
      <div class="tile"><div class="small muted">KB시세</div><div class="soon">2단계에서 연결</div></div>
      <div class="tile"><div class="small muted">전고점 (${u.peak ? dateLabel(u.peak.date).slice(0, 7) : '–'})</div><div class="v">${won(pk)}</div><div class="small muted">${u.peak ? u.peak.floor + '층 거래' : ''}</div></div>
      <div class="tile blue"><div class="small muted">전고점보다</div><div class="v">${u.drop == null ? '–' : u.drop >= 0 ? Math.round(u.drop * 100) + '% 낮음' : Math.round(-u.drop * 100) + '% 높음'}</div></div>
    </section>
    <section class="row">
      <div class="grow card">
        <div class="card-head"><h2>가격 흐름 한눈에</h2><span class="small muted">점에 마우스를 올리면 거래 정보가 보여요</span></div>
        <div class="legend"><span><svg width="22" height="10"><line x1="0" y1="5" x2="22" y2="5" stroke="#007AFF" stroke-width="3"/></svg>실거래 흐름 (3개월 평균)</span>
          <span><svg width="12" height="12"><circle cx="6" cy="6" r="4.5"/></svg>실거래 한 건</span>
          <span><svg width="22" height="10"><line x1="0" y1="5" x2="22" y2="5" stroke="#8E8E93" stroke-width="3" stroke-dasharray="5 3"/></svg>전세</span>
          <span><svg width="16" height="12"><rect y="1" width="16" height="10" fill="#E0EFFF"/></svg>전고점 대비 10~20% 싼 구간</span></div>
        ${priceChart}
        <p class="small muted" style="margin:0">저층(${3}층 이하)·직거래·취소된 거래는 점에서 뺐어요. 아래 표에는 모두 보여요.</p>
      </div>
      <aside class="side side-w">
        <div class="card"><h2>${top ? '왜 추천했나요?' : '이 단지 한 줄 평'}</h2>
          <div style="font-size:14px">${esc(u.reason || '조건(예산·거래 수)에 맞지 않아 추천 후보에서 빠진 단지예요.')}</div>
          <div class="tags">${(u.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join('')}</div>
          ${cons.length ? `<div class="small" style="background:#F2F2F7;border-radius:10px;padding:12px 14px;color:#3C3C43">아쉬운 점: ${cons.map(esc).join(' ')}</div>` : ''}
        </div>
        <div class="card blue"><h2>내 돈은 얼마나 필요할까?</h2>
          <div class="small muted">${won(u.recent || u.last.price)}에 사고, 대출을 최대(${won(money.loan)})로 받는다면</div>
          <div class="big" style="font-size:32px">약 ${wonMan(Math.round(money.total / 100) * 100)} 원</div>
          <div class="small" style="display:flex;flex-direction:column;gap:6px;color:#D6E9FF">
            <div class="kv"><span>집값 − 대출</span><span>${wonMan(money.down)}</span></div>
            <div class="kv"><span>취득세 등</span><span>${wonMan(money.tax)}</span></div>
            <div class="kv"><span>중개 수수료</span><span>${wonMan(money.broker)}</span></div>
            <div class="kv"><span>등기·법무사·채권·인지세</span><span>${wonMan(money.bond + money.legal + money.stamp)}</span></div>
            <div class="kv"><span>이사·인테리어</span><span>${wonMan(rules.defaults.moving + rules.defaults.interior)}</span></div></div>
          <a class="btn white" href="#/calc/${encodeURIComponent(u.id)}">계산기에서 바꿔보기</a></div>
      </aside>
    </section>
    <section class="row">
      <div class="grow card"><h2>단지 정보</h2>
        <div class="grid g4">
          ${[['준공', `${u.built || '?'}년 (${age}년차)`], ['전용 · 평형', `${u.area}㎡ · 약 ${u.pyeong}평`], ['최근 2년 거래', `${u.trades2y}건`], ['최근 6개월 거래', `${u.trades6m}건`],
             ['전세 (최근 1년 중간값)', u.jeonse ? won(u.jeonse) : '거래 없음'], ['전세가율', u.jratio ? pct(u.jratio) : '–'], ['마지막 거래', `${dateLabel(u.last.date)} · ${u.last.floor}층`], ['주소', `${esc(u.dong)} ${esc(u.jibun)}`]]
            .map(([k, v]) => `<div style="background:#F2F2F7;border-radius:10px;padding:14px 16px;display:flex;flex-direction:column;gap:4px"><span class="small muted">${k}</span><span style="font-size:16px;font-weight:600">${v}</span></div>`).join('')}
        </div>
        <div class="small muted">세대수·주차·관리비·용적률·대지지분은 2단계(공동주택관리정보시스템·건축물대장)에서 연결해요.</div>
      </div>
      <div class="card side-w"><h2>재건축</h2>
        ${age >= 30 ? `<div style="font-size:15px">준공 ${age}년차라 <b>재건축을 검토할 수 있는 나이</b>예요.</div>` : `<div style="font-size:15px">준공 ${age}년차예요. 보통 30년이 지나야 재건축을 검토해요.</div>`}
        <div class="small muted">어느 단계까지 왔는지는 2단계에서 서울시 정비사업 정보몽땅과 연결해요.</div></div>
    </section>
    ${region ? `<section style="display:flex;flex-direction:column;gap:12px">
      <div class="sec-title"><h2>이 동네 흐름</h2><a class="small" href="#/region/${region.lawd}">${esc(region.name)} 리포트 전체 보기</a></div>
      <div class="grid g3">
        <div class="card"><div style="display:flex;gap:8px;align-items:center">${dot(region.tone)}<h3>시세 흐름 · ${esc(region.status)}</h3></div><div class="small" style="color:#3C3C43">${esc(region.summary)}</div></div>
        ${region.checks.filter((c) => c.id !== 'room').slice(0, 2).map((c) => `<div class="card"><div style="display:flex;gap:8px;align-items:center">${checkIcon(c.ok, c.na)}<h3>${esc(c.title)}</h3></div><div class="small" style="color:#3C3C43">${esc(c.detail)}</div></div>`).join('')}
      </div></section>` : ''}
    <section class="row">
      <div class="grow card"><h2>최근 실거래 (${u.area}㎡)</h2>
        <div class="table-wrap"><table class="table"><thead><tr><th>계약일</th><th>층</th><th>가격</th><th>전고점 대비</th><th>비고</th></tr></thead><tbody>
        ${recentTrades.map((t) => `<tr class="${t.x ? 'dim' : ''}"><td>${dateLabel(t.d)}</td><td>${t.f}층</td><td style="font-weight:600">${won(t.p)}</td>
          <td style="${!t.x ? 'color:#007AFF;font-weight:600' : ''}">${pk ? (t.p <= pk ? '-' : '+') + Math.abs(Math.round((1 - t.p / pk) * 100)) + '%' : '–'}</td><td>${t.x ? esc(t.x) + ' · 계산에서 뺌' : ''}</td></tr>`).join('')}
        </tbody></table></div></div>
      <div class="card side-w"><div class="card-head"><h2>내 임장 메모</h2><span class="small muted">이 브라우저에 저장돼요</span></div>
        <div class="grid g2">
          ${[['dir', '향 (방향)', '예: 남향'], ['sun', '햇빛', '예: 오후까지 잘 듦'], ['view', '전망', '예: 앞 동에 막힘'], ['noise', '소음', '예: 큰길 쪽 동은 시끄러움']]
            .map(([k, l, ph]) => `<label class="field small muted">${l}<input type="text" data-memo="${k}" placeholder="${ph}"></label>`).join('')}
        </div>
        <label class="field small muted">자유 메모<textarea data-memo="free" placeholder="분위기, 경사, 마트·학교까지 걸어본 느낌 등"></textarea></label></div>
    </section>`;

    document.getElementById('fav').onclick = () => {
      const f = favs();
      if (f[u.id]) delete f[u.id]; else f[u.id] = { name: u.name, recent: u.recent, lastDate: u.last.date, saved: new Date().toISOString().slice(0, 10) };
      store.set('favs', f); unit(id);
    };
    const memo = store.get('memo:' + u.id, {});
    $app.querySelectorAll('[data-memo]').forEach((el) => {
      el.value = memo[el.dataset.memo] || '';
      el.addEventListener('input', () => { memo[el.dataset.memo] = el.value; store.set('memo:' + u.id, memo); });
    });
  }

  // ---------- 화면: 돈 계산기 ----------
  async function calcPage(id) {
    const [rules, units] = await Promise.all([load('rules.json'), load('units.json')]);
    const u = units.find((x) => x.id === id) || units[0];
    const st = { price: u ? (u.recent || 100000) : 100000, loan: null, rate: rules.defaults.rate, interior: rules.defaults.interior, moving: rules.defaults.moving, first: false };
    $app.innerHTML = `
    <section class="head"><div>
      ${u ? `<a class="back" href="#/unit/${encodeURIComponent(u.id)}">← ${esc(u.name)} 상세로</a>` : ''}
      <h1 class="h1">내 돈은 얼마나 필요할까?</h1>
      <p class="sub">막대를 움직이면 바로 다시 계산해요.</p></div>
      <label class="field small muted" style="min-width:min(320px,100%)">단지 고르기
        <select id="pick">${units.map((x) => `<option value="${esc(x.id)}" ${u && x.id === u.id ? 'selected' : ''}>${esc(x.name)} · ${x.area}㎡ · ${won(x.recent)}</option>`).join('')}</select></label>
    </section>
    <section class="row">
      <div class="card side-w" style="gap:24px"><h2>조건 넣기</h2>
        <label class="field"><div class="field-top"><span style="font-weight:600">살 가격</span><b id="v-price"></b></div>
          <input type="range" id="price" min="30000" max="250000" step="500">
          <div class="small muted" id="price-note"></div></label>
        <div class="field"><span style="font-weight:600">생애 첫 집인가요?</span>
          <div style="display:flex;gap:8px"><button class="btn" id="first-y">네, 첫 집이에요</button><button class="btn" id="first-n">아니요</button></div>
          <div class="small muted">첫 집이면 대출을 집값의 ${pct(rules.ltv.firstHome)}까지, 아니면 ${pct(rules.ltv.default)}까지 받을 수 있어요. 12억 이하면 취득세도 최대 200만 원 깎아줘요.</div></div>
        <label class="field"><div class="field-top"><span style="font-weight:600">대출</span><b id="v-loan"></b></div>
          <input type="range" id="loan" min="0" step="500"><div class="small muted" id="loan-note"></div></label>
        <label class="field"><div class="field-top"><span style="font-weight:600">대출 금리</span><b id="v-rate"></b></div>
          <input type="range" id="rate" min="2.5" max="7" step="0.1"></label>
        <label class="field"><div class="field-top"><span style="font-weight:600">인테리어</span><b id="v-interior"></b></div>
          <input type="range" id="interior" min="0" max="10000" step="100"></label>
        <label class="field"><div class="field-top"><span style="font-weight:600">이사비</span><b id="v-moving"></b></div>
          <input type="range" id="moving" min="50" max="600" step="10"></label>
        <div class="small muted">규칙: ${esc(rules.asOf)}. 소득에 따른 대출 한도(DSR)는 반영하지 않았어요.</div>
      </div>
      <div class="grow" style="display:flex;flex-direction:column;gap:16px" id="result"></div>
    </section>`;

    const $ = (s) => document.getElementById(s);
    const inputs = ['price', 'loan', 'rate', 'interior', 'moving'];
    function render() {
      const r = calc(st, rules);
      st.loan = r.loan;
      $('price').value = st.price; $('rate').value = st.rate; $('interior').value = st.interior; $('moving').value = st.moving;
      $('loan').max = Math.max(500, r.loanMax); $('loan').value = r.loan;
      $('v-price').textContent = won(st.price); $('v-loan').textContent = won(r.loan); $('v-rate').textContent = st.rate.toFixed(1) + '%';
      $('v-interior').textContent = wonMan(st.interior); $('v-moving').textContent = wonMan(st.moving);
      $('price-note').textContent = u ? `${u.name} 최근 거래가 ${won(u.recent)} · 전고점 ${won(u.peak && u.peak.price)}` : '';
      $('loan-note').textContent = `이 가격이면 최대 ${won(r.loanMax)}까지 (집값의 ${pct(st.first ? rules.ltv.firstHome : rules.ltv.default)}, 가격대별 한도 중 작은 쪽)`;
      $('first-y').className = 'btn' + (st.first ? ' on' : ''); $('first-n').className = 'btn' + (!st.first ? ' on' : '');
      const downPct = Math.max(0, Math.min(100, (r.down / r.total) * 100));
      $('result').innerHTML = `
        <div class="card blue" style="padding:32px;gap:16px"><div class="muted">내 통장에서 나가야 할 돈</div>
          <div class="hero">${wonMan(r.total)} 원</div>
          <div class="bar"><div style="width:${downPct}%;background:#fff"></div><div style="flex:1;background:#99CAFF"></div></div>
          <div class="legend" style="color:#D6E9FF"><span><i class="dot" style="background:#fff"></i>집값 중 내 돈 ${wonMan(r.down)}</span><span><i class="dot" style="background:#99CAFF"></i>그 밖의 비용 ${wonMan(r.cost)}</span></div>
          <div style="display:flex;gap:12px;padding-top:16px;border-top:1px solid #4DA2FF">
            <div style="flex:1"><div class="small muted">매달 갚을 돈 (${rules.defaults.years}년 원리금균등)</div><div class="big" style="font-size:22px">약 ${wonMan(Math.round(r.monthly))}</div></div>
            <div style="flex:1"><div class="small muted">집값 중 대출 비율</div><div class="big" style="font-size:22px">${pct(r.loan / st.price)}</div></div></div></div>
        <div class="card"><h2>그 밖의 비용, 하나씩 보기</h2>
          ${[['취득세 (지방교육세 포함)', st.first && st.price <= rules.firstHomeRelief.maxPrice ? '첫 집 감면 반영' : `세율 ${(r.taxRate * 100).toFixed(2)}% + 교육세`, r.tax],
             ['중개 수수료', '법정 최고 요율 + 부가세. 협의로 낮출 수 있어요', r.broker],
             ['국민주택채권', '사자마자 되팔 때 손해 보는 금액 (추정)', r.bond],
             ['법무사 · 등기', '등기 대행 수수료 (대략)', r.legal],
             ['인지세', '매매 계약서에 붙는 세금', r.stamp],
             ['이사비', '직접 입력', st.moving], ['인테리어', '직접 입력', st.interior]]
            .map(([l, n, v]) => `<div class="kv" style="padding:12px 0;border-bottom:1px solid #E5E5EA;align-items:center"><div><div style="font-weight:600">${l}</div><div class="small muted">${n}</div></div><b style="font-size:17px;white-space:nowrap">${wonMan(v)}</b></div>`).join('')}
          <div class="kv" style="padding-top:8px"><b>합계</b><b style="font-size:20px">${wonMan(r.cost)}</b></div></div>
        <div class="card dashed small" style="color:#3C3C43">잊기 쉬운 것: 잔금 날짜와 지금 집 보증금 돌려받는 날짜가 어긋나면 잠깐 돈이 더 필요해요. 대출 서류 인지세 절반도 내 몫이에요.</div>`;
    }
    inputs.forEach((k) => $(k).addEventListener('input', (e) => { st[k] = +e.target.value; if (k === 'price') st.loan = null; render(); }));
    $('first-y').onclick = () => { st.first = true; st.loan = null; render(); };
    $('first-n').onclick = () => { st.first = false; st.loan = null; render(); };
    $('pick').onchange = (e) => { location.hash = '#/calc/' + encodeURIComponent(e.target.value); };
    render();
  }

  // ---------- 화면: 지역 리포트 ----------
  async function regionPage(lawd) {
    const [meta, regions] = await Promise.all([load('meta.json'), load('regions.json')]);
    let rone = null;
    if (meta.hasRone) { try { rone = await load('rone.json'); } catch (e) { rone = null; } }
    const g = regions.find((x) => x.lawd === lawd) || regions[0];
    const s24 = g.series.slice(-24);
    const xs = s24.map((s) => ymLabel(s.ym));
    const lastIdx = s24.length - 1;
    const tipM = (label, key, fmt) => (i) => (s24[i][key] == null ? null : `${ymLabel(s24[i].ym)}<br>${label} <b>${fmt(s24[i][key])}</b>`);
    const perPyeong = (v) => won(v * 3.3058);
    const small = (o) => chart(Object.assign({ w: 520, h: 200, left: 60, maxLabels: 6 }, o));
    const n = g.now;
    const chg = (x, up, down) => (x == null ? '' : `${Math.abs(x * 100).toFixed(1)}% ${x >= 0 ? up : down}`);
    const roneSale = rone && rone.sale && rone.sale[g.name];

    $app.innerHTML = `
    <section class="head"><div>${sampleNote(meta)}
      <h1 class="h1">${esc(g.name)} 지역 리포트</h1>
      <p class="sub">이 동네, 지금 사도 괜찮을까? 실거래를 바탕으로 살펴봤어요.</p></div>
      <div class="chips">${regions.map((x) => `<a class="chip ${x.lawd === g.lawd ? 'on' : ''}" style="display:inline-flex;align-items:center" href="#/region/${x.lawd}">${esc(x.name)}</a>`).join('')}</div>
    </section>
    <section class="card blue" style="padding:32px 36px;flex-direction:row;gap:40px;align-items:center;flex-wrap:wrap">
      <div style="width:340px;display:flex;flex-direction:column;gap:10px"><div class="muted">한 줄 결론</div>
        <div style="font-size:32px;font-weight:800;letter-spacing:-1px">${esc(g.status)}</div>
        <div class="small muted">${esc(g.summary)} (신호 ${g.checkCount || 4}개 중 ${g.okCount}개)</div></div>
      <div class="grid g3" style="flex:1;min-width:300px">
        ${[['평당 가격 (최근 3개월)', perPyeong(n.ppm), n.fromPeak != null ? `동네 고점보다 ${Math.abs(Math.round(n.fromPeak * 100))}% ${n.fromPeak < 0 ? '낮아요' : '높아요'}` : ''],
           ['전세가율', n.jratio ? pct(n.jratio) : '–', '집값 대비 전세 보증금'],
           ['거래량 변화', n.volChange != null ? (n.volChange >= 0 ? '+' : '') + Math.round(n.volChange * 100) + '%' : '–', '최근 6개월 vs 그 전 6개월']]
          .map(([k, v, d]) => `<div style="border:1px solid #4DA2FF;border-radius:14px;padding:18px 20px;display:flex;flex-direction:column;gap:6px"><span class="small muted">${k}</span><span style="font-size:24px;font-weight:800">${v}</span><span class="small muted">${d}</span></div>`).join('')}
      </div>
    </section>
    <section style="display:flex;flex-direction:column;gap:16px">
      <div class="sec-title"><h2>1. 시세 흐름 — 돌아서는 신호가 있나?</h2><span class="small muted">출처: 국토교통부 실거래가${roneSale ? ', 한국부동산원 R-ONE' : ''}</span></div>
      <div class="row">
        <div class="grow grid g2">
          <div class="card"><div class="card-head"><h3>매매 평당 가격</h3><span class="small muted">최근 2년 · 월별 중간값</span></div>
            ${small({ xs, series: [{ vals: s24.map((s) => s.ppm && s.ppm * 3.3058), color: '#007AFF', width: 2.5 }], yFmt: won, tip: (i) => s24[i].ppm ? `${ymLabel(s24[i].ym)}<br>평당 <b>${perPyeong(s24[i].ppm)}</b>` : null, label: '매매 평당 가격' })}
            <div class="small" style="color:#3C3C43">최근 3개월 가격이 그 전보다 ${chg(n.priceChange, '올랐어요', '내렸어요') || '–'}.</div></div>
          <div class="card"><div class="card-head"><h3>전세 평당 보증금</h3><span class="small muted">최근 2년</span></div>
            ${small({ xs, series: [{ vals: s24.map((s) => s.jppm && s.jppm * 3.3058), color: '#007AFF', width: 2.5 }], yFmt: won, tip: (i) => s24[i].jppm ? `${ymLabel(s24[i].ym)}<br>평당 <b>${perPyeong(s24[i].jppm)}</b>` : null, label: '전세 평당 보증금' })}
            <div class="small" style="color:#3C3C43">최근 3개월 전세가 그 전보다 ${chg(n.jeonseChange, '올랐어요', '내렸어요') || '–'}. 전세가 오르면 실제로 살려는 수요가 있다는 뜻이에요.</div></div>
          <div class="card"><div class="card-head"><h3>거래량</h3><span class="small muted">최근 2년 · 월별</span></div>
            ${small({ xs, bars: { vals: s24.map((s) => s.vol), dim: [lastIdx] }, yFmt: (v) => v, tip: tipM('거래', 'vol', (v) => v + '건'), label: '거래량' })}
            <div class="small" style="color:#3C3C43">회색 막대(지난달)는 아직 신고가 다 안 들어와서 적게 보여요. 보통 가격보다 거래량이 먼저 움직여요.</div></div>
          <div class="card"><div class="card-head"><h3>전세가율</h3><span class="small muted">전세 ÷ 매매 (㎡당)</span></div>
            ${small({ xs, series: [{ vals: s24.map((s) => s.jratio), color: '#007AFF', width: 2.5 }], yFmt: (v) => Math.round(v * 100) + '%', tip: tipM('전세가율', 'jratio', (v) => pct(v)), label: '전세가율' })}
            <div class="small" style="color:#3C3C43">전세가율이 오르면 집값을 아래에서 받쳐주는 힘이 커져요.</div></div>
          ${roneSale ? `<div class="card" style="grid-column:1/-1"><div class="card-head"><h3>한국부동산원 주간 아파트 매매가격지수</h3><span class="small muted">최근 1년</span></div>
            ${(() => { const r = roneSale.slice(-52); return chart({ xs: r.map((p) => p.t), series: [{ vals: r.map((p) => p.v), color: '#007AFF', width: 2.5 }], yFmt: (v) => v.toFixed(1), tip: (i) => `${esc(r[i].t)}<br>지수 <b>${r[i].v.toFixed(2)}</b>`, h: 220, maxLabels: 6, label: '주간 매매가격지수' }); })()}</div>` : ''}
        </div>
        <aside class="side card" style="gap:16px"><h3>돌아서는 신호 체크</h3>
          ${g.checks.map((c) => `<div class="check">${checkIcon(c.ok, c.na)}<div class="small"><b>${esc(c.title)}</b><br><span class="muted">${esc(c.detail)}</span></div></div>`).join('')}
          <div class="small" style="background:#F2F2F7;border-radius:10px;padding:12px 14px">${g.checkCount || 4}개 중 ${g.okCount}개 충족 → <b class="accent">${esc(g.status)}</b><br><span class="muted">4개 중 3개 이상(75%): 회복 신호 · 절반: 지켜보기 · 그 아래: 약세</span></div>
        </aside>
      </div>
    </section>
    <section class="grid g2">
      <div class="card dashed"><h2>2. 공급 — 새 집이 한꺼번에 쏟아지진 않나?</h2>
        <div class="small muted">입주 예정 물량, 재건축·재개발 진행 단계, 미분양은 2단계에서 연결해요.</div></div>
      <div class="card dashed"><h2>3. 사람 — 계속 들어오고, 들어올 이유가 있나?</h2>
        <div class="small muted">인구·세대수·20~40대·전입전출, 일자리·학군·교통·상권은 2단계에서 연결해요.</div></div>
    </section>`;
  }

  // ---------- 화면: 찜한 매물 ----------
  async function watch() {
    const units = await load('units.json');
    const changes = favChanges(units);
    $app.innerHTML = `
    <section class="head"><div><h1 class="h1">찜한 매물</h1><p class="sub">찜한 날 이후 새 거래가 생기면 여기서 알려드려요. (이 브라우저에 저장)</p></div></section>
    <section class="list">
      ${changes.length ? changes.map((c) => c.u ? `<a class="list-r" href="#/unit/${encodeURIComponent(c.id)}" style="grid-template-columns:minmax(0,2fr) minmax(0,1fr) minmax(0,1fr) 120px">
        <div><div class="name">${esc(c.u.name)}</div><div class="small muted">${esc(c.u.region)} ${esc(c.u.dong)} · ${c.u.area}㎡ · ${esc(c.saved.saved)} 찜</div></div>
        <div><div style="font-weight:600">${won(c.u.recent)}</div><div class="small muted">찜할 때 ${won(c.saved.recent)}</div></div>
        <div><div class="small muted">마지막 거래</div><div>${dateLabel(c.u.last.date)} · ${wonMan(c.u.last.price)}</div></div>
        <div style="font-weight:700;text-align:right;${c.changed ? 'color:#007AFF' : 'color:#6C6C70'}">${c.changed ? '새 거래' : '변화 없음'}</div></a>`
        : `<div class="list-r" style="grid-template-columns:1fr"><div class="muted">${esc(c.saved.name)} · 지금은 조건에서 빠진 단지예요</div></div>`).join('')
        : '<div class="empty">아직 찜한 곳이 없어요. 단지 상세에서 ‘찜하기’를 눌러 보세요.</div>'}
    </section>`;
  }

  // ---------- 화면: 내 조건 ----------
  async function setting() {
    const rec = await load('recommend.json');
    const f = rec.filters, w = rec.weights;
    const names = { price_drop: '전고점보다 싼지', growth: '오를 가능성', commute: '출퇴근', school: '학군', condition: '단지 컨디션' };
    $app.innerHTML = `
    <section class="head"><div><h1 class="h1">내 조건</h1><p class="sub">조건은 저장소의 <b>config.json</b> 파일에서 바꿔요. 바꾸면 다음 날 아침 추천에 반영돼요.</p></div></section>
    <section class="grid g2">
      <div class="card"><h2>찾는 집</h2>
        ${[['지역', rec.regions.join(', ')], ['전용면적', `${f.area_min_m2}~${f.area_max_m2}㎡`], ['예산 (집값)', won(f.max_price_manwon) + ' 이하'], ['최소 거래 수', `최근 2년 ${f.min_trades_2y}건 이상`], ['가격 계산에서 빼는 거래', `${f.exclude_low_floor_upto}층 이하, ${f.exclude_direct_deal ? '직거래, ' : ''}취소된 거래`]]
          .map(([k, v]) => `<div class="kv" style="padding:10px 0;border-bottom:1px solid #E5E5EA"><span class="muted">${k}</span><b>${esc(v)}</b></div>`).join('')}</div>
      <div class="card"><h2>점수 비중 (합계 100)</h2>
        ${Object.keys(names).map((k) => `<div style="display:flex;align-items:center;gap:12px"><span style="width:120px" class="muted">${names[k]}</span>
          <div style="flex:1;height:10px;background:#E5E5EA;border-radius:5px;overflow:hidden"><div style="width:${w[k]}%;height:100%;background:#007AFF;border-radius:5px"></div></div><b style="width:36px;text-align:right">${w[k]}</b></div>`).join('')}
        <div class="small muted">출퇴근 시간은 구마다 기본값을 쓰고, 동별로 적어 두면 더 정확해져요 (config.json의 commute_by_dong). 학군 좋은 동도 school_by_dong에 적을 수 있어요.</div></div>
    </section>`;
  }

  // ---------- 라우터 ----------
  async function route() {
    const parts = (location.hash.replace(/^#\/?/, '') || '').split('/').map(decodeURIComponent);
    const r = parts[0] || 'home';
    document.querySelectorAll('#nav a').forEach((a) => a.classList.toggle('on', a.dataset.r === (r === 'unit' ? 'home' : r)));
    $tip.style.display = 'none';
    try {
      if (r === 'unit') await unit(parts[1]);
      else if (r === 'calc') await calcPage(parts[1]);
      else if (r === 'region') await regionPage(parts[1]);
      else if (r === 'watch') await watch();
      else if (r === 'setting') await setting();
      else await home();
    } catch (e) {
      console.error(e);
      $app.innerHTML = '<div class="empty">데이터를 불러오지 못했어요. 잠시 뒤 새로고침해 주세요.</div>';
    }
    window.scrollTo(0, 0);
  }
  load('meta.json').then((m) => { document.getElementById('updated').textContent = `${m.updated} 업데이트${m.sample ? ' · 테스트 데이터' : ''}`; }).catch(() => {});
  window.addEventListener('hashchange', route);
  route();
})();
