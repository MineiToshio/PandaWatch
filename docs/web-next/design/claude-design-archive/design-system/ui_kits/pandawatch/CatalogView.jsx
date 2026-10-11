// PandaWatch UI Kit — Catalog View (Home)
const { useState, useMemo, useEffect } = React;

const STATS = [
  { value:'2,481', label:'editions tracked' },
  { value:'37', label:'countries' },
  { value:'126', label:'publishers' },
  { value:'Daily', label:'updates' },
];

function AppliedFilters({ filters, onRemove, onClear }) {
  const chips = [];
  Object.entries(filters).forEach(([key, values]) => {
    (values || []).forEach(val => chips.push({ key, val }));
  });
  if (!chips.length) return null;
  const keyLabels = { rarity:'Rarity', editionType:'Type', country:'Country', language:'Lang', publisher:'Publisher', status:'Status' };
  const rarityLabels = { 'accessible':'Accessible','limited':'Limited','rare':'Rare','very-rare':'Super Rare','ultra-rare':'Ultra Rare','unknown':'Unknown' };

  return (
    <div style={{ display:'flex', alignItems:'center', gap:6, flexWrap:'wrap', marginBottom:12 }}>
      {chips.map(({ key, val }) => {
        const label = rarityLabels[val] || val;
        const cfg = key === 'rarity' ? RARITY_CONFIG[val] : null;
        return (
          <div key={`${key}-${val}`} style={{
            display:'inline-flex', alignItems:'center', gap:5,
            padding:'4px 8px', borderRadius:6, fontSize:12, fontWeight:500,
            background: cfg ? cfg.bg : '#1C1915',
            color: cfg ? cfg.color : '#fff',
            border:`1px solid ${cfg ? cfg.border : 'transparent'}`,
            fontFamily:"'DM Sans',sans-serif",
          }}>
            {label}
            <div
              onClick={() => onRemove(key, val)}
              style={{
                width:14, height:14, borderRadius:3, cursor:'pointer',
                display:'flex', alignItems:'center', justifyContent:'center',
                background: cfg ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.18)',
              }}
            >
              <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </div>
          </div>
        );
      })}
      <div
        onClick={onClear}
        style={{
          display:'inline-flex', alignItems:'center', gap:5,
          padding:'4px 10px', borderRadius:6, fontSize:12,
          border:'1px solid #DDD8CF', color:'#8C8178', cursor:'pointer',
          background:'transparent',
        }}
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        Clear all
      </div>
    </div>
  );
}

function SortBar({ sort, onSort, count, viewMode, onViewMode, isMobile, onOpenFilters, filterCount }) {
  const [open, setOpen] = useState(false);
  const current = SORT_OPTIONS.find(o => o.value === sort) || SORT_OPTIONS[0];
  return (
    <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:14, flexWrap:'wrap' }}>
      {isMobile && (
        <button
          onClick={onOpenFilters}
          style={{
            display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
            borderRadius:7, border:`1.5px solid ${filterCount > 0 ? '#1A8A5A' : '#DDD8CF'}`,
            background: filterCount > 0 ? '#EDFAF3' : '#fff',
            color: filterCount > 0 ? '#1A8A5A' : '#554D49',
            fontSize:13, fontWeight:500, cursor:'pointer',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="4" y1="6" x2="20" y2="6"/><line x1="8" y1="12" x2="16" y2="12"/><line x1="11" y1="18" x2="13" y2="18"/>
          </svg>
          Filters{filterCount > 0 ? ` (${filterCount})` : ''}
        </button>
      )}
      <span style={{ fontSize:13, color:'#8C8178', whiteSpace:'nowrap' }}>Sort by</span>
      <div style={{ position:'relative' }}>
        <div
          onClick={() => setOpen(!open)}
          style={{
            display:'flex', alignItems:'center', gap:6, padding:'6px 12px',
            borderRadius:7, border:'1.5px solid #DDD8CF', background:'#fff',
            fontSize:13, fontWeight:500, color:'#554D49', cursor:'pointer',
          }}
        >
          {current.label}
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#A89E93" strokeWidth="2">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </div>
        {open && (
          <div style={{
            position:'absolute', top:'calc(100% + 4px)', left:0, zIndex:50,
            background:'#fff', border:'1px solid #DDD8CF', borderRadius:8,
            boxShadow:'0 4px 12px rgba(0,0,0,0.08)', minWidth:180,
            overflow:'hidden',
          }}>
            {SORT_OPTIONS.map(opt => (
              <div
                key={opt.value}
                onClick={() => { onSort(opt.value); setOpen(false); }}
                style={{
                  padding:'9px 14px', fontSize:13, cursor:'pointer',
                  color: opt.value === sort ? '#1A8A5A' : '#554D49',
                  fontWeight: opt.value === sort ? 500 : 400,
                  background: opt.value === sort ? '#EDFAF3' : 'transparent',
                }}
              >{opt.label}</div>
            ))}
          </div>
        )}
      </div>

      {!isMobile && (
        <div style={{ display:'flex', gap:4, marginLeft:4 }}>
          {['grid','list'].map(mode => (
            <div
              key={mode}
              onClick={() => onViewMode(mode)}
              style={{
                width:32, height:32, borderRadius:6, display:'flex',
                alignItems:'center', justifyContent:'center', cursor:'pointer',
                border:`1.5px solid ${viewMode === mode ? '#1A8A5A' : '#DDD8CF'}`,
                color: viewMode === mode ? '#1A8A5A' : '#A89E93',
                background: viewMode === mode ? '#EDFAF3' : '#fff',
              }}
            >
              {mode === 'grid'
                ? <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
                : <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
              }
            </div>
          ))}
        </div>
      )}
      <div style={{ marginLeft:'auto', fontSize:12, color:'#8C8178', whiteSpace:'nowrap' }}>
        {count} edition{count !== 1 ? 's' : ''} found
      </div>
    </div>
  );
}

function EmptyState({ onClear }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center',
      padding:'64px 24px', textAlign:'center', color:'#8C8178' }}>
      <div style={{ width:56, height:56, borderRadius:14, background:'#F5F1EB',
        display:'flex', alignItems:'center', justifyContent:'center', marginBottom:16 }}>
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#A89E93" strokeWidth="1.5">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
      </div>
      <div style={{ fontSize:16, fontWeight:600, color:'#1C1915', fontFamily:"'Space Grotesk',sans-serif", marginBottom:6 }}>
        No editions found
      </div>
      <div style={{ fontSize:13, lineHeight:1.6, maxWidth:280, marginBottom:20 }}>
        Your current filters returned no results. Try broadening your search or clearing some filters.
      </div>
      <div onClick={onClear} style={{
        display:'inline-flex', alignItems:'center', gap:6, padding:'8px 18px',
        background:'#1A8A5A', color:'#fff', borderRadius:8, cursor:'pointer',
        fontSize:13, fontWeight:500,
      }}>
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
          <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
        </svg>
        Clear all filters
      </div>
    </div>
  );
}

function CatalogView({ onSelectItem, onSelectCollection, isMobile, externalQuery, onFilterCountChange }) {
  const [filters, setFilters] = useState({});
  const [sort, setSort] = useState('most-rare');
  const [viewMode, setViewMode] = useState('grid');
  const [showFilters, setShowFilters] = useState(!isMobile);
  const [showMobileSheet, setShowMobileSheet] = useState(false);

  const query = externalQuery || '';

  const filterCount = Object.values(filters).reduce((s, a) => s + (a?.length || 0), 0);
  useEffect(() => { onFilterCountChange && onFilterCountChange(filterCount); }, [filterCount]);

  const filtered = useMemo(() => filterItems(MANGA_ITEMS, filters, query), [filters, query]);
  const sorted = useMemo(() => sortItems(filtered, sort), [filtered, sort]);
  function removeFilter(key, val) {
    setFilters(f => ({ ...f, [key]: (f[key] || []).filter(v => v !== val) }));
  }
  function clearAll() { setFilters({}); }

  const cols = isMobile ? 2 : (showFilters ? 4 : 5);

  return (
    <div>
      {/* Hero */}
      <div style={{ background:'linear-gradient(to bottom, #fff 0%, #F5F1EB 100%)', borderBottom:'1px solid #E5E0D8', padding: isMobile ? '24px 16px' : '32px 32px 28px' }}>
        <div style={{ maxWidth:700 }}>
          <h1 style={{ fontFamily:"'Space Grotesk',sans-serif", fontSize: isMobile ? 22 : 28, fontWeight:700, color:'#1C1915', letterSpacing:'-0.02em', marginBottom:6, lineHeight:1.2 }}>
            Find special manga editions<br/>before they disappear
          </h1>
          <p style={{ fontSize:13, color:'#8C8178', lineHeight:1.6, marginBottom:16 }}>
            Fanbooks, deluxe prints, box sets, variant covers — all tracked across {STATS[1].value} countries.
          </p>
          <div style={{ display:'flex', gap: isMobile ? 16 : 28, flexWrap:'wrap' }}>
            {STATS.map(s => (
              <div key={s.label}>
                <div style={{ fontSize: isMobile ? 16 : 18, fontWeight:700, fontFamily:"'Space Grotesk',sans-serif", color:'#1A8A5A' }}>{s.value}</div>
                <div style={{ fontSize:11, color:'#A89E93', marginTop:1 }}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Main content */}
      <div style={{ display:'flex', gap:20, padding: isMobile ? '16px 12px' : '20px 24px', maxWidth:1440, margin:'0 auto' }}>
        {/* Sidebar */}
        {!isMobile && showFilters && (
          <FilterSidebar
            filters={filters}
            onFiltersChange={setFilters}
            items={MANGA_ITEMS}
            onClear={clearAll}
          />
        )}

        {/* Mobile sheet */}
        {isMobile && showMobileSheet && (
          <MobileFilterSheet
            filters={filters}
            onFiltersChange={setFilters}
            items={MANGA_ITEMS}
            onClear={clearAll}
            onClose={() => setShowMobileSheet(false)}
            resultCount={sorted.length}
          />
        )}

        {/* Grid area */}
        <div style={{ flex:1, minWidth:0 }}>
          <SortBar
            sort={sort} onSort={setSort}
            count={sorted.length}
            viewMode={viewMode} onViewMode={setViewMode}
            isMobile={isMobile}
            onOpenFilters={() => setShowMobileSheet(true)}
            filterCount={filterCount}
          />
          <AppliedFilters filters={filters} onRemove={removeFilter} onClear={clearAll} />

          {sorted.length === 0
            ? <EmptyState onClear={clearAll} />
            : (
              <div style={{
                display:'grid',
                gridTemplateColumns: `repeat(${cols}, 1fr)`,
                columnGap: isMobile ? 10 : 16,
                rowGap: isMobile ? 24 : 36,   // extra row gap so stacked cards' back-peek (extends 16px below) doesn't crash into the next row
                alignItems:'start',
              }}>
                {sorted.map(item => (
                  item.type === 'collection'
                    ? <CollectionCard key={item.id} item={item} onClick={onSelectCollection} />
                    : <MangaCard key={item.id} item={item} onClick={onSelectItem} />
                ))}
              </div>
            )
          }
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CatalogView });
