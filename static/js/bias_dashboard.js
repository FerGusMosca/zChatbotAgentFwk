// static/js/bias_dashboard.js
// TradingView widgets + chart switcher for Bias Fund main dashboard

(function () {
  'use strict';

  // ── Symbol type detection ──────────────────────────────────────────────────
  // Yields/bonds need TradingView.widget (advanced chart)
  // Equities/ETFs use TradingView.MediumWidget
  // Symbols that require the advanced TradingView.widget instead of MediumWidget
  const ADVANCED_CHART_SYMBOLS = ['TVC:US', 'CBOE:VIX'];

  function isYieldSymbol(symbol) {
    return ADVANCED_CHART_SYMBOLS.some(p => symbol.startsWith(p));
  }

  // ── Fallback symbols (used if /api/tv/* endpoints are unreachable) ─────────
  const FALLBACK_TICKER = [
    { symbol: 'AMEX:SPY',    label: 'SPY'   },
    { symbol: 'NASDAQ:QQQ',  label: 'QQQ'   },
    { symbol: 'CBOE:VIX',    label: 'VIX'   },
    { symbol: 'NASDAQ:TLT',  label: 'TLT'   },
    { symbol: 'TVC:US10Y',   label: 'US10Y' },
    { symbol: 'TVC:US02Y',   label: 'US02Y' },
  ];

  const FALLBACK_CHART = [
    { symbol: 'AMEX:SPY',    label: 'SPY',   description: 'S&P 500 ETF' },
    { symbol: 'NASDAQ:QQQ',  label: 'QQQ',   description: 'Nasdaq 100 ETF' },
    { symbol: 'CBOE:VIX',    label: 'VIX',   description: 'Volatility Index' },
    { symbol: 'NASDAQ:TLT',  label: 'TLT',   description: '20yr Treasury ETF' },
    { symbol: 'TVC:US01Y',   label: 'US01Y', description: 'US 1Y Yield' },
    { symbol: 'TVC:US02Y',   label: 'US02Y', description: 'US 2Y Yield' },
    { symbol: 'TVC:US05Y',   label: 'US05Y', description: 'US 5Y Yield' },
    { symbol: 'TVC:US10Y',   label: 'US10Y', description: 'US 10Y Yield' },
  ];

  let activeSymbol = null;

  // ── 1. Ticker tape ─────────────────────────────────────────────────────────
  async function initTickerTape() {
    let symbols;
    try {
      const resp = await fetch('/api/tv/ticker_symbols');
      if (!resp.ok) throw new Error('API unavailable');
      symbols = await resp.json();
    } catch {
      symbols = FALLBACK_TICKER;
    }

    const container = document.getElementById('tickerTapeContainer');
    if (!container) return;

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container';
    const innerDiv = document.createElement('div');
    innerDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.appendChild(innerDiv);
    container.appendChild(widgetDiv);

    new TradingView.widget({
      colorTheme:     'dark',
      isTransparent:  true,
      showSymbolLogo: true,
      displayMode:    'adaptive',
      locale:         'en',
      symbols:        symbols.map(s => ({ proName: s.symbol, title: s.label })),
    });
  }

  // ── 2. Chart switcher tabs ─────────────────────────────────────────────────
  async function initChart() {
    let symbols;
    try {
      const resp = await fetch('/api/tv/chart_symbols');
      if (!resp.ok) throw new Error('API unavailable');
      symbols = await resp.json();
    } catch {
      symbols = FALLBACK_CHART;
    }

    const switcher = document.getElementById('chartSwitcher');
    if (!switcher) return;

    symbols.forEach((s, i) => {
      const btn = document.createElement('button');
      btn.className   = 'bias-chart-tab' + (i === 0 ? ' active' : '');
      btn.textContent = s.label;
      btn.title       = s.description || s.label;
      btn.dataset.symbol = s.symbol;

      btn.addEventListener('click', () => {
        if (s.symbol === activeSymbol) return;
        switcher.querySelectorAll('.bias-chart-tab')
                .forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        loadChart(s.symbol);
      });

      switcher.appendChild(btn);
    });

    if (symbols.length > 0) loadChart(symbols[0].symbol);
  }

  // ── 3. Load chart (equity vs yield — different TradingView widgets) ─────────
  function loadChart(symbol) {
    activeSymbol = symbol;

    const wrap = document.getElementById('tvChartContainer');
    if (!wrap) return;
    wrap.innerHTML = '';

    const uid = 'tv_' + Date.now();
    const div = document.createElement('div');
    div.id = uid;
    wrap.appendChild(div);

    if (isYieldSymbol(symbol)) {
      // ── Advanced chart — required for bonds/yields/rates ─────────────────
      // MediumWidget shows "only available on TradingView" for TVC:* symbols
      new TradingView.widget({
        container_id:       uid,
        symbol:             symbol,
        interval:           'D',
        timezone:           'Etc/UTC',
        theme:              'dark',
        style:              '3',        // line chart
        locale:             'en',
        toolbar_bg:         '#0D1117',
        enable_publishing:  false,
        hide_top_toolbar:   false,
        hide_legend:        true,
        hide_side_toolbar:  true,
        save_image:         false,
        height:             300,
        width:              '100%',
        backgroundColor:    'rgba(0,0,0,0)',
        gridColor:          'rgba(255,255,255,0.04)',
        overrides: {
          'mainSeriesProperties.style': 2,  // line
          'mainSeriesProperties.lineStyle.color': '#58A6FF',
          'mainSeriesProperties.lineStyle.linewidth': 2,
        },
      });

    } else {
      // ── Medium widget — works for equities, ETFs, VIX ───────────────────
      new TradingView.MediumWidget({
        container_id:   uid,
        symbols:        [[symbol, symbol]],
        chartOnly:      false,
        width:          '100%',
        height:         300,
        locale:         'en',
        colorTheme:     'dark',
        isTransparent:  true,
        autosize:       true,
        showVolume:     false,
        scalePosition:  'right',
        scaleMode:      'Normal',
        fontFamily:     'IBM Plex Mono, monospace',
        fontSize:       '10',
        noTimeScale:    false,
        valuesTracking: '1',
        changeMode:     'price-and-percent',
        chartType:      'area',
        lineColor:      '#58A6FF',
        lineWidth:      2,
        backgroundColor:'rgba(0,0,0,0)',
        topColor:       'rgba(88,166,255,0.12)',
        bottomColor:    'rgba(88,166,255,0)',
      });
    }
  }

  // ── Init on DOM ready ──────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    initTickerTape();
    initChart();
  });

})();