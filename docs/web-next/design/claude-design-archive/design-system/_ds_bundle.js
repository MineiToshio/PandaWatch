/* @ds-bundle: {"format":4,"namespace":"PandaWatchDesignSystem_7965ac","components":[],"sourceHashes":{"ui_kits/pandawatch/CatalogView.jsx":"ec2045ffbc21","ui_kits/pandawatch/CollectionView.jsx":"74be8426a913","ui_kits/pandawatch/DetailView.jsx":"6835ff230215","ui_kits/pandawatch/FilterSidebar.jsx":"a5e212a7824b","ui_kits/pandawatch/Header.jsx":"ec8565529c1d","ui_kits/pandawatch/MangaCard.jsx":"ccff1d059e54","ui_kits/pandawatch/data.js":"471c19e9ec8e"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.PandaWatchDesignSystem_7965ac = window.PandaWatchDesignSystem_7965ac || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// ui_kits/pandawatch/CatalogView.jsx
try { (() => {
// PandaWatch UI Kit — Catalog View (Home)
const {
  useState,
  useMemo,
  useEffect
} = React;
const STATS = [{
  value: '2,481',
  label: 'editions tracked'
}, {
  value: '37',
  label: 'countries'
}, {
  value: '126',
  label: 'publishers'
}, {
  value: 'Daily',
  label: 'updates'
}];
function AppliedFilters({
  filters,
  onRemove,
  onClear
}) {
  const chips = [];
  Object.entries(filters).forEach(([key, values]) => {
    (values || []).forEach(val => chips.push({
      key,
      val
    }));
  });
  if (!chips.length) return null;
  const keyLabels = {
    rarity: 'Rarity',
    editionType: 'Type',
    country: 'Country',
    language: 'Lang',
    publisher: 'Publisher',
    status: 'Status'
  };
  const rarityLabels = {
    'accessible': 'Accessible',
    'limited': 'Limited',
    'rare': 'Rare',
    'very-rare': 'Super Rare',
    'ultra-rare': 'Ultra Rare',
    'unknown': 'Unknown'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      flexWrap: 'wrap',
      marginBottom: 12
    }
  }, chips.map(({
    key,
    val
  }) => {
    const label = rarityLabels[val] || val;
    const cfg = key === 'rarity' ? RARITY_CONFIG[val] : null;
    return /*#__PURE__*/React.createElement("div", {
      key: `${key}-${val}`,
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '4px 8px',
        borderRadius: 6,
        fontSize: 12,
        fontWeight: 500,
        background: cfg ? cfg.bg : '#1C1915',
        color: cfg ? cfg.color : '#fff',
        border: `1px solid ${cfg ? cfg.border : 'transparent'}`,
        fontFamily: "'DM Sans',sans-serif"
      }
    }, label, /*#__PURE__*/React.createElement("div", {
      onClick: () => onRemove(key, val),
      style: {
        width: 14,
        height: 14,
        borderRadius: 3,
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: cfg ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.18)'
      }
    }, /*#__PURE__*/React.createElement("svg", {
      width: "8",
      height: "8",
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "3"
    }, /*#__PURE__*/React.createElement("line", {
      x1: "18",
      y1: "6",
      x2: "6",
      y2: "18"
    }), /*#__PURE__*/React.createElement("line", {
      x1: "6",
      y1: "6",
      x2: "18",
      y2: "18"
    }))));
  }), /*#__PURE__*/React.createElement("div", {
    onClick: onClear,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      padding: '4px 10px',
      borderRadius: 6,
      fontSize: 12,
      border: '1px solid #DDD8CF',
      color: '#8C8178',
      cursor: 'pointer',
      background: 'transparent'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "11",
    height: "11",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2.5"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "15",
    y1: "9",
    x2: "9",
    y2: "15"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "9",
    y1: "9",
    x2: "15",
    y2: "15"
  })), "Clear all"));
}
function SortBar({
  sort,
  onSort,
  count,
  viewMode,
  onViewMode,
  isMobile,
  onOpenFilters,
  filterCount
}) {
  const [open, setOpen] = useState(false);
  const current = SORT_OPTIONS.find(o => o.value === sort) || SORT_OPTIONS[0];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 8,
      marginBottom: 14,
      flexWrap: 'wrap'
    }
  }, isMobile && /*#__PURE__*/React.createElement("button", {
    onClick: onOpenFilters,
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '6px 12px',
      borderRadius: 7,
      border: `1.5px solid ${filterCount > 0 ? '#1A8A5A' : '#DDD8CF'}`,
      background: filterCount > 0 ? '#EDFAF3' : '#fff',
      color: filterCount > 0 ? '#1A8A5A' : '#554D49',
      fontSize: 13,
      fontWeight: 500,
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("line", {
    x1: "4",
    y1: "6",
    x2: "20",
    y2: "6"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "8",
    y1: "12",
    x2: "16",
    y2: "12"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "11",
    y1: "18",
    x2: "13",
    y2: "18"
  })), "Filters", filterCount > 0 ? ` (${filterCount})` : ''), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      color: '#8C8178',
      whiteSpace: 'nowrap'
    }
  }, "Sort by"), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative'
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: () => setOpen(!open),
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      padding: '6px 12px',
      borderRadius: 7,
      border: '1.5px solid #DDD8CF',
      background: '#fff',
      fontSize: 13,
      fontWeight: 500,
      color: '#554D49',
      cursor: 'pointer'
    }
  }, current.label, /*#__PURE__*/React.createElement("svg", {
    width: "13",
    height: "13",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#A89E93",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("polyline", {
    points: "6 9 12 15 18 9"
  }))), open && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 'calc(100% + 4px)',
      left: 0,
      zIndex: 50,
      background: '#fff',
      border: '1px solid #DDD8CF',
      borderRadius: 8,
      boxShadow: '0 4px 12px rgba(0,0,0,0.08)',
      minWidth: 180,
      overflow: 'hidden'
    }
  }, SORT_OPTIONS.map(opt => /*#__PURE__*/React.createElement("div", {
    key: opt.value,
    onClick: () => {
      onSort(opt.value);
      setOpen(false);
    },
    style: {
      padding: '9px 14px',
      fontSize: 13,
      cursor: 'pointer',
      color: opt.value === sort ? '#1A8A5A' : '#554D49',
      fontWeight: opt.value === sort ? 500 : 400,
      background: opt.value === sort ? '#EDFAF3' : 'transparent'
    }
  }, opt.label)))), !isMobile && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 4,
      marginLeft: 4
    }
  }, ['grid', 'list'].map(mode => /*#__PURE__*/React.createElement("div", {
    key: mode,
    onClick: () => onViewMode(mode),
    style: {
      width: 32,
      height: 32,
      borderRadius: 6,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      border: `1.5px solid ${viewMode === mode ? '#1A8A5A' : '#DDD8CF'}`,
      color: viewMode === mode ? '#1A8A5A' : '#A89E93',
      background: viewMode === mode ? '#EDFAF3' : '#fff'
    }
  }, mode === 'grid' ? /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("rect", {
    x: "3",
    y: "3",
    width: "7",
    height: "7"
  }), /*#__PURE__*/React.createElement("rect", {
    x: "14",
    y: "3",
    width: "7",
    height: "7"
  }), /*#__PURE__*/React.createElement("rect", {
    x: "14",
    y: "14",
    width: "7",
    height: "7"
  }), /*#__PURE__*/React.createElement("rect", {
    x: "3",
    y: "14",
    width: "7",
    height: "7"
  })) : /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("line", {
    x1: "8",
    y1: "6",
    x2: "21",
    y2: "6"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "8",
    y1: "12",
    x2: "21",
    y2: "12"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "8",
    y1: "18",
    x2: "21",
    y2: "18"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "3",
    y1: "6",
    x2: "3.01",
    y2: "6"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "3",
    y1: "12",
    x2: "3.01",
    y2: "12"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "3",
    y1: "18",
    x2: "3.01",
    y2: "18"
  }))))), /*#__PURE__*/React.createElement("div", {
    style: {
      marginLeft: 'auto',
      fontSize: 12,
      color: '#8C8178',
      whiteSpace: 'nowrap'
    }
  }, count, " edition", count !== 1 ? 's' : '', " found"));
}
function EmptyState({
  onClear
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '64px 24px',
      textAlign: 'center',
      color: '#8C8178'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 56,
      height: 56,
      borderRadius: 14,
      background: '#F5F1EB',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "26",
    height: "26",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#A89E93",
    strokeWidth: "1.5"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "11",
    cy: "11",
    r: "8"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "21",
    y1: "21",
    x2: "16.65",
    y2: "16.65"
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 16,
      fontWeight: 600,
      color: '#1C1915',
      fontFamily: "'Space Grotesk',sans-serif",
      marginBottom: 6
    }
  }, "No editions found"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      lineHeight: 1.6,
      maxWidth: 280,
      marginBottom: 20
    }
  }, "Your current filters returned no results. Try broadening your search or clearing some filters."), /*#__PURE__*/React.createElement("div", {
    onClick: onClear,
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '8px 18px',
      background: '#1A8A5A',
      color: '#fff',
      borderRadius: 8,
      cursor: 'pointer',
      fontSize: 13,
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "13",
    height: "13",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2.5"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "15",
    y1: "9",
    x2: "9",
    y2: "15"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "9",
    y1: "9",
    x2: "15",
    y2: "15"
  })), "Clear all filters"));
}
function CatalogView({
  onSelectItem,
  onSelectCollection,
  isMobile,
  externalQuery,
  onFilterCountChange
}) {
  const [filters, setFilters] = useState({});
  const [sort, setSort] = useState('most-rare');
  const [viewMode, setViewMode] = useState('grid');
  const [showFilters, setShowFilters] = useState(!isMobile);
  const [showMobileSheet, setShowMobileSheet] = useState(false);
  const query = externalQuery || '';
  const filterCount = Object.values(filters).reduce((s, a) => s + (a?.length || 0), 0);
  useEffect(() => {
    onFilterCountChange && onFilterCountChange(filterCount);
  }, [filterCount]);
  const filtered = useMemo(() => filterItems(MANGA_ITEMS, filters, query), [filters, query]);
  const sorted = useMemo(() => sortItems(filtered, sort), [filtered, sort]);
  function removeFilter(key, val) {
    setFilters(f => ({
      ...f,
      [key]: (f[key] || []).filter(v => v !== val)
    }));
  }
  function clearAll() {
    setFilters({});
  }
  const cols = isMobile ? 2 : showFilters ? 4 : 5;
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      background: 'linear-gradient(to bottom, #fff 0%, #F5F1EB 100%)',
      borderBottom: '1px solid #E5E0D8',
      padding: isMobile ? '24px 16px' : '32px 32px 28px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 700
    }
  }, /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "'Space Grotesk',sans-serif",
      fontSize: isMobile ? 22 : 28,
      fontWeight: 700,
      color: '#1C1915',
      letterSpacing: '-0.02em',
      marginBottom: 6,
      lineHeight: 1.2
    }
  }, "Find special manga editions", /*#__PURE__*/React.createElement("br", null), "before they disappear"), /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13,
      color: '#8C8178',
      lineHeight: 1.6,
      marginBottom: 16
    }
  }, "Fanbooks, deluxe prints, box sets, variant covers \u2014 all tracked across ", STATS[1].value, " countries."), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: isMobile ? 16 : 28,
      flexWrap: 'wrap'
    }
  }, STATS.map(s => /*#__PURE__*/React.createElement("div", {
    key: s.label
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: isMobile ? 16 : 18,
      fontWeight: 700,
      fontFamily: "'Space Grotesk',sans-serif",
      color: '#1A8A5A'
    }
  }, s.value), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: '#A89E93',
      marginTop: 1
    }
  }, s.label)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 20,
      padding: isMobile ? '16px 12px' : '20px 24px',
      maxWidth: 1440,
      margin: '0 auto'
    }
  }, !isMobile && showFilters && /*#__PURE__*/React.createElement(FilterSidebar, {
    filters: filters,
    onFiltersChange: setFilters,
    items: MANGA_ITEMS,
    onClear: clearAll
  }), isMobile && showMobileSheet && /*#__PURE__*/React.createElement(MobileFilterSheet, {
    filters: filters,
    onFiltersChange: setFilters,
    items: MANGA_ITEMS,
    onClear: clearAll,
    onClose: () => setShowMobileSheet(false),
    resultCount: sorted.length
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement(SortBar, {
    sort: sort,
    onSort: setSort,
    count: sorted.length,
    viewMode: viewMode,
    onViewMode: setViewMode,
    isMobile: isMobile,
    onOpenFilters: () => setShowMobileSheet(true),
    filterCount: filterCount
  }), /*#__PURE__*/React.createElement(AppliedFilters, {
    filters: filters,
    onRemove: removeFilter,
    onClear: clearAll
  }), sorted.length === 0 ? /*#__PURE__*/React.createElement(EmptyState, {
    onClear: clearAll
  }) : /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: `repeat(${cols}, 1fr)`,
      columnGap: isMobile ? 10 : 16,
      rowGap: isMobile ? 24 : 36,
      // extra row gap so stacked cards' back-peek (extends 16px below) doesn't crash into the next row
      alignItems: 'start'
    }
  }, sorted.map(item => item.type === 'collection' ? /*#__PURE__*/React.createElement(CollectionCard, {
    key: item.id,
    item: item,
    onClick: onSelectCollection
  }) : /*#__PURE__*/React.createElement(MangaCard, {
    key: item.id,
    item: item,
    onClick: onSelectItem
  }))))));
}
Object.assign(window, {
  CatalogView
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/CatalogView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/pandawatch/CollectionView.jsx
try { (() => {
// PandaWatch UI Kit — Collection Detail View
const {
  useState
} = React;
function Breadcrumb({
  crumbs,
  onNavigate
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 6,
      marginBottom: 20,
      flexWrap: 'wrap'
    }
  }, crumbs.map((crumb, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: i
  }, i > 0 && /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#C6BEB4",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("polyline", {
    points: "9 18 15 12 9 6"
  })), /*#__PURE__*/React.createElement("span", {
    onClick: () => crumb.onClick && crumb.onClick(),
    style: {
      fontSize: 13,
      color: crumb.onClick ? '#1A8A5A' : '#1C1915',
      fontWeight: crumb.onClick ? 400 : 500,
      cursor: crumb.onClick ? 'pointer' : 'default',
      fontFamily: "'DM Sans',sans-serif"
    }
  }, crumb.label))));
}
function CollectionView({
  item,
  onSelectItem,
  onBack,
  isMobile
}) {
  const [innerFilter, setInnerFilter] = useState('all');
  const covers = item.volumeCovers || [item.coverScheme, item.coverScheme, item.coverScheme];

  // Generate fake volumes for demo
  const volumes = Array.from({
    length: item.volumes || 3
  }, (_, i) => ({
    ...item,
    id: `${item.id}-vol-${i + 1}`,
    type: 'single',
    title: `${item.series} ${item.editionType} Vol. ${i + 1}`,
    shortTitle: `Vol. ${i + 1}`,
    coverScheme: covers[i % covers.length] || item.coverScheme,
    score: Math.max(10, item.score - i * 2),
    rarity: scoreToRarity(Math.max(10, item.score - i * 2)),
    rarityConfig: RARITY_CONFIG[scoreToRarity(Math.max(10, item.score - i * 2))],
    isbn: `978${Math.floor(Math.random() * 9000000000 + 1000000000)}`,
    publishedAt: `${2018 + Math.floor(i / 2)}-${String(i % 12 + 1).padStart(2, '0')}-01`,
    status: i === 0 ? 'new' : i === 1 ? 'changed' : null
  }));
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100vh'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#fff',
      borderBottom: '1px solid #E5E0D8',
      padding: isMobile ? '20px 16px' : '28px 32px'
    }
  }, /*#__PURE__*/React.createElement(Breadcrumb, {
    crumbs: [{
      label: 'Catalog',
      onClick: onBack
    }, {
      label: 'Collections'
    }, {
      label: item.title
    }],
    onNavigate: onBack
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: isMobile ? 16 : 32,
      alignItems: 'flex-start',
      flexWrap: isMobile ? 'wrap' : 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      flexShrink: 0,
      width: isMobile ? 116 : 156,
      // card_width + max right peek (12)
      paddingRight: 12,
      paddingBottom: 16,
      // gutter for back peeks
      boxSizing: 'border-box'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 16,
      left: 12,
      right: 0,
      bottom: 0,
      zIndex: 1,
      borderRadius: 10,
      background: '#D6CFC0',
      border: '1px solid #BAB2A1',
      boxShadow: '0 1px 6px rgba(0,0,0,0.06)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 8,
      left: 6,
      right: 6,
      bottom: 8,
      zIndex: 2,
      borderRadius: 10,
      background: '#E2DCCE',
      border: '1px solid #C9C2B1',
      boxShadow: '0 2px 8px rgba(0,0,0,0.07)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      zIndex: 3,
      width: '100%',
      aspectRatio: '2/3',
      borderRadius: 10,
      overflow: 'hidden',
      border: '1px solid #E5E0D8',
      boxShadow: '0 4px 18px rgba(0,0,0,0.13), 0 1px 4px rgba(0,0,0,0.07)'
    }
  }, /*#__PURE__*/React.createElement(CoverPlaceholder, {
    scheme: covers[0],
    series: "",
    title: ""
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: '#A89E93',
      fontWeight: 500,
      letterSpacing: '0.07em',
      textTransform: 'uppercase',
      marginBottom: 4
    }
  }, item.series), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "'Space Grotesk',sans-serif",
      fontSize: isMobile ? 20 : 26,
      fontWeight: 700,
      color: '#1C1915',
      letterSpacing: '-0.02em',
      marginBottom: 10,
      lineHeight: 1.2
    }
  }, item.title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8,
      marginBottom: 14,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(RarityBadge, {
    rarity: item.rarity,
    size: "md"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      padding: '4px 10px',
      borderRadius: 5,
      background: '#F5F1EB',
      color: '#554D49',
      fontSize: 12,
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("rect", {
    x: "3",
    y: "3",
    width: "18",
    height: "18",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3 9h18M9 21V9"
  })), item.volumes, " volumes"), item.status && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '4px 10px',
      borderRadius: 999,
      fontSize: 11,
      fontWeight: 600,
      background: item.status === 'new' ? '#FEF3EF' : '#FFFBEB',
      color: item.status === 'new' ? '#D93D1A' : '#9E6C00',
      border: `1px solid ${item.status === 'new' ? '#FABEAD' : '#FDE68A'}`
    }
  }, item.status === 'new' ? 'New' : 'Changed')), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4,auto)',
      gap: '8px 20px',
      marginBottom: 14
    }
  }, [{
    icon: 'globe',
    label: 'Publisher',
    value: item.publisher
  }, {
    icon: 'map',
    label: 'Country',
    value: item.country
  }, {
    icon: 'lang',
    label: 'Language',
    value: item.language
  }, {
    icon: 'cal',
    label: 'First Release',
    value: item.publishedAt?.slice(0, 4)
  }].map(m => /*#__PURE__*/React.createElement("div", {
    key: m.label
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: '#A89E93',
      fontWeight: 500,
      letterSpacing: '0.07em',
      textTransform: 'uppercase',
      marginBottom: 2
    }
  }, m.label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 500,
      color: '#1C1915'
    }
  }, m.value)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 6
    }
  }, item.signals.map(sig => /*#__PURE__*/React.createElement("div", {
    key: sig,
    style: {
      padding: '3px 8px',
      borderRadius: 999,
      background: '#EDE9E2',
      color: '#706560',
      fontSize: 11,
      fontWeight: 500
    }
  }, sig)))))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: isMobile ? '16px 12px' : '20px 32px',
      maxWidth: 1440,
      margin: '0 auto'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      fontWeight: 600,
      fontFamily: "'Space Grotesk',sans-serif",
      color: '#1C1915',
      whiteSpace: 'nowrap'
    }
  }, "All ", item.volumes, " Volumes"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6
    }
  }, ['all', 'new', 'changed'].map(f => /*#__PURE__*/React.createElement("div", {
    key: f,
    onClick: () => setInnerFilter(f),
    style: {
      padding: '4px 12px',
      borderRadius: 999,
      fontSize: 11,
      fontWeight: 500,
      border: `1.5px solid ${innerFilter === f ? '#1A8A5A' : '#DDD8CF'}`,
      background: innerFilter === f ? '#EDFAF3' : '#fff',
      color: innerFilter === f ? '#1A8A5A' : '#706560',
      cursor: 'pointer',
      textTransform: 'capitalize'
    }
  }, f)))), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: isMobile ? 'repeat(2,1fr)' : 'repeat(5,1fr)',
      gap: isMobile ? 10 : 16,
      alignItems: 'start'
    }
  }, volumes.filter(v => innerFilter === 'all' || v.status === innerFilter).map(vol => /*#__PURE__*/React.createElement(MangaCard, {
    key: vol.id,
    item: vol,
    onClick: onSelectItem
  })))));
}
Object.assign(window, {
  CollectionView,
  Breadcrumb
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/CollectionView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/pandawatch/DetailView.jsx
try { (() => {
// PandaWatch UI Kit — Manga Detail View
const {
  useState
} = React;
function MetaRow({
  label,
  value,
  mono = false
}) {
  if (!value) return null;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: '140px 1fr',
      gap: 8,
      padding: '8px 0',
      borderBottom: '1px solid #EDE9E2',
      alignItems: 'start'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: '#A89E93',
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      paddingTop: 1
    }
  }, label), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      color: '#1C1915',
      fontFamily: mono ? "'JetBrains Mono',monospace" : "'DM Sans',sans-serif",
      wordBreak: 'break-all'
    }
  }, value));
}
function SignalCard({
  signal
}) {
  const descriptions = {
    'fanbook': 'Official companion book — not a standard volume. Contains artwork, interviews, or supplementary content.',
    'deluxe': 'Premium oversized format with higher production quality, improved paper, or bonus content.',
    'box-set': 'Multi-volume boxed set — physical packaging distinguishes it from individual volumes.',
    'variant-cover': 'Alternate cover art distinguishes this from the standard release.',
    'limited': 'Limited production run — fewer copies than a standard release.',
    'hardcover': 'Hardcover binding instead of standard softcover/paperback.',
    'anniversary': 'Released to commemorate a series milestone or anniversary.',
    'exhibition': 'Produced in conjunction with an official exhibit or event.',
    'celebration': 'Special celebratory release tied to a milestone in the series.',
    'limited-print': 'Explicitly limited print quantity stated by publisher.',
    'oversized': 'Larger than standard tankobon format — expanded physical dimensions.',
    'special-cover': 'Non-standard cover treatment — foil, embossing, alternate art, etc.'
  };
  const colors = {
    'fanbook': {
      bg: '#EDFAF3',
      color: '#1A8A5A',
      border: '#A6DFCA'
    },
    'deluxe': {
      bg: '#EEF2FF',
      color: '#2D52CC',
      border: '#C7D2FE'
    },
    'box-set': {
      bg: '#F5F3FF',
      color: '#7C3AED',
      border: '#DDD6FE'
    },
    'variant-cover': {
      bg: '#FFFBEB',
      color: '#9E6C00',
      border: '#FDE68A'
    },
    'limited': {
      bg: '#FEF3EF',
      color: '#D93D1A',
      border: '#FABEAD'
    },
    'limited-print': {
      bg: '#FEF3EF',
      color: '#D93D1A',
      border: '#FABEAD'
    }
  };
  const c = colors[signal] || {
    bg: '#F5F1EB',
    color: '#706560',
    border: '#DDD8CF'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: c.bg,
      border: `1px solid ${c.border}`,
      borderRadius: 8,
      padding: '10px 12px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      color: c.color,
      fontFamily: "'Space Grotesk',sans-serif",
      marginBottom: 3,
      textTransform: 'capitalize'
    }
  }, signal.replace(/-/g, ' ')), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: '#706560',
      lineHeight: 1.5
    }
  }, descriptions[signal] || 'Distinctive signal detected by PandaWatch.'));
}
function DetailView({
  item,
  onBack,
  isMobile
}) {
  const [activeSection, setActiveSection] = useState(null);
  const toggleSection = s => setActiveSection(activeSection === s ? null : s);
  const SourceBadge = ({
    cls
  }) => {
    const map = {
      trusted_media: {
        label: 'Trusted Media',
        color: '#1A8A5A',
        bg: '#EDFAF3',
        border: '#A6DFCA'
      },
      publisher: {
        label: 'Publisher Direct',
        color: '#2D52CC',
        bg: '#EEF2FF',
        border: '#C7D2FE'
      },
      marketplace: {
        label: 'Marketplace Signal',
        color: '#9E6C00',
        bg: '#FFFBEB',
        border: '#FDE68A'
      }
    };
    const m = map[cls] || {
      label: cls,
      color: '#9CA3AF',
      bg: '#F9FAFB',
      border: '#E5E7EB'
    };
    return /*#__PURE__*/React.createElement("div", {
      style: {
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '3px 9px',
        borderRadius: 5,
        border: `1px solid ${m.border}`,
        background: m.bg,
        fontSize: 11,
        fontWeight: 500,
        color: m.color
      }
    }, /*#__PURE__*/React.createElement("svg", {
      width: "10",
      height: "10",
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "currentColor",
      strokeWidth: "2"
    }, /*#__PURE__*/React.createElement("path", {
      d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"
    })), m.label);
  };
  const SectionHeader = ({
    id,
    title,
    children
  }) => /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: () => isMobile && toggleSection(id),
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: !isMobile || activeSection === id || activeSection === null ? 12 : 0,
      cursor: isMobile ? 'pointer' : 'default',
      paddingBottom: 8,
      borderBottom: '1px solid #E5E0D8'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      color: '#1C1915',
      fontFamily: "'Space Grotesk',sans-serif"
    }
  }, title), isMobile && /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#A89E93",
    strokeWidth: "2",
    style: {
      transform: activeSection === id || !isMobile ? 'rotate(180deg)' : 'none',
      transition: 'transform 150ms'
    }
  }, /*#__PURE__*/React.createElement("polyline", {
    points: "6 9 12 15 18 9"
  }))), (!isMobile || activeSection === id || activeSection === null) && children);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      minHeight: '100vh'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#fff',
      borderBottom: '1px solid #E5E0D8',
      padding: isMobile ? '16px 16px 0' : '20px 32px 0'
    }
  }, /*#__PURE__*/React.createElement(Breadcrumb, {
    crumbs: [{
      label: 'Catalog',
      onClick: onBack
    }, {
      label: item.series
    }, {
      label: item.shortTitle
    }]
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      maxWidth: 1200,
      margin: '0 auto',
      padding: isMobile ? '16px 12px' : '28px 32px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 40,
      alignItems: 'flex-start',
      flexWrap: isMobile ? 'wrap' : 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: isMobile ? '100%' : 300,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      borderRadius: 12,
      overflow: 'hidden',
      border: '1px solid #E5E0D8',
      boxShadow: '0 4px 16px rgba(0,0,0,0.08)',
      aspectRatio: '2/3',
      position: 'relative',
      marginBottom: 14,
      maxWidth: isMobile ? 200 : '100%',
      margin: isMobile ? '0 auto 14px' : '0 0 14px'
    }
  }, /*#__PURE__*/React.createElement(CoverPlaceholder, {
    scheme: item.coverScheme,
    series: item.series,
    title: item.shortTitle
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("a", {
    href: item.sourceUrl || '#',
    target: "_blank",
    rel: "noopener noreferrer",
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      padding: '10px',
      border: '1.5px solid #DDD8CF',
      borderRadius: 8,
      fontSize: 13,
      fontWeight: 500,
      color: '#554D49',
      textDecoration: 'none',
      background: '#fff'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"
  }), /*#__PURE__*/React.createElement("polyline", {
    points: "15 3 21 3 21 9"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "10",
    y1: "14",
    x2: "21",
    y2: "3"
  })), "View original source"))), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 6,
      fontSize: 12,
      color: '#A89E93',
      fontWeight: 500,
      letterSpacing: '0.06em',
      textTransform: 'uppercase'
    }
  }, item.series), /*#__PURE__*/React.createElement("h1", {
    style: {
      fontFamily: "'Space Grotesk',sans-serif",
      fontSize: isMobile ? 20 : 24,
      fontWeight: 700,
      color: '#1C1915',
      letterSpacing: '-0.02em',
      marginBottom: 12,
      lineHeight: 1.25
    }
  }, item.title), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8,
      marginBottom: 16,
      alignItems: 'center'
    }
  }, /*#__PURE__*/React.createElement(RarityBadge, {
    rarity: item.rarity,
    size: "md"
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '4px 10px',
      borderRadius: 5,
      background: '#F5F1EB',
      color: '#554D49',
      fontSize: 12,
      fontWeight: 500,
      fontFamily: "'DM Sans',sans-serif"
    }
  }, item.editionType), item.status && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '4px 10px',
      borderRadius: 999,
      fontSize: 11,
      fontWeight: 600,
      background: item.status === 'new' ? '#FEF3EF' : '#FFFBEB',
      color: item.status === 'new' ? '#D93D1A' : '#9E6C00',
      border: `1px solid ${item.status === 'new' ? '#FABEAD' : '#FDE68A'}`
    }
  }, item.status === 'new' ? '● New' : '↻ Changed')), /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 24
    }
  }, /*#__PURE__*/React.createElement(MetaRow, {
    label: "Series",
    value: item.series
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "Edition",
    value: item.editionType
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "Publisher",
    value: item.publisher
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "Country",
    value: item.country
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "Language",
    value: item.language
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "ISBN",
    value: item.isbn,
    mono: true
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "Price",
    value: item.price
  }), /*#__PURE__*/React.createElement(MetaRow, {
    label: "Published",
    value: item.publishedAt
  })), /*#__PURE__*/React.createElement(SectionHeader, {
    id: "signals",
    title: "Why it was detected"
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      fontSize: 13,
      color: '#8C8178',
      lineHeight: 1.6,
      marginBottom: 12
    }
  }, "Rarity estimated from signals, source class, and availability data. PandaWatch flagged this edition for the following reasons:"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'grid',
      gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr',
      gap: 8
    }
  }, (item.signals || []).map(sig => /*#__PURE__*/React.createElement(SignalCard, {
    key: sig,
    signal: sig
  })))), /*#__PURE__*/React.createElement(SectionHeader, {
    id: "notes",
    title: "Collector Notes"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      background: '#F5F1EB',
      border: '1px dashed #C6BEB4',
      borderRadius: 8,
      padding: '16px',
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      color: '#A89E93'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "18",
    height: "18",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.5"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
  })), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 500,
      color: '#8C8178',
      marginBottom: 2
    }
  }, "Wishlist & notes coming soon"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: '#A89E93'
    }
  }, "Track your collection, add personal notes, and mark items as owned or wanted.")))), /*#__PURE__*/React.createElement(SectionHeader, {
    id: "confidence",
    title: "Data Confidence"
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: '#8C8178'
    }
  }, "Source class"), /*#__PURE__*/React.createElement(SourceBadge, {
    cls: item.sourceClass
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingTop: 8,
      borderTop: '1px solid #EDE9E2'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: '#8C8178'
    }
  }, "Source"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: '#1C1915',
      fontWeight: 500
    }
  }, item.source)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingTop: 8,
      borderTop: '1px solid #EDE9E2'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: '#8C8178'
    }
  }, "Detected at"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: '#1C1915',
      fontFamily: "'JetBrains Mono',monospace"
    }
  }, item.detectedAt)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingTop: 8,
      borderTop: '1px solid #EDE9E2'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      color: '#8C8178'
    }
  }, "Rarity score"), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontFamily: "'JetBrains Mono',monospace",
      fontWeight: 500,
      color: '#1C1915'
    }
  }, item.score ?? 'n/a', " / 100")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 6,
      paddingTop: 8,
      borderTop: '1px solid #EDE9E2'
    }
  }, (item.tags || []).map(tag => /*#__PURE__*/React.createElement("div", {
    key: tag,
    style: {
      padding: '2px 7px',
      borderRadius: 3,
      background: '#EDE9E2',
      color: '#706560',
      fontSize: 10,
      fontFamily: "'JetBrains Mono',monospace"
    }
  }, tag)))))))));
}
Object.assign(window, {
  DetailView
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/DetailView.jsx", error: String((e && e.message) || e) }); }

// ui_kits/pandawatch/FilterSidebar.jsx
try { (() => {
// PandaWatch UI Kit — Filter Sidebar + Mobile Bottom Sheet
const {
  useState
} = React;
const RARITY_LABELS = {
  'accessible': 'Accessible',
  'limited': 'Limited',
  'rare': 'Rare',
  'very-rare': 'Super Rare',
  'ultra-rare': 'Ultra Rare',
  'unknown': 'Unknown'
};
function FilterGroup({
  title,
  options,
  selected,
  onToggle,
  counts = {}
}) {
  const [expanded, setExpanded] = useState(true);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: () => setExpanded(!expanded),
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: expanded ? 8 : 0,
      cursor: 'pointer'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 12,
      fontWeight: 600,
      color: '#1C1915',
      fontFamily: "'Space Grotesk',sans-serif"
    }
  }, title, selected.length > 0 && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 6,
      background: '#1A8A5A',
      color: '#fff',
      borderRadius: 999,
      fontSize: 9,
      fontWeight: 700,
      padding: '1px 5px',
      verticalAlign: 'middle'
    }
  }, selected.length)), /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#A89E93",
    strokeWidth: "2",
    style: {
      transform: expanded ? 'rotate(180deg)' : 'none',
      transition: 'transform 150ms'
    }
  }, /*#__PURE__*/React.createElement("polyline", {
    points: "6 9 12 15 18 9"
  }))), expanded && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexDirection: 'column',
      gap: 2
    }
  }, options.map(opt => {
    const isChecked = selected.includes(opt);
    const label = RARITY_LABELS[opt] || opt;
    const count = counts[opt] || 0;
    return /*#__PURE__*/React.createElement("div", {
      key: opt,
      onClick: () => onToggle(opt),
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '5px 4px',
        borderRadius: 5,
        cursor: 'pointer',
        background: isChecked ? '#EDFAF3' : 'transparent',
        transition: 'background 100ms'
      }
    }, /*#__PURE__*/React.createElement("div", {
      style: {
        width: 15,
        height: 15,
        borderRadius: 3,
        flexShrink: 0,
        border: `1.5px solid ${isChecked ? '#1A8A5A' : '#DDD8CF'}`,
        background: isChecked ? '#1A8A5A' : '#fff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 120ms'
      }
    }, isChecked && /*#__PURE__*/React.createElement("svg", {
      width: "9",
      height: "9",
      viewBox: "0 0 24 24",
      fill: "none",
      stroke: "white",
      strokeWidth: "3"
    }, /*#__PURE__*/React.createElement("polyline", {
      points: "20 6 9 17 4 12"
    }))), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 12,
        color: isChecked ? '#1A8A5A' : '#554D49',
        flex: 1,
        fontWeight: isChecked ? 500 : 400
      }
    }, label), count > 0 && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 10,
        color: '#A89E93'
      }
    }, count));
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      background: '#EDE9E2',
      marginTop: 14
    }
  }));
}
function FilterSidebar({
  filters,
  onFiltersChange,
  items,
  onClear
}) {
  function getCounts(key, mapFn) {
    return items.reduce((acc, item) => {
      const val = mapFn ? mapFn(item) : item[key];
      if (val) acc[val] = (acc[val] || 0) + 1;
      return acc;
    }, {});
  }
  function toggle(key, value) {
    const cur = filters[key] || [];
    const next = cur.includes(value) ? cur.filter(v => v !== value) : [...cur, value];
    onFiltersChange({
      ...filters,
      [key]: next
    });
  }
  const totalActive = Object.values(filters).reduce((s, a) => s + (a?.length || 0), 0);
  return /*#__PURE__*/React.createElement("div", {
    style: {
      width: 272,
      flexShrink: 0,
      background: '#fff',
      borderRadius: 10,
      border: '1px solid #E5E0D8',
      boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      padding: '16px 16px 8px',
      alignSelf: 'flex-start',
      position: 'sticky',
      top: 76,
      maxHeight: 'calc(100vh - 96px)',
      overflowY: 'auto'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 16
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      fontWeight: 600,
      color: '#1C1915',
      fontFamily: "'Space Grotesk',sans-serif"
    }
  }, "Filters"), totalActive > 0 && /*#__PURE__*/React.createElement("span", {
    onClick: onClear,
    style: {
      fontSize: 11,
      color: '#D93D1A',
      cursor: 'pointer',
      fontWeight: 500
    }
  }, "Clear all")), /*#__PURE__*/React.createElement(FilterGroup, {
    title: "Rarity",
    options: FILTER_OPTIONS.rarity,
    selected: filters.rarity || [],
    onToggle: v => toggle('rarity', v),
    counts: getCounts('rarity')
  }), /*#__PURE__*/React.createElement(FilterGroup, {
    title: "Edition Type",
    options: FILTER_OPTIONS.editionType,
    selected: filters.editionType || [],
    onToggle: v => toggle('editionType', v),
    counts: getCounts('editionType')
  }), /*#__PURE__*/React.createElement(FilterGroup, {
    title: "Country",
    options: FILTER_OPTIONS.country,
    selected: filters.country || [],
    onToggle: v => toggle('country', v),
    counts: getCounts('country')
  }), /*#__PURE__*/React.createElement(FilterGroup, {
    title: "Language",
    options: FILTER_OPTIONS.language,
    selected: filters.language || [],
    onToggle: v => toggle('language', v),
    counts: getCounts('language')
  }), /*#__PURE__*/React.createElement(FilterGroup, {
    title: "Publisher",
    options: FILTER_OPTIONS.publisher,
    selected: filters.publisher || [],
    onToggle: v => toggle('publisher', v),
    counts: getCounts('publisher')
  }), /*#__PURE__*/React.createElement(FilterGroup, {
    title: "Status",
    options: FILTER_OPTIONS.status,
    selected: filters.status || [],
    onToggle: v => toggle('status', v),
    counts: getCounts('status')
  }));
}

// ── Mobile Bottom Sheet ───────────────────────────────────────
function MobileFilterSheet({
  filters,
  onFiltersChange,
  items,
  onClear,
  onClose,
  resultCount
}) {
  const [activeTab, setActiveTab] = useState('rarity');
  const tabs = [{
    key: 'rarity',
    label: 'Rarity'
  }, {
    key: 'editionType',
    label: 'Type'
  }, {
    key: 'country',
    label: 'Country'
  }, {
    key: 'publisher',
    label: 'Publisher'
  }];
  function toggle(key, value) {
    const cur = filters[key] || [];
    const next = cur.includes(value) ? cur.filter(v => v !== value) : [...cur, value];
    onFiltersChange({
      ...filters,
      [key]: next
    });
  }
  const totalActive = Object.values(filters).reduce((s, a) => s + (a?.length || 0), 0);
  const activeOptions = FILTER_OPTIONS[activeTab] || [];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'fixed',
      inset: 0,
      zIndex: 200,
      background: 'rgba(28,25,21,0.4)',
      backdropFilter: 'blur(3px)',
      display: 'flex',
      flexDirection: 'column',
      justifyContent: 'flex-end'
    },
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    onClick: e => e.stopPropagation(),
    style: {
      background: '#fff',
      borderRadius: '16px 16px 0 0',
      padding: '0 0 24px',
      boxShadow: '0 -12px 40px rgba(0,0,0,0.15)',
      maxHeight: '80vh',
      display: 'flex',
      flexDirection: 'column'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      justifyContent: 'center',
      padding: '10px 0 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: 36,
      height: 4,
      background: '#DDD8CF',
      borderRadius: 2
    }
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '12px 18px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      fontWeight: 600,
      color: '#1C1915',
      fontFamily: "'Space Grotesk',sans-serif"
    }
  }, "Filters"), totalActive > 0 && /*#__PURE__*/React.createElement("span", {
    onClick: onClear,
    style: {
      fontSize: 12,
      color: '#D93D1A',
      cursor: 'pointer',
      fontWeight: 500
    }
  }, "Clear all")), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      gap: 6,
      padding: '12px 18px 0',
      overflowX: 'auto'
    }
  }, tabs.map(tab => {
    const count = (filters[tab.key] || []).length;
    return /*#__PURE__*/React.createElement("div", {
      key: tab.key,
      onClick: () => setActiveTab(tab.key),
      style: {
        padding: '5px 14px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 500,
        border: `1.5px solid ${activeTab === tab.key ? '#1A8A5A' : '#DDD8CF'}`,
        background: activeTab === tab.key ? '#EDFAF3' : '#fff',
        color: activeTab === tab.key ? '#1A8A5A' : '#706560',
        cursor: 'pointer',
        flexShrink: 0,
        whiteSpace: 'nowrap'
      }
    }, tab.label, count > 0 ? ` (${count})` : '');
  })), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      overflowY: 'auto',
      padding: '14px 18px 0',
      borderTop: '1px solid #EDE9E2',
      marginTop: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      flexWrap: 'wrap',
      gap: 8
    }
  }, activeOptions.map(opt => {
    const label = RARITY_LABELS[opt] || opt;
    const isSelected = (filters[activeTab] || []).includes(opt);
    return /*#__PURE__*/React.createElement("div", {
      key: opt,
      onClick: () => toggle(activeTab, opt),
      style: {
        padding: '6px 14px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 500,
        border: `1.5px solid ${isSelected ? '#1A8A5A' : '#DDD8CF'}`,
        background: isSelected ? '#EDFAF3' : '#fff',
        color: isSelected ? '#1A8A5A' : '#706560',
        cursor: 'pointer'
      }
    }, label);
  }))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '16px 18px 0'
    }
  }, /*#__PURE__*/React.createElement("div", {
    onClick: onClose,
    style: {
      background: '#1A8A5A',
      color: '#fff',
      borderRadius: 8,
      padding: '12px',
      textAlign: 'center',
      cursor: 'pointer',
      fontSize: 14,
      fontWeight: 600,
      fontFamily: "'Space Grotesk',sans-serif"
    }
  }, "Show ", resultCount, " result", resultCount !== 1 ? 's' : ''))));
}
Object.assign(window, {
  FilterSidebar,
  MobileFilterSheet
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/FilterSidebar.jsx", error: String((e && e.message) || e) }); }

// ui_kits/pandawatch/Header.jsx
try { (() => {
// PandaWatch UI Kit — Header + Search Component
const {
  useState,
  useRef,
  useEffect
} = React;
const PandaLogo = () => /*#__PURE__*/React.createElement("img", {
  src: "../../assets/panda-mark.png",
  width: "32",
  height: "32",
  alt: "PandaWatch",
  style: {
    flexShrink: 0,
    display: 'block',
    objectFit: 'contain'
  }
});
const headerStyles = {
  header: {
    position: 'sticky',
    top: 0,
    zIndex: 100,
    background: '#fff',
    borderBottom: '1px solid #E5E0D8',
    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
    display: 'flex',
    alignItems: 'center',
    gap: 16,
    padding: '0 24px',
    height: 60
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    textDecoration: 'none',
    flexShrink: 0,
    cursor: 'pointer'
  },
  wordmark: {
    fontFamily: "'Space Grotesk',sans-serif",
    fontSize: 17,
    letterSpacing: '-0.02em'
  },
  searchWrap: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    background: '#F5F1EB',
    border: '1.5px solid #DDD8CF',
    borderRadius: 8,
    padding: '0 14px',
    height: 38,
    transition: 'border-color 150ms, box-shadow 150ms, background 150ms'
  },
  searchWrapFocused: {
    borderColor: '#1A8A5A',
    boxShadow: '0 0 0 3px rgba(26,138,90,0.12)',
    background: '#fff'
  },
  searchInput: {
    flex: 1,
    border: 'none',
    background: 'transparent',
    outline: 'none',
    fontFamily: "'DM Sans',sans-serif",
    fontSize: 14,
    color: '#1C1915'
  },
  filterBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '0 14px',
    height: 36,
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 500,
    color: '#554D49',
    border: '1.5px solid #DDD8CF',
    cursor: 'pointer',
    transition: 'border-color 120ms, color 120ms',
    background: 'transparent',
    flexShrink: 0
  },
  filterBtnActive: {
    borderColor: '#1A8A5A',
    color: '#1A8A5A'
  },
  filterBadge: {
    background: '#1A8A5A',
    color: '#fff',
    borderRadius: 999,
    fontSize: 10,
    fontWeight: 700,
    minWidth: 16,
    height: 16,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '0 4px'
  },
  iconBtn: {
    width: 36,
    height: 36,
    borderRadius: 8,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    color: '#706560',
    cursor: 'pointer',
    border: '1px solid transparent',
    flexShrink: 0
  }
};
function Header({
  query,
  onQueryChange,
  onToggleFilters,
  filterCount,
  view,
  onLogoClick
}) {
  const [focused, setFocused] = useState(false);
  const inputRef = useRef(null);
  const activeFilters = filterCount > 0;
  return /*#__PURE__*/React.createElement("header", {
    style: headerStyles.header
  }, /*#__PURE__*/React.createElement("div", {
    style: headerStyles.logo,
    onClick: onLogoClick,
    role: "button",
    tabIndex: 0
  }, /*#__PURE__*/React.createElement(PandaLogo, null), /*#__PURE__*/React.createElement("div", {
    style: headerStyles.wordmark
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 600,
      color: '#1C1915'
    }
  }, "Panda"), /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 400,
      color: '#1A8A5A'
    }
  }, "Watch"))), /*#__PURE__*/React.createElement("div", {
    style: {
      ...headerStyles.searchWrap,
      ...(focused ? headerStyles.searchWrapFocused : {})
    },
    onClick: () => inputRef.current?.focus()
  }, /*#__PURE__*/React.createElement("svg", {
    width: "16",
    height: "16",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: focused ? '#1A8A5A' : '#A89E93',
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "11",
    cy: "11",
    r: "8"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "21",
    y1: "21",
    x2: "16.65",
    y2: "16.65"
  })), /*#__PURE__*/React.createElement("input", {
    ref: inputRef,
    type: "text",
    placeholder: "Search by manga, series, publisher, ISBN\u2026",
    value: query,
    onChange: e => onQueryChange(e.target.value),
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
    style: headerStyles.searchInput
  }), query && /*#__PURE__*/React.createElement("div", {
    onClick: () => onQueryChange(''),
    style: {
      cursor: 'pointer',
      color: '#A89E93',
      display: 'flex'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "15",
    y1: "9",
    x2: "9",
    y2: "15"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "9",
    y1: "9",
    x2: "15",
    y2: "15"
  })))), view === 'catalog' && /*#__PURE__*/React.createElement("button", {
    style: {
      ...headerStyles.filterBtn,
      ...(activeFilters ? headerStyles.filterBtnActive : {})
    },
    onClick: onToggleFilters
  }, /*#__PURE__*/React.createElement("svg", {
    width: "14",
    height: "14",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("line", {
    x1: "4",
    y1: "6",
    x2: "20",
    y2: "6"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "8",
    y1: "12",
    x2: "16",
    y2: "12"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "11",
    y1: "18",
    x2: "13",
    y2: "18"
  })), "Filters", filterCount > 0 && /*#__PURE__*/React.createElement("div", {
    style: headerStyles.filterBadge
  }, filterCount)));
}
Object.assign(window, {
  Header,
  PandaLogo
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/Header.jsx", error: String((e && e.message) || e) }); }

// ui_kits/pandawatch/MangaCard.jsx
try { (() => {
// PandaWatch UI Kit — Manga Card & Collection Card Components
const {
  useState
} = React;

// ── Rarity Badge ─────────────────────────────────────────────
function RarityIcon({
  type,
  size = 12
}) {
  const s = {
    width: size,
    height: size,
    flexShrink: 0
  };
  switch (type) {
    case 'circle':
      return /*#__PURE__*/React.createElement("svg", {
        style: s,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: "2.5"
      }, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "10"
      }));
    case 'star':
      return /*#__PURE__*/React.createElement("svg", {
        style: s,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: "2"
      }, /*#__PURE__*/React.createElement("polygon", {
        points: "12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"
      }));
    case 'star2':
      return /*#__PURE__*/React.createElement("svg", {
        style: s,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: "2"
      }, /*#__PURE__*/React.createElement("path", {
        d: "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"
      }));
    case 'sparkle':
      return /*#__PURE__*/React.createElement("svg", {
        style: s,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: "2"
      }, /*#__PURE__*/React.createElement("path", {
        d: "M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z"
      }), /*#__PURE__*/React.createElement("path", {
        d: "M5 17l.75 2.25L8 20l-2.25.75L5 23l-.75-2.25L2 20l2.25-.75z"
      }));
    case 'diamond':
      return /*#__PURE__*/React.createElement("svg", {
        style: s,
        viewBox: "0 0 24 24",
        fill: "currentColor"
      }, /*#__PURE__*/React.createElement("path", {
        d: "M6 3h12l4 6-10 13L2 9z"
      }));
    default:
      return /*#__PURE__*/React.createElement("svg", {
        style: s,
        viewBox: "0 0 24 24",
        fill: "none",
        stroke: "currentColor",
        strokeWidth: "2"
      }, /*#__PURE__*/React.createElement("circle", {
        cx: "12",
        cy: "12",
        r: "10"
      }), /*#__PURE__*/React.createElement("line", {
        x1: "12",
        y1: "8",
        x2: "12",
        y2: "12"
      }), /*#__PURE__*/React.createElement("line", {
        x1: "12",
        y1: "16",
        x2: "12.01",
        y2: "16"
      }));
  }
}
function RarityBadge({
  rarity,
  size = 'md',
  glassy = false
}) {
  const cfg = RARITY_CONFIG[rarity] || RARITY_CONFIG.unknown;
  const [hover, setHover] = useState(false);
  const sizes = {
    sm: {
      padding: '4px 8px',
      fontSize: 10,
      radius: 5,
      gap: 4,
      iconSize: 9
    },
    md: {
      padding: '4px 9px',
      fontSize: 11,
      radius: 5,
      gap: 5,
      iconSize: 12
    },
    lg: {
      padding: '6px 12px',
      fontSize: 13,
      radius: 7,
      gap: 6,
      iconSize: 14
    }
  };
  const sz = sizes[size] || sizes.md;
  const style = glassy ? {
    background: 'rgba(20,17,14,0.82)',
    color: cfg.color,
    borderColor: 'rgba(255,255,255,0.12)',
    backdropFilter: 'blur(6px)'
  } : {
    background: cfg.bg,
    color: cfg.color,
    borderColor: cfg.border
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      display: 'inline-flex'
    }
  }, /*#__PURE__*/React.createElement("div", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: sz.gap,
      padding: sz.padding,
      borderRadius: sz.radius,
      fontSize: sz.fontSize,
      fontWeight: 600,
      fontFamily: "'Space Grotesk',sans-serif",
      border: '1px solid',
      cursor: 'default',
      whiteSpace: 'nowrap',
      ...style
    }
  }, /*#__PURE__*/React.createElement(RarityIcon, {
    type: cfg.icon,
    size: sz.iconSize
  }), cfg.label), hover && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 'calc(100% + 6px)',
      left: 0,
      zIndex: 999,
      background: '#1C1915',
      color: '#fff',
      borderRadius: 6,
      padding: '6px 10px',
      fontSize: 11,
      lineHeight: 1.4,
      maxWidth: 200,
      whiteSpace: 'normal',
      pointerEvents: 'none',
      boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
      fontFamily: "'DM Sans',sans-serif",
      fontWeight: 400
    }
  }, cfg.tooltip));
}

// ── Cover Placeholder ─────────────────────────────────────────
// Renders a real image when imgSrc is provided (matches the preview spec exactly);
// otherwise falls back to a gradient placeholder keyed by `scheme`.
function CoverPlaceholder({
  scheme,
  series,
  title,
  imgSrc,
  style: extraStyle = {}
}) {
  if (imgSrc) {
    return /*#__PURE__*/React.createElement("img", {
      src: imgSrc,
      alt: title || series || '',
      style: {
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        objectFit: 'cover',
        objectPosition: 'center top',
        ...extraStyle
      }
    });
  }
  const s = COVER_SCHEMES[scheme] || COVER_SCHEMES['generic-dark'];
  return /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      background: s.grad,
      ...extraStyle
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      inset: 0,
      backgroundImage: 'repeating-linear-gradient(135deg,rgba(255,255,255,0.025) 0px,rgba(255,255,255,0.025) 1px,transparent 1px,transparent 14px)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      height: 24,
      background: s.bar,
      display: 'flex',
      alignItems: 'center',
      padding: '0 8px'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 8,
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color: s.barText,
      fontFamily: "'Space Grotesk',sans-serif",
      fontWeight: 600,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, series)));
}

// ── Single Manga Card ─────────────────────────────────────────
function MangaCard({
  item,
  onClick
}) {
  const [hovered, setHovered] = useState(false);
  return /*#__PURE__*/React.createElement("div", {
    role: "button",
    tabIndex: 0,
    onClick: () => onClick(item),
    onKeyDown: e => e.key === 'Enter' && onClick(item),
    onMouseEnter: () => setHovered(true),
    onMouseLeave: () => setHovered(false),
    style: {
      width: '100%',
      borderRadius: 12,
      overflow: 'hidden',
      background: '#fff',
      border: '1px solid #E5E0D8',
      boxShadow: hovered ? '0 6px 16px rgba(0,0,0,0.10)' : '0 1px 3px rgba(0,0,0,0.06)',
      transform: hovered ? 'translateY(-3px)' : 'none',
      transition: 'transform 180ms cubic-bezier(0.22,1,0.36,1), box-shadow 180ms',
      cursor: 'pointer',
      outline: 'none',
      position: 'relative'
    },
    onFocus: e => e.currentTarget.style.outline = '2px solid #1A8A5A',
    onBlur: e => e.currentTarget.style.outline = 'none'
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: '100%',
      aspectRatio: '2/3',
      position: 'relative',
      overflow: 'hidden',
      borderRadius: '11px 11px 0 0'
    }
  }, /*#__PURE__*/React.createElement(CoverPlaceholder, {
    scheme: item.coverScheme,
    series: "",
    title: "",
    imgSrc: item.imgSrc
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 8,
      left: 8,
      zIndex: 2
    }
  }, /*#__PURE__*/React.createElement(RarityBadge, {
    rarity: item.rarity,
    size: "sm",
    glassy: true
  })), item.status && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 8,
      right: 8,
      zIndex: 2,
      padding: '3px 7px',
      borderRadius: 4,
      fontSize: 9,
      fontWeight: 700,
      fontFamily: "'Space Grotesk',sans-serif",
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
      background: item.status === 'new' ? '#D93D1A' : 'rgba(158,108,0,0.85)',
      color: item.status === 'new' ? '#fff' : '#FDE68A'
    }
  }, item.status === 'new' ? 'New' : 'Changed'), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      bottom: 0,
      left: 0,
      right: 0,
      zIndex: 3,
      background: 'rgba(28,25,21,0.88)',
      backdropFilter: 'blur(6px)',
      padding: '8px 10px',
      display: 'flex',
      gap: 6,
      opacity: hovered ? 1 : 0,
      transition: 'opacity 150ms',
      borderRadius: '0 0 11px 11px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      textAlign: 'center',
      fontSize: 11,
      fontWeight: 500,
      color: '#fff',
      padding: '5px',
      borderRadius: 4,
      background: 'rgba(255,255,255,0.12)'
    }
  }, "View details"), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      textAlign: 'center',
      fontSize: 11,
      fontWeight: 500,
      color: 'rgba(255,255,255,0.65)',
      padding: '5px',
      borderRadius: 4
    }
  }, "Source \u2197"))), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '10px 12px 12px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: '#A89E93',
      fontWeight: 500,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      marginBottom: 3,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, item.series), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      fontFamily: "'Space Grotesk',sans-serif",
      color: '#1C1915',
      lineHeight: 1.25,
      marginBottom: 6,
      display: '-webkit-box',
      WebkitLineClamp: 2,
      WebkitBoxOrient: 'vertical',
      overflow: 'hidden'
    }
  }, item.shortTitle), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: '#8C8178'
    }
  }, item.publisher, " \xB7 ", item.country), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      gap: 4,
      marginTop: 3
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "10",
    height: "10",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "#A89E93",
    strokeWidth: "2"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "10"
  }), /*#__PURE__*/React.createElement("line", {
    x1: "2",
    y1: "12",
    x2: "22",
    y2: "12"
  })), /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 10,
      color: '#A89E93'
    }
  }, item.language)), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      background: '#F5F1EB',
      color: '#706560',
      borderRadius: 3,
      padding: '2px 7px',
      fontSize: 10,
      fontWeight: 500,
      marginTop: 7
    }
  }, item.editionType)));
}

// ── Collection Card ───────────────────────────────────────────
// Stacked card layout (matches design system spec — see preview/components-collection-card.html):
// - Front (main) card is full-width of its grid cell → IDENTICAL dimensions to a single MangaCard.
//   This makes single and stacked cards align perfectly along the top.
// - Back cards are absolutely positioned with NEGATIVE right/bottom offsets so they peek
//   beyond the wrapper (to the right and below) — extending past the main card baseline.
// - Back card heights/widths equal the main card exactly (top+bottom and left+right anchors
//   span the wrapper).
// - Catalog grid uses extra row-gap so back cards have room to extend without colliding
//   with the next row.
// - Cover badges match the single card: rarity TOP-LEFT, status TOP-RIGHT.
// - Collection / Box Set tag lives in the FOOTER (not on top of cover).
function CollectionCard({
  item,
  onClick
}) {
  const [hovered, setHovered] = useState(false);
  const isBoxSet = item.editionType === 'Box Set' || item.editionType === 'Anniversary Box Set';
  const typeLabel = isBoxSet ? 'Box Set' : 'Collection';
  const unitsLabel = isBoxSet ? 'items' : 'volumes';
  return /*#__PURE__*/React.createElement("div", {
    role: "button",
    tabIndex: 0,
    onClick: () => onClick(item),
    onKeyDown: e => e.key === 'Enter' && onClick(item),
    onMouseEnter: () => setHovered(true),
    onMouseLeave: () => setHovered(false),
    style: {
      position: 'relative',
      width: '100%',
      // fills grid cell — same as MangaCard
      boxSizing: 'border-box',
      cursor: 'pointer',
      outline: 'none'
    },
    onFocus: e => e.currentTarget.style.outline = '2px solid #1A8A5A',
    onBlur: e => e.currentTarget.style.outline = 'none'
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 16,
      left: 12,
      right: -12,
      bottom: -16,
      zIndex: 1,
      borderRadius: 12,
      background: '#D6CFC0',
      border: '1px solid #BAB2A1',
      boxShadow: '0 1px 6px rgba(0,0,0,0.06)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 8,
      left: 6,
      right: -6,
      bottom: -8,
      zIndex: 2,
      borderRadius: 12,
      background: '#E2DCCE',
      border: '1px solid #C9C2B1',
      boxShadow: '0 2px 8px rgba(0,0,0,0.07)'
    }
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'relative',
      zIndex: 3,
      borderRadius: 12,
      overflow: 'hidden',
      background: '#fff',
      border: '1px solid #E5E0D8',
      boxShadow: hovered ? '0 8px 24px rgba(0,0,0,0.14), 0 2px 6px rgba(0,0,0,0.08)' : '0 4px 18px rgba(0,0,0,0.13), 0 1px 4px rgba(0,0,0,0.07)',
      transform: hovered ? 'translateY(-2px)' : 'none',
      transition: 'transform 180ms cubic-bezier(0.22,1,0.36,1), box-shadow 180ms'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      width: '100%',
      aspectRatio: '2/3',
      position: 'relative',
      overflow: 'hidden',
      borderRadius: '11px 11px 0 0'
    }
  }, /*#__PURE__*/React.createElement(CoverPlaceholder, {
    scheme: item.coverScheme,
    series: "",
    title: "",
    imgSrc: item.imgSrc
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 8,
      left: 8,
      zIndex: 2
    }
  }, /*#__PURE__*/React.createElement(RarityBadge, {
    rarity: item.rarity,
    size: "sm",
    glassy: true
  })), item.status && /*#__PURE__*/React.createElement("div", {
    style: {
      position: 'absolute',
      top: 8,
      right: 8,
      zIndex: 2,
      padding: '3px 7px',
      borderRadius: 4,
      fontSize: 9,
      fontWeight: 700,
      fontFamily: "'Space Grotesk',sans-serif",
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
      whiteSpace: 'nowrap',
      background: item.status === 'new' ? '#D93D1A' : 'rgba(158,108,0,0.85)',
      color: item.status === 'new' ? '#fff' : '#FDE68A'
    }
  }, item.status === 'new' ? 'New' : 'Changed')), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: '11px 13px 13px'
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10,
      color: '#A89E93',
      fontWeight: 500,
      letterSpacing: '0.06em',
      textTransform: 'uppercase',
      marginBottom: 3,
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap'
    }
  }, item.series), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      fontWeight: 600,
      fontFamily: "'Space Grotesk',sans-serif",
      color: '#1C1915',
      lineHeight: 1.25,
      marginBottom: 5,
      display: '-webkit-box',
      WebkitLineClamp: 2,
      WebkitBoxOrient: 'vertical',
      overflow: 'hidden'
    }
  }, item.shortTitle), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      color: '#8C8178'
    }
  }, item.publisher, " \xB7 ", item.country), /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginTop: 10,
      paddingTop: 10,
      borderTop: '1px solid #EDE9E2',
      gap: 8
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 5,
      padding: '4px 8px',
      borderRadius: 5,
      background: '#F0EDE6',
      border: '1px solid #DDD8CF',
      fontSize: 10,
      fontWeight: 600,
      fontFamily: "'Space Grotesk',sans-serif",
      color: '#3D3833',
      letterSpacing: '0.02em',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("svg", {
    width: "10",
    height: "10",
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2.4"
  }, /*#__PURE__*/React.createElement("rect", {
    x: "2",
    y: "7",
    width: "20",
    height: "14",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"
  })), typeLabel), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: '#1A8A5A',
      whiteSpace: 'nowrap'
    }
  }, /*#__PURE__*/React.createElement("strong", {
    style: {
      fontWeight: 700
    }
  }, item.volumes), " ", unitsLabel)))));
}
Object.assign(window, {
  RarityBadge,
  RarityIcon,
  MangaCard,
  CollectionCard,
  CoverPlaceholder
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/MangaCard.jsx", error: String((e && e.message) || e) }); }

// ui_kits/pandawatch/data.js
try { (() => {
// PandaWatch UI Kit — Mock Data & Utilities
// Plain JS (no JSX) — loaded before React components

const RARITY_CONFIG = {
  accessible: {
    label: 'Accessible',
    color: '#64748B',
    bg: '#F1F5F9',
    border: '#CBD5E1',
    icon: 'circle',
    score: '0–20',
    tooltip: 'Special edition, widely available. No rush.'
  },
  limited: {
    label: 'Limited',
    color: '#1A8A5A',
    bg: '#EDFAF3',
    border: '#A6DFCA',
    icon: 'star',
    score: '21–40',
    tooltip: 'Limited print run. Available with some effort.'
  },
  rare: {
    label: 'Rare',
    color: '#2D52CC',
    bg: '#EEF2FF',
    border: '#C7D2FE',
    icon: 'star2',
    score: '41–65',
    tooltip: 'Hard to find. Secondary market usually required.'
  },
  'very-rare': {
    label: 'Super Rare',
    color: '#7C3AED',
    bg: '#F5F3FF',
    border: '#DDD6FE',
    icon: 'sparkle',
    score: '66–85',
    tooltip: 'Very low availability. Regional or short print window.'
  },
  'ultra-rare': {
    label: 'Ultra Rare',
    color: '#9E6C00',
    bg: '#FFFBEB',
    border: '#FDE68A',
    icon: 'diamond',
    score: '86–100',
    tooltip: 'Extremely scarce. Event exclusives, lotteries, micro-prints.'
  },
  unknown: {
    label: 'Unknown',
    color: '#9CA3AF',
    bg: '#F9FAFB',
    border: '#E5E7EB',
    icon: 'help',
    score: 'null',
    tooltip: 'Insufficient data to estimate rarity.'
  }
};
function scoreToRarity(score) {
  if (score == null) return 'unknown';
  if (score <= 20) return 'accessible';
  if (score <= 40) return 'limited';
  if (score <= 65) return 'rare';
  if (score <= 85) return 'very-rare';
  return 'ultra-rare';
}
const COVER_SCHEMES = {
  'pn-fanbook': {
    grad: 'linear-gradient(160deg,#0f0c29 0%,#302b63 55%,#24243e 100%)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(180,170,255,0.9)'
  },
  'berserk': {
    grad: 'linear-gradient(160deg,#0a0000 0%,#2a0800 40%,#5c1200 80%,#8b1a00 100%)',
    bar: 'rgba(0,0,0,0.6)',
    barText: 'rgba(212,180,50,0.95)'
  },
  'berserk-2': {
    grad: 'linear-gradient(160deg,#1a0800,#3d1200)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(180,120,50,0.85)'
  },
  'berserk-3': {
    grad: 'linear-gradient(160deg,#2d0a00,#5c1500)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(180,120,50,0.7)'
  },
  'op-100': {
    grad: 'linear-gradient(160deg,#1e3a8a 0%,#1e40af 40%,#ea580c 80%,#f97316 100%)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(255,220,150,0.95)'
  },
  'csm-boxset': {
    grad: 'linear-gradient(160deg,#1a0000 0%,#5c0000 50%,#991b1b 100%)',
    bar: 'rgba(0,0,0,0.55)',
    barText: 'rgba(252,165,165,0.9)'
  },
  'csm-2': {
    grad: 'linear-gradient(160deg,#3d0000,#7f1d1d)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(252,165,165,0.75)'
  },
  'csm-3': {
    grad: 'linear-gradient(160deg,#5c0000,#8b1a1a)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(252,165,165,0.65)'
  },
  'akira': {
    grad: 'linear-gradient(160deg,#0a0a0a 0%,#1a0000 40%,#7f1d1d 100%)',
    bar: 'rgba(0,0,0,0.6)',
    barText: 'rgba(239,68,68,0.9)'
  },
  'naruto': {
    grad: 'linear-gradient(135deg,#7c2d12 0%,#ea580c 45%,#f97316 100%)',
    bar: 'rgba(0,0,0,0.45)',
    barText: 'rgba(255,240,200,0.95)'
  },
  'generic-dark': {
    grad: 'linear-gradient(160deg,#1c1915,#3b3632)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(200,190,180,0.9)'
  },
  'generic-blue': {
    grad: 'linear-gradient(160deg,#0c1a3d,#1e3a8a,#1e40af)',
    bar: 'rgba(0,0,0,0.5)',
    barText: 'rgba(180,200,255,0.9)'
  }
};
const MANGA_ITEMS = [
// ── Bakuman items ── use the real cover image (assets/bakuman-cover.png) — match the
//    examples shown in preview/components-manga-card.html and components-collection-card.html.
{
  id: 'bakuman-anniversary-de',
  type: 'single',
  title: 'Bakuman 20th Anniversary Edition',
  shortTitle: '20th Anniversary Edition',
  series: 'Bakuman',
  editionType: 'Anniversary',
  productType: 'anniversary',
  publisher: 'Tokyopop',
  country: 'Germany',
  language: 'German',
  score: 55,
  status: null,
  isbn: '9783842089136',
  price: '€19.00',
  publishedAt: '2023-04-12',
  detectedAt: '2026-05-21',
  signals: ['anniversary', 'hardcover'],
  signalTypes: ['anniversary'],
  source: 'Publisher Direct',
  sourceClass: 'publisher',
  sourceUrl: 'https://www.tokyopop.de/',
  coverScheme: 'generic-dark',
  imgSrc: '../../assets/bakuman-cover.png',
  description: 'Tokyopop\'s 20th anniversary edition of Bakuman for the German market.',
  tags: ['anniversary', 'germany', 'german', 'tokyopop']
}, {
  id: 'bakuman-deluxe-jp',
  type: 'collection',
  title: 'Bakuman Deluxe Collector\'s Edition',
  shortTitle: 'Deluxe Collector\'s Edition',
  series: 'Bakuman',
  editionType: 'Deluxe',
  productType: 'deluxe',
  publisher: 'Shueisha',
  country: 'Japan',
  language: 'Japanese',
  score: 35,
  status: 'new',
  isbn: null,
  price: '¥3,200 / vol',
  publishedAt: '2024-12-04',
  detectedAt: '2026-05-22',
  signals: ['deluxe', 'hardcover', 'limited'],
  signalTypes: ['deluxe', 'limited'],
  source: 'Publisher Direct',
  sourceClass: 'publisher',
  sourceUrl: 'https://www.shueisha.co.jp/',
  coverScheme: 'generic-dark',
  imgSrc: '../../assets/bakuman-cover.png',
  volumes: 11,
  volumeCovers: ['generic-dark', 'generic-dark', 'generic-dark'],
  description: 'Shueisha\'s deluxe collector\'s edition of Bakuman, hardcover with bonus material.',
  tags: ['deluxe', 'box-set', 'japan', 'japanese', 'shueisha']
}, {
  id: 'bakuman-fanbook',
  type: 'single',
  title: 'Bakuman Exhibition Fanbook — Ohba & Obata',
  shortTitle: 'Exhibition Fanbook — Ohba & Obata',
  series: 'Bakuman',
  editionType: 'Fanbook',
  productType: 'fanbook',
  publisher: 'Shueisha',
  country: 'Japan',
  language: 'Japanese',
  score: 75,
  status: 'changed',
  isbn: '9784088808451',
  price: '¥2,800',
  publishedAt: '2018-10-20',
  detectedAt: '2026-05-12',
  signals: ['fanbook', 'exhibition', 'limited'],
  signalTypes: ['fanbook', 'exhibition'],
  source: 'Manga Sanctuary',
  sourceClass: 'trusted_media',
  sourceUrl: 'https://www.manga-sanctuary.com/',
  coverScheme: 'generic-dark',
  imgSrc: '../../assets/bakuman-cover.png',
  description: 'Limited fanbook produced for the Ohba & Obata exhibition.',
  tags: ['fanbook', 'exhibition', 'japan', 'japanese', 'shueisha']
}, {
  id: 'pn-fanbook',
  type: 'single',
  title: 'The Promised Neverland Mystic Code Fanbook',
  shortTitle: 'Mystic Code Fanbook',
  series: 'The Promised Neverland',
  editionType: 'Fanbook',
  productType: 'fanbook',
  publisher: 'kazé manga',
  country: 'France',
  language: 'French',
  score: 30,
  status: 'changed',
  isbn: '9782820342706',
  price: '€9.99',
  publishedAt: '2021-10-27',
  detectedAt: '2026-05-19',
  signals: ['fanbook'],
  signalTypes: ['fanbook'],
  source: 'Manga Sanctuary',
  sourceClass: 'trusted_media',
  sourceUrl: 'https://www.manga-sanctuary.com/',
  coverScheme: 'pn-fanbook',
  description: 'kazé manga · simple · Fanbook · The Promised Neverland - Mystic Code',
  tags: ['wiki', 'manga-sanctuary', 'manga', 'france', 'type:fanbook', 'edition:simple']
}, {
  id: 'berserk-deluxe',
  type: 'collection',
  title: 'Berserk Deluxe Edition',
  shortTitle: 'Deluxe Edition',
  series: 'Berserk',
  editionType: 'Deluxe',
  productType: 'deluxe',
  publisher: 'Dark Horse Comics',
  country: 'USA',
  language: 'English',
  score: 55,
  status: null,
  isbn: null,
  price: '$49.99 / vol',
  publishedAt: '2019-04-09',
  detectedAt: '2026-05-15',
  signals: ['deluxe', 'hardcover', 'oversized'],
  signalTypes: ['deluxe', 'hardcover'],
  source: 'Publisher Direct',
  sourceClass: 'publisher',
  sourceUrl: 'https://www.darkhorse.com/',
  coverScheme: 'berserk',
  volumes: 14,
  volumeCovers: ['berserk', 'berserk-2', 'berserk-3'],
  description: 'Oversized hardcover deluxe editions collecting Berserk in premium format with full-color pages and improved binding.',
  tags: ['deluxe', 'hardcover', 'oversized', 'usa', 'english', 'dark-horse']
}, {
  id: 'op-100-variant',
  type: 'single',
  title: 'One Piece Vol. 100 Celebration Variant Cover',
  shortTitle: 'Vol. 100 Celebration Variant',
  series: 'One Piece',
  editionType: 'Variant Cover',
  productType: 'variant-cover',
  publisher: 'Shueisha',
  country: 'Japan',
  language: 'Japanese',
  score: 92,
  status: 'new',
  isbn: '9784088828442',
  price: '¥528',
  publishedAt: '2021-09-03',
  detectedAt: '2026-05-20',
  signals: ['variant-cover', 'celebration', 'limited-print'],
  signalTypes: ['variant-cover', 'limited-print'],
  source: 'Publisher Direct',
  sourceClass: 'publisher',
  sourceUrl: 'https://www.shueisha.co.jp/',
  coverScheme: 'op-100',
  description: 'Special variant cover edition celebrating the 100th volume milestone of One Piece, featuring exclusive artwork.',
  tags: ['variant-cover', 'celebration', 'limited', 'japan', 'japanese', 'shueisha']
}, {
  id: 'csm-boxset',
  type: 'collection',
  title: 'Chainsaw Man Box Set Vol. 1–11',
  shortTitle: 'Box Set Vol. 1–11',
  series: 'Chainsaw Man',
  editionType: 'Box Set',
  productType: 'box-set',
  publisher: 'Norma Editorial',
  country: 'Spain',
  language: 'Spanish',
  score: 35,
  status: 'new',
  isbn: null,
  price: '€89.99',
  publishedAt: '2023-11-15',
  detectedAt: '2026-05-18',
  signals: ['box-set'],
  signalTypes: ['box-set'],
  source: 'Manga Sanctuary',
  sourceClass: 'trusted_media',
  sourceUrl: 'https://www.manga-sanctuary.com/',
  coverScheme: 'csm-boxset',
  volumes: 11,
  volumeCovers: ['csm-boxset', 'csm-2', 'csm-3'],
  description: 'Complete box set of Chainsaw Man volumes 1 through 11 by Norma Editorial for the Spanish market.',
  tags: ['box-set', 'spain', 'spanish', 'norma-editorial']
}, {
  id: 'akira-35th',
  type: 'collection',
  title: 'Akira 35th Anniversary Box Set',
  shortTitle: '35th Anniversary Box Set',
  series: 'Akira',
  editionType: 'Anniversary Box Set',
  productType: 'box-set',
  publisher: 'Kodansha Comics',
  country: 'Japan',
  language: 'Japanese',
  score: 78,
  status: 'changed',
  isbn: null,
  price: '¥38,500',
  publishedAt: '2018-11-13',
  detectedAt: '2026-05-10',
  signals: ['box-set', 'anniversary', 'limited', 'special-cover'],
  signalTypes: ['box-set', 'anniversary', 'limited'],
  source: 'Publisher Direct',
  sourceClass: 'publisher',
  sourceUrl: 'https://www.kodansha.us/',
  coverScheme: 'akira',
  volumes: 6,
  volumeCovers: ['akira', 'generic-dark', 'generic-dark'],
  description: 'Limited 35th anniversary box set of Akira by Kodansha, featuring 6 volumes in a premium collector\'s box with exclusive artwork.',
  tags: ['box-set', 'anniversary', 'limited', 'japan', 'japanese', 'kodansha']
}, {
  id: 'naruto-exhibition',
  type: 'single',
  title: 'Naruto Exhibition Official Fanbook',
  shortTitle: 'Exhibition Official Fanbook',
  series: 'Naruto',
  editionType: 'Fanbook',
  productType: 'fanbook',
  publisher: 'Shueisha',
  country: 'Japan',
  language: 'Japanese',
  score: 58,
  status: null,
  isbn: '9784088806983',
  price: '¥1,650',
  publishedAt: '2015-07-01',
  detectedAt: '2026-05-05',
  signals: ['fanbook', 'exhibition'],
  signalTypes: ['fanbook', 'exhibition'],
  source: 'Publisher Direct',
  sourceClass: 'publisher',
  sourceUrl: 'https://www.shueisha.co.jp/',
  coverScheme: 'naruto',
  description: 'Official fanbook produced for the Naruto exhibition, featuring exclusive artwork, interviews, and behind-the-scenes content.',
  tags: ['fanbook', 'exhibition', 'japan', 'japanese', 'shueisha']
}];

// Derive rarity for each item
MANGA_ITEMS.forEach(item => {
  item.rarity = scoreToRarity(item.score);
  item.rarityConfig = RARITY_CONFIG[item.rarity];
});
const FILTER_OPTIONS = {
  rarity: ['accessible', 'limited', 'rare', 'very-rare', 'ultra-rare', 'unknown'],
  editionType: ['Fanbook', 'Box Set', 'Deluxe', 'Variant Cover', 'Anniversary', 'Anniversary Box Set', 'Limited Edition', 'Premium', 'Collector\'s Edition'],
  country: ['Japan', 'France', 'USA', 'Spain', 'Germany', 'Italy', 'UK'],
  language: ['Japanese', 'French', 'English', 'Spanish', 'German', 'Italian'],
  publisher: ['Shueisha', 'kazé manga', 'Dark Horse Comics', 'Norma Editorial', 'Kodansha Comics', 'Tokyopop'],
  sourceClass: ['trusted_media', 'publisher', 'marketplace'],
  status: ['new', 'changed']
};
const SORT_OPTIONS = [{
  value: 'most-rare',
  label: 'Most Rare'
}, {
  value: 'recently-detected',
  label: 'Recently Detected'
}, {
  value: 'newest-release',
  label: 'Newest Release'
}, {
  value: 'a-z',
  label: 'A–Z'
}, {
  value: 'publisher',
  label: 'Publisher'
}];
function sortItems(items, sortBy) {
  const sorted = [...items];
  switch (sortBy) {
    case 'most-rare':
      return sorted.sort((a, b) => (b.score || 0) - (a.score || 0));
    case 'recently-detected':
      return sorted.sort((a, b) => b.detectedAt.localeCompare(a.detectedAt));
    case 'newest-release':
      return sorted.sort((a, b) => b.publishedAt.localeCompare(a.publishedAt));
    case 'a-z':
      return sorted.sort((a, b) => a.title.localeCompare(b.title));
    case 'publisher':
      return sorted.sort((a, b) => a.publisher.localeCompare(b.publisher));
    default:
      return sorted;
  }
}
function filterItems(items, filters, query) {
  return items.filter(item => {
    if (query) {
      const q = query.toLowerCase();
      if (![item.title, item.series, item.publisher, item.isbn || '', item.country].some(f => f && f.toLowerCase().includes(q))) return false;
    }
    if (filters.rarity?.length && !filters.rarity.includes(item.rarity)) return false;
    if (filters.editionType?.length && !filters.editionType.includes(item.editionType)) return false;
    if (filters.country?.length && !filters.country.includes(item.country)) return false;
    if (filters.language?.length && !filters.language.includes(item.language)) return false;
    if (filters.publisher?.length && !filters.publisher.includes(item.publisher)) return false;
    if (filters.status?.length && !filters.status.includes(item.status)) return false;
    return true;
  });
}

// Export to window for cross-file access
Object.assign(window, {
  RARITY_CONFIG,
  MANGA_ITEMS,
  FILTER_OPTIONS,
  SORT_OPTIONS,
  scoreToRarity,
  sortItems,
  filterItems,
  COVER_SCHEMES
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/pandawatch/data.js", error: String((e && e.message) || e) }); }

})();
