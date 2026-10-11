// PandaWatch UI Kit — Filter Sidebar + Mobile Bottom Sheet
const { useState } = React;

const RARITY_LABELS = {
  'accessible': 'Accessible', 'limited': 'Limited', 'rare': 'Rare',
  'very-rare': 'Super Rare', 'ultra-rare': 'Ultra Rare', 'unknown': 'Unknown'
};

function FilterGroup({ title, options, selected, onToggle, counts = {} }) {
  const [expanded, setExpanded] = useState(true);
  return (
    <div style={{ marginBottom: 16 }}>
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display:'flex', alignItems:'center', justifyContent:'space-between',
          marginBottom: expanded ? 8 : 0, cursor:'pointer',
        }}
      >
        <div style={{ fontSize:12, fontWeight:600, color:'#1C1915', fontFamily:"'Space Grotesk',sans-serif" }}>
          {title}
          {selected.length > 0 && (
            <span style={{ marginLeft:6, background:'#1A8A5A', color:'#fff',
              borderRadius:999, fontSize:9, fontWeight:700,
              padding:'1px 5px', verticalAlign:'middle' }}>
              {selected.length}
            </span>
          )}
        </div>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#A89E93" strokeWidth="2"
          style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition:'transform 150ms' }}>
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      {expanded && (
        <div style={{ display:'flex', flexDirection:'column', gap:2 }}>
          {options.map(opt => {
            const isChecked = selected.includes(opt);
            const label = RARITY_LABELS[opt] || opt;
            const count = counts[opt] || 0;
            return (
              <div
                key={opt}
                onClick={() => onToggle(opt)}
                style={{
                  display:'flex', alignItems:'center', gap:8,
                  padding:'5px 4px', borderRadius:5, cursor:'pointer',
                  background: isChecked ? '#EDFAF3' : 'transparent',
                  transition:'background 100ms',
                }}
              >
                <div style={{
                  width:15, height:15, borderRadius:3, flexShrink:0,
                  border: `1.5px solid ${isChecked ? '#1A8A5A' : '#DDD8CF'}`,
                  background: isChecked ? '#1A8A5A' : '#fff',
                  display:'flex', alignItems:'center', justifyContent:'center',
                  transition:'all 120ms',
                }}>
                  {isChecked && (
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                      <polyline points="20 6 9 17 4 12"/>
                    </svg>
                  )}
                </div>
                <span style={{ fontSize:12, color: isChecked ? '#1A8A5A' : '#554D49', flex:1, fontWeight: isChecked ? 500 : 400 }}>
                  {label}
                </span>
                {count > 0 && <span style={{ fontSize:10, color:'#A89E93' }}>{count}</span>}
              </div>
            );
          })}
        </div>
      )}
      <div style={{ height:1, background:'#EDE9E2', marginTop:14 }}/>
    </div>
  );
}

function FilterSidebar({ filters, onFiltersChange, items, onClear }) {
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
    onFiltersChange({ ...filters, [key]: next });
  }

  const totalActive = Object.values(filters).reduce((s, a) => s + (a?.length || 0), 0);

  return (
    <div style={{
      width:272, flexShrink:0,
      background:'#fff', borderRadius:10,
      border:'1px solid #E5E0D8',
      boxShadow:'0 1px 3px rgba(0,0,0,0.04)',
      padding:'16px 16px 8px',
      alignSelf:'flex-start',
      position:'sticky', top:76,
      maxHeight:'calc(100vh - 96px)', overflowY:'auto',
    }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16 }}>
        <div style={{ fontSize:14, fontWeight:600, color:'#1C1915', fontFamily:"'Space Grotesk',sans-serif" }}>
          Filters
        </div>
        {totalActive > 0 && (
          <span
            onClick={onClear}
            style={{ fontSize:11, color:'#D93D1A', cursor:'pointer', fontWeight:500 }}
          >Clear all</span>
        )}
      </div>

      <FilterGroup
        title="Rarity"
        options={FILTER_OPTIONS.rarity}
        selected={filters.rarity || []}
        onToggle={v => toggle('rarity', v)}
        counts={getCounts('rarity')}
      />
      <FilterGroup
        title="Edition Type"
        options={FILTER_OPTIONS.editionType}
        selected={filters.editionType || []}
        onToggle={v => toggle('editionType', v)}
        counts={getCounts('editionType')}
      />
      <FilterGroup
        title="Country"
        options={FILTER_OPTIONS.country}
        selected={filters.country || []}
        onToggle={v => toggle('country', v)}
        counts={getCounts('country')}
      />
      <FilterGroup
        title="Language"
        options={FILTER_OPTIONS.language}
        selected={filters.language || []}
        onToggle={v => toggle('language', v)}
        counts={getCounts('language')}
      />
      <FilterGroup
        title="Publisher"
        options={FILTER_OPTIONS.publisher}
        selected={filters.publisher || []}
        onToggle={v => toggle('publisher', v)}
        counts={getCounts('publisher')}
      />
      <FilterGroup
        title="Status"
        options={FILTER_OPTIONS.status}
        selected={filters.status || []}
        onToggle={v => toggle('status', v)}
        counts={getCounts('status')}
      />
    </div>
  );
}

// ── Mobile Bottom Sheet ───────────────────────────────────────
function MobileFilterSheet({ filters, onFiltersChange, items, onClear, onClose, resultCount }) {
  const [activeTab, setActiveTab] = useState('rarity');
  const tabs = [
    { key:'rarity', label:'Rarity' },
    { key:'editionType', label:'Type' },
    { key:'country', label:'Country' },
    { key:'publisher', label:'Publisher' },
  ];

  function toggle(key, value) {
    const cur = filters[key] || [];
    const next = cur.includes(value) ? cur.filter(v => v !== value) : [...cur, value];
    onFiltersChange({ ...filters, [key]: next });
  }

  const totalActive = Object.values(filters).reduce((s, a) => s + (a?.length || 0), 0);
  const activeOptions = FILTER_OPTIONS[activeTab] || [];

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:200,
      background:'rgba(28,25,21,0.4)', backdropFilter:'blur(3px)',
      display:'flex', flexDirection:'column', justifyContent:'flex-end',
    }} onClick={onClose}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background:'#fff', borderRadius:'16px 16px 0 0',
          padding:'0 0 24px',
          boxShadow:'0 -12px 40px rgba(0,0,0,0.15)',
          maxHeight:'80vh', display:'flex', flexDirection:'column',
        }}
      >
        <div style={{ display:'flex', justifyContent:'center', padding:'10px 0 0' }}>
          <div style={{ width:36, height:4, background:'#DDD8CF', borderRadius:2 }}/>
        </div>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'12px 18px 0' }}>
          <div style={{ fontSize:15, fontWeight:600, color:'#1C1915', fontFamily:"'Space Grotesk',sans-serif" }}>Filters</div>
          {totalActive > 0 && <span onClick={onClear} style={{ fontSize:12, color:'#D93D1A', cursor:'pointer', fontWeight:500 }}>Clear all</span>}
        </div>
        <div style={{ display:'flex', gap:6, padding:'12px 18px 0', overflowX:'auto' }}>
          {tabs.map(tab => {
            const count = (filters[tab.key] || []).length;
            return (
              <div
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                style={{
                  padding:'5px 14px', borderRadius:999, fontSize:12, fontWeight:500,
                  border:`1.5px solid ${activeTab === tab.key ? '#1A8A5A' : '#DDD8CF'}`,
                  background: activeTab === tab.key ? '#EDFAF3' : '#fff',
                  color: activeTab === tab.key ? '#1A8A5A' : '#706560',
                  cursor:'pointer', flexShrink:0, whiteSpace:'nowrap',
                }}
              >
                {tab.label}{count > 0 ? ` (${count})` : ''}
              </div>
            );
          })}
        </div>
        <div style={{ flex:1, overflowY:'auto', padding:'14px 18px 0', borderTop:'1px solid #EDE9E2', marginTop:12 }}>
          <div style={{ display:'flex', flexWrap:'wrap', gap:8 }}>
            {activeOptions.map(opt => {
              const label = RARITY_LABELS[opt] || opt;
              const isSelected = (filters[activeTab] || []).includes(opt);
              return (
                <div
                  key={opt}
                  onClick={() => toggle(activeTab, opt)}
                  style={{
                    padding:'6px 14px', borderRadius:999, fontSize:12, fontWeight:500,
                    border:`1.5px solid ${isSelected ? '#1A8A5A' : '#DDD8CF'}`,
                    background: isSelected ? '#EDFAF3' : '#fff',
                    color: isSelected ? '#1A8A5A' : '#706560',
                    cursor:'pointer',
                  }}
                >{label}</div>
              );
            })}
          </div>
        </div>
        <div style={{ padding:'16px 18px 0' }}>
          <div
            onClick={onClose}
            style={{
              background:'#1A8A5A', color:'#fff', borderRadius:8,
              padding:'12px', textAlign:'center', cursor:'pointer',
              fontSize:14, fontWeight:600, fontFamily:"'Space Grotesk',sans-serif",
            }}
          >
            Show {resultCount} result{resultCount !== 1 ? 's' : ''}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { FilterSidebar, MobileFilterSheet });
