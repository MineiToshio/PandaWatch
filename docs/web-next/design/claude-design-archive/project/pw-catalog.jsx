/* ═══════════════════════════════════════════
   PW-CATALOG.JSX — A1 Discovery / Catalog
   FilterSidebar · DiscoveryStrip · BentoGrid
   CatalogScreen (desktop + mobile)
═══════════════════════════════════════════ */

const EDITION_TYPES = [
  { key:'deluxe',    label:'Deluxe',    icon:'📘', color:'#D48A0C' },
  { key:'limited',   label:'Limitada',  icon:'🔴', color:'#E05830' },
  { key:'boxset',    label:'Box Set',   icon:'📦', color:'#0CA99E' },
  { key:'artbook',   label:'Artbook',   icon:'🎨', color:'#9540E6' },
  { key:'kanzenban', label:'Rare',       icon:'⭐', color:'#F5C242' },
  { key:'variant',   label:'Super Rare', icon:'✨', color:'#C46BFF' },
];

const COUNTRIES = [
  { code:'JP', label:'Japón' }, { code:'FR', label:'Francia' },
  { code:'US', label:'EE.UU.' }, { code:'ES', label:'España' },
  { code:'IT', label:'Italia' }, { code:'BR', label:'Brasil' },
];

const SORT_OPTIONS = [
  { key:'score', label:'Score ↓' },
  { key:'detected', label:'Más recientes' },
  { key:'price_asc', label:'Precio ↑' },
  { key:'price_desc', label:'Precio ↓' },
  { key:'title', label:'Título A→Z' },
];

function useFilteredEditions(filters, sort) {
  return React.useMemo(() => {
    let list = [...MOCK_EDITIONS];
    if (filters.types.length)     list = list.filter(e => filters.types.includes(e.type));
    if (filters.countries.length) list = list.filter(e => filters.countries.includes(e.country));
    if (filters.inStock)          list = list.filter(e => e.stock !== 'unavailable');
    if (filters.minScore > 0)     list = list.filter(e => e.score >= filters.minScore);
    if (filters.search.trim())    list = list.filter(e =>
      e.title.toLowerCase().includes(filters.search.toLowerCase()) ||
      (e.titleJp && e.titleJp.includes(filters.search))
    );
    switch (sort) {
      case 'score':      return list.sort((a,b) => b.score - a.score);
      case 'detected':   return list.sort((a,b) => b.id - a.id);
      case 'price_asc':  return list.sort((a,b) => (a.priceMin||999) - (b.priceMin||999));
      case 'price_desc': return list.sort((a,b) => (b.priceMin||0)   - (a.priceMin||0));
      case 'title':      return list.sort((a,b) => a.title.localeCompare(b.title));
      default: return list;
    }
  }, [filters, sort]);
}

/* ── Filter Sidebar (Desktop) ── */
function FilterSidebar({ filters, onChange }) {
  const toggle = (key, arr) => onChange({
    ...filters,
    [key]: filters[key].includes(arr) ? filters[key].filter(x => x !== arr) : [...filters[key], arr],
  });

  const hasFilters = filters.types.length || filters.countries.length ||
    filters.inStock || filters.minScore > 0 || filters.search.trim();

  return (
    <div className="pw-sidebar">
      {/* Search */}
      <div style={{ position:'relative', marginBottom:'var(--s5)' }}>
        <span style={{ position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',
          fontSize:13,color:'var(--text-muted)',pointerEvents:'none' }}>🔍</span>
        <input
          value={filters.search}
          onChange={e => onChange({ ...filters, search: e.target.value })}
          placeholder="Buscar edición..."
          style={{
            width:'100%', paddingLeft:32, paddingRight:12, paddingTop:8, paddingBottom:8,
            background:'var(--surface-2)', border:'1px solid var(--border-md)',
            borderRadius:'var(--r-md)', color:'var(--text)', fontSize:12,
            fontFamily:'var(--f-body)', outline:'none',
          }}
        />
      </div>

      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'var(--s4)' }}>
        <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)' }}>
          Filtros
        </div>
        {hasFilters && (
          <button onClick={() => onChange({ types:[], countries:[], inStock:false, minScore:0, search:'' })}
            style={{ fontSize:10,color:'var(--danger)',background:'none',border:'none',cursor:'pointer',fontFamily:'var(--f-body)',fontWeight:600 }}>
            Reset
          </button>
        )}
      </div>

      {/* Edition types */}
      <div style={{ marginBottom:'var(--s6)' }}>
        <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)' }}>
          Tipo de edición
        </div>
        <div style={{ display:'flex', flexWrap:'wrap', gap:'var(--s2)' }}>
          {EDITION_TYPES.map(t => (
            <Chip key={t.key} label={t.label} icon={t.icon} color={t.color}
              selected={filters.types.includes(t.key)}
              onClick={() => toggle('types', t.key)}
            />
          ))}
        </div>
      </div>

      {/* Countries */}
      <div style={{ marginBottom:'var(--s6)' }}>
        <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)' }}>
          País / Idioma
        </div>
        <div style={{ display:'flex', flexWrap:'wrap', gap:'var(--s2)' }}>
          {COUNTRIES.map(c => (
            <Chip key={c.code} label={c.label} flag={c.code}
              selected={filters.countries.includes(c.code)}
              onClick={() => toggle('countries', c.code)}
            />
          ))}
        </div>
      </div>

      {/* Score */}
      <div style={{ marginBottom:'var(--s6)' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'var(--s3)' }}>
          <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)' }}>
            Score mínimo
          </div>
          {filters.minScore > 0 && (
            <div style={{ fontSize:11,fontWeight:700,color:'var(--gold)',padding:'1px 8px',
              background:'var(--gold-dim)',border:'1px solid var(--gold)',borderRadius:'var(--r-full)' }}>
              {filters.minScore}+
            </div>
          )}
        </div>
        <input type="range" min={0} max={99} step={5} value={filters.minScore}
          onChange={e => onChange({ ...filters, minScore: +e.target.value })}
          style={{ width:'100%', accentColor:'var(--gold)' }}
        />
        <div style={{ display:'flex', justifyContent:'space-between', fontSize:9, color:'var(--text-muted)', marginTop:2 }}>
          <span>Todos</span><span>99+</span>
        </div>
      </div>

      {/* Toggles */}
      <div style={{ display:'flex', flexDirection:'column', gap:'var(--s3)', marginBottom:'var(--s7)' }}>
        {[
          { key:'inStock', label:'Solo con stock' },
        ].map(item => (
          <label key={item.key} style={{ display:'flex', alignItems:'center', gap:'var(--s3)', cursor:'pointer' }}>
            <div onClick={() => onChange({ ...filters, [item.key]: !filters[item.key] })} style={{
              width:36, height:20, borderRadius:10, position:'relative', cursor:'pointer',
              background: filters[item.key] ? 'var(--gold)' : 'var(--surface-3)',
              transition:'background .15s', flexShrink:0,
            }}>
              <div style={{
                position:'absolute', top:3, left: filters[item.key] ? 18 : 3,
                width:14, height:14, borderRadius:'50%', background:'#fff',
                transition:'left .15s', boxShadow:'0 1px 3px rgba(0,0,0,.3)',
              }} />
            </div>
            <span style={{ fontSize:12, color:'var(--text-sec)', userSelect:'none' }}>{item.label}</span>
          </label>
        ))}
      </div>

      {/* Save search (future feature) */}
      <button style={{
        width:'100%', padding:'8px 12px', borderRadius:'var(--r-md)',
        background:'var(--surface-2)', border:'1px solid var(--border-md)',
        color:'var(--text-muted)', fontSize:11, fontWeight:600,
        cursor:'pointer', display:'flex', alignItems:'center', gap:6,
        fontFamily:'var(--f-body)',
      }}>
        <span>🔖</span>
        Guardar esta búsqueda
        <span style={{ marginLeft:'auto', fontSize:9, color:'var(--indigo)',
          background:'var(--indigo-dim)', padding:'1px 6px',
          borderRadius:'var(--r-full)', border:'1px solid var(--indigo)' }}>
          Próximamente
        </span>
      </button>
    </div>
  );
}

/* ── Discovery Strip ── */
function DiscoveryStrip({ navigate }) {
  const recent = NEW_DETECTIONS;
  return (
    <div style={{ background:'var(--surface-2)', borderBottom:'1px solid var(--border)', padding:'var(--s4) 0' }}>
      <div style={{ padding:'0 var(--s6) var(--s3)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'var(--s2)' }}>
          <span style={{ fontSize:14 }}>🔍</span>
          <span style={{ fontFamily:'var(--f-display)', fontSize:14, fontWeight:700, color:'var(--text)', letterSpacing:'-0.01em' }}>
            Nuevos hallazgos
          </span>
          <div style={{
            fontSize:9, fontWeight:800, letterSpacing:'.08em',
            background:'var(--danger-dim)', color:'var(--danger)',
            border:'1px solid var(--danger)', borderRadius:'var(--r-full)',
            padding:'1px 8px', textTransform:'uppercase',
          }}>
            {recent.length} detectados · 24h
          </div>
        </div>
        <button style={{ fontSize:11, color:'var(--gold)', background:'none', border:'none', cursor:'pointer', fontFamily:'var(--f-body)', fontWeight:600 }}>
          Ver todos →
        </button>
      </div>
      <div style={{ display:'flex', gap:'var(--s4)', paddingLeft:'var(--s6)', overflowX:'auto', paddingBottom:'var(--s2)', scrollbarWidth:'none' }}>
        {recent.map(e => (
          <div key={e.id} style={{ flexShrink:0, width:150 }}>
            <MangaCard edition={e} size="sm"
              onClick={() => navigate('detail', { productId: e.id })}
            />
          </div>
        ))}
        <div style={{ width:'var(--s4)', flexShrink:0 }} />
      </div>
    </div>
  );
}

/* ── Bento Grid ── */
function BentoGrid({ editions, navigate, isMobile }) {
  if (isMobile) {
    return (
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'var(--s3)', padding:'var(--s4)' }}>
        {editions.map(e => (
          <MangaCard key={e.id} edition={e} size="sm" isMobile
            onClick={() => navigate('detail', { productId: e.id })}
          />
        ))}
      </div>
    );
  }

  return (
    <div style={{ padding:'var(--s6)' }}>
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4, 1fr)', gap:'var(--s5)' }}>
        {editions.map(e => (
          <MangaCard key={e.id} edition={e} size="md"
            onClick={() => navigate('detail', { productId: e.id })}
          />
        ))}
      </div>
    </div>
  );
}

/* ── Content header (sort + count) ── */
function ContentHeader({ count, sort, onSort, filters }) {
  const activeCount = filters.types.length + filters.countries.length +
    (filters.inStock ? 1 : 0) + (filters.minScore > 0 ? 1 : 0);

  return (
    <div style={{
      display:'flex', alignItems:'center', gap:'var(--s4)',
      padding:'var(--s4) var(--s6)', borderBottom:'1px solid var(--border)',
      background:'var(--bg)',
    }}>
      <div style={{ fontSize:13, color:'var(--text-sec)', flex:1 }}>
        <span style={{ fontWeight:700, color:'var(--text)' }}>{count}</span> ediciones
        {activeCount > 0 && (
          <span style={{ marginLeft:8, fontSize:11, color:'var(--gold)', background:'var(--gold-dim)',
            border:'1px solid var(--gold)', padding:'1px 8px', borderRadius:'var(--r-full)', fontWeight:700 }}>
            {activeCount} filtros activos
          </span>
        )}
      </div>
      <div style={{ display:'flex', alignItems:'center', gap:'var(--s2)' }}>
        <span style={{ fontSize:11, color:'var(--text-muted)' }}>Ordenar:</span>
        <select value={sort} onChange={e => onSort(e.target.value)} style={{
          padding:'5px 10px', background:'var(--surface-2)', border:'1px solid var(--border-md)',
          borderRadius:'var(--r-md)', color:'var(--text)', fontSize:12,
          fontFamily:'var(--f-body)', cursor:'pointer', outline:'none',
        }}>
          {SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>
    </div>
  );
}

/* ── Pagination ── */
function Pagination({ current, total, onChange }) {
  const pages = [1,2,3,4,5,'…',total];
  return (
    <div style={{
      display:'flex', alignItems:'center', justifyContent:'center',
      gap:'var(--s2)', padding:'var(--s8) var(--s6)',
      borderTop:'1px solid var(--border)',
    }}>
      <button onClick={() => onChange(Math.max(1, current-1))} style={{
        padding:'7px 14px', background:'var(--surface-2)',
        border:'1px solid var(--border-md)', borderRadius:'var(--r-md)',
        color:'var(--text-sec)', cursor:'pointer', fontSize:12,
        fontFamily:'var(--f-body)', fontWeight:500,
      }}>← Anterior</button>
      {pages.map((p,i) => (
        <button key={i} onClick={() => typeof p === 'number' && onChange(p)} style={{
          width:34,height:34,
          background: p === current ? 'var(--gold)' : p === '…' ? 'transparent' : 'var(--surface-2)',
          border: p === current ? 'none' : '1px solid var(--border)',
          borderRadius:'var(--r-md)',
          color: p === current ? 'var(--gold-text)' : p === '…' ? 'var(--text-muted)' : 'var(--text-sec)',
          cursor: p === '…' ? 'default' : 'pointer',
          fontSize:12, fontWeight: p === current ? 700 : 400,
          fontFamily:'var(--f-body)',
          boxShadow: p === current ? 'var(--sh-gold)' : 'none',
        }}>{p}</button>
      ))}
      <button onClick={() => onChange(Math.min(total, current+1))} style={{
        padding:'7px 14px', background:'var(--surface-2)',
        border:'1px solid var(--border-md)', borderRadius:'var(--r-md)',
        color:'var(--text-sec)', cursor:'pointer', fontSize:12,
        fontFamily:'var(--f-body)', fontWeight:500,
      }}>Siguiente →</button>
    </div>
  );
}

/* ── Mobile Filter Sheet ── */
function MobileFilterSheet({ filters, onChange, onClose }) {
  return (
    <div style={{
      position:'absolute', inset:0, zIndex:200,
      background:'rgba(0,0,0,.6)', backdropFilter:'blur(4px)',
      display:'flex', flexDirection:'column', justifyContent:'flex-end',
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background:'var(--surface)', borderRadius:'var(--r-2xl) var(--r-2xl) 0 0',
        padding:'var(--s6) var(--s5) var(--s8)',
        maxHeight:'75%', overflowY:'auto',
      }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'var(--s5)' }}>
          <div style={{ fontFamily:'var(--f-display)', fontSize:18, fontWeight:700, color:'var(--text)' }}>
            Filtros
          </div>
          <button onClick={onClose} style={{
            width:28,height:28, borderRadius:'50%', border:'none',
            background:'var(--surface-2)', color:'var(--text-sec)',
            cursor:'pointer', fontSize:14,
          }}>✕</button>
        </div>

        <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)' }}>
          Tipo de edición
        </div>
        <div style={{ display:'flex', flexWrap:'wrap', gap:'var(--s2)', marginBottom:'var(--s5)' }}>
          {EDITION_TYPES.map(t => (
            <Chip key={t.key} label={t.label} icon={t.icon} color={t.color}
              selected={filters.types.includes(t.key)}
              onClick={() => onChange({
                ...filters,
                types: filters.types.includes(t.key)
                  ? filters.types.filter(x => x !== t.key)
                  : [...filters.types, t.key]
              })}
            />
          ))}
        </div>

        <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)' }}>
          País
        </div>
        <div style={{ display:'flex', flexWrap:'wrap', gap:'var(--s2)', marginBottom:'var(--s5)' }}>
          {COUNTRIES.map(c => (
            <Chip key={c.code} label={c.label} flag={c.code}
              selected={filters.countries.includes(c.code)}
              onClick={() => onChange({
                ...filters,
                countries: filters.countries.includes(c.code)
                  ? filters.countries.filter(x => x !== c.code)
                  : [...filters.countries, c.code]
              })}
            />
          ))}
        </div>

        <label style={{ display:'flex', alignItems:'center', gap:'var(--s3)', cursor:'pointer', marginBottom:'var(--s6)' }}>
          <div onClick={() => onChange({ ...filters, inStock: !filters.inStock })} style={{
            width:40,height:22,borderRadius:11,position:'relative',cursor:'pointer',
            background: filters.inStock ? 'var(--gold)' : 'var(--surface-3)',transition:'background .15s',
          }}>
            <div style={{
              position:'absolute',top:4,left: filters.inStock ? 20 : 4,
              width:14,height:14,borderRadius:'50%',background:'#fff',
              transition:'left .15s',
            }}/>
          </div>
          <span style={{ fontSize:13, color:'var(--text-sec)' }}>Solo con stock</span>
        </label>

        <div style={{ display:'flex', gap:'var(--s3)' }}>
          <button onClick={() => onChange({ types:[], countries:[], inStock:false, minScore:0, search:'' })} style={{
            flex:1, padding:'10px', borderRadius:'var(--r-md)',
            background:'var(--surface-2)', border:'1px solid var(--border-md)',
            color:'var(--text-sec)', fontSize:13, fontWeight:600,
            cursor:'pointer', fontFamily:'var(--f-body)',
          }}>Limpiar</button>
          <button onClick={onClose} style={{
            flex:2, padding:'10px', borderRadius:'var(--r-md)',
            background:'var(--gold)', border:'none',
            color:'var(--gold-text)', fontSize:13, fontWeight:700,
            cursor:'pointer', fontFamily:'var(--f-body)',
          }}>Ver resultados</button>
        </div>
      </div>
    </div>
  );
}

/* ═══ CATALOG SCREEN ═══ */
function CatalogScreen({ navigate, isMobile }) {
  const [filters, setFilters] = React.useState({ types:[], countries:[], inStock:false, minScore:0, search:'' });
  const [sort, setSort] = React.useState('score');
  const [page, setPage] = React.useState(1);
  const [showSheet, setShowSheet] = React.useState(false);
  const filtered = useFilteredEditions(filters, sort);

  if (isMobile) {
    return (
      <div style={{ position:'relative', minHeight:'100%' }}>
        {/* Mobile top bar */}
        <div style={{ padding:'var(--s3) var(--s4)', borderBottom:'1px solid var(--border)' }}>
          <div style={{ position:'relative', marginBottom:'var(--s3)' }}>
            <span style={{ position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',fontSize:13,color:'var(--text-muted)',pointerEvents:'none' }}>🔍</span>
            <input
              value={filters.search}
              onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
              placeholder="Buscar edición..."
              style={{
                width:'100%', paddingLeft:32, paddingRight:12, paddingTop:9, paddingBottom:9,
                background:'var(--surface-2)', border:'1px solid var(--border-md)',
                borderRadius:'var(--r-full)', color:'var(--text)', fontSize:12,
                fontFamily:'var(--f-body)', outline:'none',
              }}
            />
          </div>
          <div style={{ display:'flex', gap:'var(--s2)', justifyContent:'space-between', alignItems:'center' }}>
            <button onClick={() => setShowSheet(true)} style={{
              display:'flex', alignItems:'center', gap:6,
              padding:'7px 14px', background:'var(--surface-2)',
              border:'1px solid var(--border-md)', borderRadius:'var(--r-full)',
              color:'var(--text-sec)', fontSize:12, fontWeight:600,
              cursor:'pointer', fontFamily:'var(--f-body)',
            }}>
              🎛 Filtros
              {(filters.types.length + filters.countries.length + (filters.inStock ? 1 : 0)) > 0 && (
                <span style={{ background:'var(--gold)',color:'var(--gold-text)',borderRadius:'var(--r-full)',
                  width:16,height:16,display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:800 }}>
                  {filters.types.length + filters.countries.length + (filters.inStock ? 1 : 0)}
                </span>
              )}
            </button>
            <select value={sort} onChange={e => setSort(e.target.value)} style={{
              padding:'7px 10px', background:'var(--surface-2)', border:'1px solid var(--border-md)',
              borderRadius:'var(--r-full)', color:'var(--text)', fontSize:11,
              fontFamily:'var(--f-body)', outline:'none',
            }}>
              {SORT_OPTIONS.map(o => <option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {/* Discovery strip */}
        <div style={{ background:'var(--surface-2)', borderBottom:'1px solid var(--border)', padding:'var(--s3) 0' }}>
          <div style={{ padding:'0 var(--s4) var(--s2)', fontSize:11, fontWeight:700, color:'var(--text)', display:'flex', alignItems:'center', gap:'var(--s2)' }}>
            🔍 Nuevos hallazgos
            <span style={{ fontSize:8, background:'var(--danger-dim)', color:'var(--danger)', border:'1px solid var(--danger)', borderRadius:'var(--r-full)', padding:'1px 6px', fontWeight:800, letterSpacing:'.06em', textTransform:'uppercase' }}>
              {NEW_DETECTIONS.length} · 24h
            </span>
          </div>
          <div style={{ display:'flex', gap:'var(--s3)', paddingLeft:'var(--s4)', overflowX:'auto', scrollbarWidth:'none' }}>
            {NEW_DETECTIONS.map(e => (
              <div key={e.id} onClick={() => navigate('detail', { productId: e.id })}
                style={{ flexShrink:0, width:90, cursor:'pointer' }}>
                <div className="cover-ph" style={{ height:120, borderRadius:'var(--r-md)', overflow:'hidden',
                  background: e.type === 'ultra' ? 'linear-gradient(160deg,#0a0020,#060818)' :
                    e.type === 'kanzenban' ? 'linear-gradient(160deg,#1a1400,#251d00)' : undefined }}>
                  <span style={{ fontSize:7, color:'rgba(255,255,255,.2)' }}>{e.title.slice(0,12)}</span>
                  {e.type === 'kanzenban' && <div className="cover-foil-gold" />}
                  {e.type === 'variant'   && <div className="cover-foil-variant" />}
                  {e.type === 'ultra'     && <><div className="cover-foil-ultra" /><div className="cover-shine" /></>}
                </div>
                <div style={{ fontSize:8, fontWeight:600, color:'var(--text)', marginTop:4, lineHeight:1.3,
                  overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{e.title}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Grid */}
        <div style={{ padding:'var(--s4)' }}>
          <div style={{ fontSize:11,color:'var(--text-muted)',marginBottom:'var(--s3)' }}>
            <span style={{ fontWeight:700,color:'var(--text)' }}>{filtered.length}</span> ediciones
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'var(--s3)' }}>
            {filtered.map(e => (
              <MangaCard key={e.id} edition={e} size="sm" isMobile
                onClick={() => navigate('detail', { productId: e.id })}
              />
            ))}
          </div>
        </div>

        {showSheet && (
          <MobileFilterSheet
            filters={filters}
            onChange={setFilters}
            onClose={() => setShowSheet(false)}
          />
        )}
      </div>
    );
  }

  /* DESKTOP */
  return (
    <div className="pw-body">
      <FilterSidebar filters={filters} onChange={setFilters} />
      <div className="pw-main">
        <DiscoveryStrip navigate={navigate} />
        <ContentHeader count={filtered.length} sort={sort} onSort={setSort} filters={filters} />
        {filtered.length === 0 ? (
          <div style={{ padding:'var(--s12)', textAlign:'center' }}>
            <div style={{ fontSize:48, marginBottom:'var(--s4)' }}>🐼</div>
            <div style={{ fontFamily:'var(--f-display)', fontSize:22, fontWeight:700, color:'var(--text)', marginBottom:'var(--s3)', letterSpacing:'-0.02em' }}>
              El panda no encontró nada
            </div>
            <div style={{ fontSize:13, color:'var(--text-muted)', marginBottom:'var(--s6)' }}>
              Probá con otros filtros — quizás esa edición existe en otro país.
            </div>
            <button onClick={() => setFilters({ types:[], countries:[], inStock:false, minScore:0, search:'' })} style={{
              padding:'8px 20px', background:'var(--gold-dim)', border:'1px solid var(--gold)',
              borderRadius:'var(--r-md)', color:'var(--gold)', fontSize:12,
              fontWeight:600, cursor:'pointer', fontFamily:'var(--f-body)',
            }}>Limpiar filtros</button>
          </div>
        ) : (
          <BentoGrid editions={filtered} navigate={navigate} isMobile={false} />
        )}
        <Pagination current={page} total={28} onChange={setPage} />
      </div>
    </div>
  );
}

Object.assign(window, { CatalogScreen });
