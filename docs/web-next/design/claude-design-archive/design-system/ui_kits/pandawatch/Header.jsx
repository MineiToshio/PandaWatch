// PandaWatch UI Kit — Header + Search Component
const { useState, useRef, useEffect } = React;

const PandaLogo = () => (
  <img
    src="../../assets/panda-mark.png"
    width="32" height="32"
    alt="PandaWatch"
    style={{ flexShrink:0, display:'block', objectFit:'contain' }}
  />
);

const headerStyles = {
  header: {
    position:'sticky', top:0, zIndex:100,
    background:'#fff', borderBottom:'1px solid #E5E0D8',
    boxShadow:'0 1px 3px rgba(0,0,0,0.04)',
    display:'flex', alignItems:'center', gap:16,
    padding:'0 24px', height:60,
  },
  logo: {
    display:'flex', alignItems:'center', gap:8,
    textDecoration:'none', flexShrink:0, cursor:'pointer',
  },
  wordmark: {
    fontFamily:"'Space Grotesk',sans-serif",
    fontSize:17, letterSpacing:'-0.02em',
  },
  searchWrap: {
    flex:1, display:'flex', alignItems:'center', gap:10,
    background:'#F5F1EB', border:'1.5px solid #DDD8CF',
    borderRadius:8, padding:'0 14px', height:38,
    transition:'border-color 150ms, box-shadow 150ms, background 150ms',
  },
  searchWrapFocused: {
    borderColor:'#1A8A5A',
    boxShadow:'0 0 0 3px rgba(26,138,90,0.12)',
    background:'#fff',
  },
  searchInput: {
    flex:1, border:'none', background:'transparent', outline:'none',
    fontFamily:"'DM Sans',sans-serif", fontSize:14, color:'#1C1915',
  },
  filterBtn: {
    display:'flex', alignItems:'center', gap:6,
    padding:'0 14px', height:36, borderRadius:8,
    fontSize:13, fontWeight:500, color:'#554D49',
    border:'1.5px solid #DDD8CF', cursor:'pointer',
    transition:'border-color 120ms, color 120ms', background:'transparent',
    flexShrink:0,
  },
  filterBtnActive: {
    borderColor:'#1A8A5A', color:'#1A8A5A',
  },
  filterBadge: {
    background:'#1A8A5A', color:'#fff', borderRadius:999,
    fontSize:10, fontWeight:700, minWidth:16, height:16,
    display:'flex', alignItems:'center', justifyContent:'center', padding:'0 4px',
  },
  iconBtn: {
    width:36, height:36, borderRadius:8, display:'flex',
    alignItems:'center', justifyContent:'center',
    color:'#706560', cursor:'pointer',
    border:'1px solid transparent', flexShrink:0,
  },
};

function Header({ query, onQueryChange, onToggleFilters, filterCount, view, onLogoClick }) {
  const [focused, setFocused] = useState(false);
  const inputRef = useRef(null);

  const activeFilters = filterCount > 0;

  return (
    <header style={headerStyles.header}>
      <div style={headerStyles.logo} onClick={onLogoClick} role="button" tabIndex={0}>
        <PandaLogo />
        <div style={headerStyles.wordmark}>
          <span style={{fontWeight:600, color:'#1C1915'}}>Panda</span>
          <span style={{fontWeight:400, color:'#1A8A5A'}}>Watch</span>
        </div>
      </div>

      <div
        style={{
          ...headerStyles.searchWrap,
          ...(focused ? headerStyles.searchWrapFocused : {}),
        }}
        onClick={() => inputRef.current?.focus()}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
          stroke={focused ? '#1A8A5A' : '#A89E93'} strokeWidth="2">
          <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
        </svg>
        <input
          ref={inputRef}
          type="text"
          placeholder="Search by manga, series, publisher, ISBN…"
          value={query}
          onChange={e => onQueryChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          style={headerStyles.searchInput}
        />
        {query && (
          <div onClick={() => onQueryChange('')} style={{cursor:'pointer', color:'#A89E93', display:'flex'}}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="15" y1="9" x2="9" y2="15"/>
              <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
          </div>
        )}
      </div>

      {view === 'catalog' && (
        <button
          style={{
            ...headerStyles.filterBtn,
            ...(activeFilters ? headerStyles.filterBtnActive : {}),
          }}
          onClick={onToggleFilters}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="4" y1="6" x2="20" y2="6"/>
            <line x1="8" y1="12" x2="16" y2="12"/>
            <line x1="11" y1="18" x2="13" y2="18"/>
          </svg>
          Filters
          {filterCount > 0 && <div style={headerStyles.filterBadge}>{filterCount}</div>}
        </button>
      )}
    </header>
  );
}

Object.assign(window, { Header, PandaLogo });
