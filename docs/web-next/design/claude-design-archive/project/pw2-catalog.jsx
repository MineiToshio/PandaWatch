/* ═══════════════════════════════════════════
   PW2-CATALOG.JSX — v2 Catalog / A1
   FilterSidebar · DiscoveryStrip · BentoGrid
   EmptyState · CatalogScreen (desktop + mobile)
═══════════════════════════════════════════ */

const EDITION_TYPES = [
  { key:'standard',  label:'Standard',  color:'#788399' },
  { key:'deluxe',    label:'Deluxe',    color:'#D48A0C' },
  { key:'limited',   label:'Limited',   color:'#E05830' },
  { key:'boxset',    label:'Box Set',   color:'#0CA99E' },
  { key:'artbook',   label:'Artbook',   color:'#9540E6' },
  { key:'kanzenban', label:'Kanzenban', color:'#C8951C' },
  { key:'variant',   label:'Variant',   color:'#C46BFF' },
  { key:'omnibus',   label:'Omnibus',   color:'#7A9CC0' },
];

const COUNTRIES = [
  {code:'JP',label:'Japón'},{code:'FR',label:'Francia'},
  {code:'US',label:'EE.UU.'},{code:'ES',label:'España'},
  {code:'IT',label:'Italia'},{code:'BR',label:'Brasil'},
];

const SORT_OPTIONS = [
  {key:'score',      label:'Score ↓'},
  {key:'detected',   label:'Más recientes'},
  {key:'price_asc',  label:'Precio ↑ (exp.)'},
  {key:'title',      label:'Título A→Z'},
];

const RARITY_RADIO = [
  {value:null,       label:'Cualquiera',    color:null},
  {value:'rare',     label:'◆ Rare',        color:'#F5C242'},
  {value:'super_rare',label:'◆◆ Super Rare',color:'#FFB84A'},
  {value:'ultra_rare',label:'✦ Ultra Rare', color:'#C46BFF'},
];

const LANGUAGES  = [{code:'JP',label:'Japonés'},{code:'FR',label:'Francés'},{code:'EN',label:'Inglés'},{code:'ES',label:'Español'},{code:'IT',label:'Italiano'},{code:'PT',label:'Portugués (BR)'}];
const PROD_TYPES  = ['Manga','Artbook','Light Novel','Magazine','Fanbook'];
const SRC_CLASSES = ['Retail','Aggregator','Official','Reference'];

function defaultFilters() {
  return { types:[], rarityTier:null, countries:[], limitedStock:false, minScore:0, search:'',
    editorial:'', language:'', productType:'', sourceClass:'' };
}

function useFilteredEditions(filters, sort) {
  return React.useMemo(()=>{
    let list=[...MOCK_EDITIONS];
    if(filters.types.length)     list=list.filter(e=>filters.types.some(t=>e.formatTypes.includes(t)));
    if(filters.rarityTier)       list=list.filter(e=>e.rarityTier===filters.rarityTier);
    if(filters.countries.length) list=list.filter(e=>filters.countries.includes(e.country));
    if(filters.limitedStock)     list=list.filter(e=>e.stock_type==='limited');
    if(filters.minScore>0)       list=list.filter(e=>e.score>=filters.minScore);
    if(filters.search.trim())    list=list.filter(e=>
      e.title.toLowerCase().includes(filters.search.toLowerCase())||
      (e.title_original&&e.title_original.toLowerCase().includes(filters.search.toLowerCase()))
    );
    switch(sort){
      case 'score':    return list.sort((a,b)=>b.score-a.score);
      case 'detected': return list.sort((a,b)=>b.id-a.id);
      case 'price_asc':return list.sort((a,b)=>a.id-b.id);
      case 'title':    return list.sort((a,b)=>a.title.localeCompare(b.title));
      default: return list;
    }
  },[filters,sort]);
}

/* ── Sidebar section label ── */
function SbLabel({ children }) {
  return <div style={{fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)'}}>{children}</div>;
}

/* ── Mini toggle pill ── */
function Toggle({ on, onClick }) {
  return (
    <div onClick={onClick} style={{width:36,height:20,borderRadius:10,position:'relative',cursor:'pointer',
      background:on?'var(--gold)':'var(--surface-3)',transition:'background .15s',flexShrink:0}}>
      <div style={{position:'absolute',top:3,left:on?18:3,width:14,height:14,borderRadius:'50%',
        background:'#fff',transition:'left .15s',boxShadow:'0 1px 3px rgba(0,0,0,.3)'}}/>
    </div>
  );
}

/* ── Filter Sidebar ── */
function FilterSidebar({ filters, onChange }) {
  const [showMore, setShowMore] = React.useState(false);
  const toggle = (key,val) => onChange({
    ...filters,
    [key]: filters[key].includes(val)?filters[key].filter(x=>x!==val):[...filters[key],val],
  });
  const hasFilters = filters.types.length||filters.rarityTier||filters.countries.length||
    filters.limitedStock||filters.minScore>0||filters.search.trim()||
    filters.editorial||filters.language||filters.productType||filters.sourceClass;

  return (
    <div className="pw-sidebar">
      {/* Search */}
      <div style={{position:'relative',marginBottom:'var(--s5)'}}>
        <span style={{position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',fontSize:13,color:'var(--text-muted)',pointerEvents:'none'}}>🔍</span>
        <input value={filters.search} onChange={e=>onChange({...filters,search:e.target.value})}
          placeholder="Buscar edición..."
          style={{width:'100%',paddingLeft:32,paddingRight:12,paddingTop:8,paddingBottom:8,
            background:'var(--surface-2)',border:'1px solid var(--border-md)',
            borderRadius:'var(--r-md)',color:'var(--text)',fontSize:12,fontFamily:'var(--f-body)',outline:'none'}}/>
      </div>

      {/* Header row */}
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'var(--s4)'}}>
        <div style={{fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)'}}>Filtros</div>
        {hasFilters&&<button onClick={()=>onChange(defaultFilters())} style={{fontSize:10,color:'var(--danger)',background:'none',border:'none',cursor:'pointer',fontFamily:'var(--f-body)',fontWeight:600}}>Reset</button>}
      </div>

      {/* Tipo de edición — 8 flat chips */}
      <div style={{marginBottom:'var(--s5)'}}>
        <SbLabel>Tipo de edición</SbLabel>
        <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)'}}>
          {EDITION_TYPES.map(t=>(
            <Chip key={t.key} label={t.label} color={t.color}
              selected={filters.types.includes(t.key)}
              onClick={()=>toggle('types',t.key)}/>
          ))}
        </div>
      </div>

      {/* Rareza — radio group (new in v2) */}
      <div style={{marginBottom:'var(--s5)',background:'var(--surface-2)',borderRadius:'var(--r-lg)',padding:'var(--s4)'}}>
        <SbLabel>Rareza</SbLabel>
        <div style={{display:'flex',flexDirection:'column',gap:'var(--s2)'}}>
          {RARITY_RADIO.map(opt=>{
            const sel=filters.rarityTier===opt.value;
            const c=opt.color||'var(--gold)';
            return (
              <label key={String(opt.value)} style={{display:'flex',alignItems:'center',gap:'var(--s3)',cursor:'pointer'}}
                onClick={()=>onChange({...filters,rarityTier:opt.value})}>
                <div style={{width:14,height:14,borderRadius:'50%',flexShrink:0,
                  border:`2px solid ${sel?c:'var(--border-md)'}`,
                  background:sel?c:'transparent',transition:'all .12s'}}/>
                <span style={{fontSize:12,color:sel?c:'var(--text-sec)',fontWeight:sel?700:400,transition:'color .12s'}}>
                  {opt.label}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      {/* País */}
      <div style={{marginBottom:'var(--s5)'}}>
        <SbLabel>País</SbLabel>
        <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)'}}>
          {COUNTRIES.map(c=>(
            <Chip key={c.code} label={c.label} flag={c.code}
              selected={filters.countries.includes(c.code)}
              onClick={()=>toggle('countries',c.code)}/>
          ))}
        </div>
      </div>

      {/* Más filtros — collapsible */}
      <div style={{marginBottom:'var(--s5)'}}>
        <button onClick={()=>setShowMore(m=>!m)} style={{
          display:'flex',width:'100%',alignItems:'center',justifyContent:'space-between',
          background:'none',border:'none',cursor:'pointer',padding:'4px 0',fontFamily:'var(--f-body)',
        }}>
          <SbLabel>{showMore?'▲ Menos filtros':'▼ Más filtros'}</SbLabel>
          {(filters.editorial||filters.language||filters.productType||filters.sourceClass)&&(
            <span style={{fontSize:9,fontWeight:800,background:'var(--indigo-dim)',color:'var(--indigo)',border:'1px solid var(--indigo)',borderRadius:'var(--r-full)',padding:'1px 5px'}}>activo</span>
          )}
        </button>
        {showMore&&(
          <div style={{marginTop:'var(--s3)',display:'flex',flexDirection:'column',gap:'var(--s4)',
            borderLeft:'2px solid var(--border)',paddingLeft:'var(--s4)'}}>

            {/* Editorial */}
            <div>
              <div style={{fontSize:10,color:'var(--text-muted)',marginBottom:'var(--s2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em'}}>Editorial</div>
              <input value={filters.editorial} onChange={e=>onChange({...filters,editorial:e.target.value})}
                placeholder="Kodansha, Viz Media..."
                style={{width:'100%',padding:'6px 8px',background:'var(--surface-2)',border:'1px solid var(--border-md)',
                  borderRadius:'var(--r-sm)',color:'var(--text)',fontSize:11,fontFamily:'var(--f-body)',outline:'none'}}/>
            </div>

            {/* Idioma */}
            <div>
              <div style={{fontSize:10,color:'var(--text-muted)',marginBottom:'var(--s2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em'}}>Idioma</div>
              <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)'}}>
                {LANGUAGES.map(l=>(
                  <div key={l.code} onClick={()=>onChange({...filters,language:filters.language===l.code?'':l.code})} style={{
                    padding:'3px 9px',borderRadius:'var(--r-full)',fontSize:10,fontWeight:600,cursor:'pointer',
                    background:filters.language===l.code?'var(--surface-3)':'var(--surface-2)',
                    border:`1px solid ${filters.language===l.code?'var(--border-lg)':'var(--border)'}`,
                    color:filters.language===l.code?'var(--text)':'var(--text-muted)',transition:'all .1s',
                  }}>{l.label}</div>
                ))}
              </div>
            </div>

            {/* Tipo de producto */}
            <div>
              <div style={{fontSize:10,color:'var(--text-muted)',marginBottom:'var(--s2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em'}}>Tipo de producto</div>
              <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)'}}>
                {PROD_TYPES.map(t=>(
                  <div key={t} onClick={()=>onChange({...filters,productType:filters.productType===t?'':t})} style={{
                    padding:'3px 9px',borderRadius:'var(--r-full)',fontSize:10,fontWeight:600,cursor:'pointer',
                    background:filters.productType===t?'var(--surface-3)':'var(--surface-2)',
                    border:`1px solid ${filters.productType===t?'var(--border-lg)':'var(--border)'}`,
                    color:filters.productType===t?'var(--text)':'var(--text-muted)',transition:'all .1s',
                  }}>{t}</div>
                ))}
              </div>
            </div>

            {/* Clase de fuente */}
            <div>
              <div style={{fontSize:10,color:'var(--text-muted)',marginBottom:'var(--s2)',fontWeight:600,textTransform:'uppercase',letterSpacing:'.06em'}}>Clase de fuente</div>
              <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)'}}>
                {SRC_CLASSES.map(s=>(
                  <div key={s} onClick={()=>onChange({...filters,sourceClass:filters.sourceClass===s?'':s})} style={{
                    padding:'3px 9px',borderRadius:'var(--r-full)',fontSize:10,fontWeight:600,cursor:'pointer',
                    background:filters.sourceClass===s?'var(--surface-3)':'var(--surface-2)',
                    border:`1px solid ${filters.sourceClass===s?'var(--border-lg)':'var(--border)'}`,
                    color:filters.sourceClass===s?'var(--text)':'var(--text-muted)',transition:'all .1s',
                  }}>{s}</div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Score mínimo */}
      <div style={{marginBottom:'var(--s5)'}}>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'var(--s3)'}}>
          <SbLabel>Score mínimo</SbLabel>
          {filters.minScore>0&&<div style={{fontSize:11,fontWeight:700,color:'var(--gold)',padding:'1px 8px',background:'var(--gold-dim)',border:'1px solid var(--gold)',borderRadius:'var(--r-full)'}}>{filters.minScore}+</div>}
        </div>
        <input type="range" min={0} max={99} step={5} value={filters.minScore}
          onChange={e=>onChange({...filters,minScore:+e.target.value})}
          style={{width:'100%',accentColor:'var(--gold)'}}/>
        <div style={{display:'flex',justifyContent:'space-between',fontSize:9,color:'var(--text-muted)',marginTop:2}}><span>Todos</span><span>99+</span></div>
      </div>

      {/* Solo stock limitado */}
      <div style={{marginBottom:'var(--s6)'}}>
        <label style={{display:'flex',alignItems:'center',gap:'var(--s3)',cursor:'pointer'}}>
          <Toggle on={filters.limitedStock} onClick={()=>onChange({...filters,limitedStock:!filters.limitedStock})}/>
          <span style={{fontSize:12,color:'var(--text-sec)',userSelect:'none'}}>Solo stock limitado</span>
        </label>
      </div>

      {/* Guardar búsqueda */}
      <button style={{width:'100%',padding:'8px 12px',borderRadius:'var(--r-md)',background:'var(--surface-2)',
        border:'1px solid var(--border-md)',color:'var(--text-muted)',fontSize:11,fontWeight:600,
        cursor:'pointer',display:'flex',alignItems:'center',gap:6,fontFamily:'var(--f-body)'}}>
        <span>🔖</span> Guardar esta búsqueda
        <span style={{marginLeft:'auto'}}><ProximamenteBadge/></span>
      </button>
    </div>
  );
}

/* ── Discovery Strip ── */
function DiscoveryStrip({ navigate }) {
  return (
    <div style={{background:'var(--surface-2)',borderBottom:'1px solid var(--border)',padding:'var(--s4) 0'}}>
      <div style={{padding:'0 var(--s6) var(--s3)',display:'flex',alignItems:'center',justifyContent:'space-between'}}>
        <div style={{display:'flex',alignItems:'center',gap:'var(--s2)'}}>
          <span style={{fontSize:14}}>🔍</span>
          <span style={{fontFamily:'var(--f-display)',fontSize:14,fontWeight:700,color:'var(--text)',letterSpacing:'-.01em'}}>Nuevos hallazgos</span>
          <div style={{fontSize:9,fontWeight:800,letterSpacing:'.08em',background:'var(--danger-dim)',color:'var(--danger)',
            border:'1px solid var(--danger)',borderRadius:'var(--r-full)',padding:'1px 8px',textTransform:'uppercase'}}>
            {NEW_DETECTIONS.length} detectados · 24h
          </div>
        </div>
        <button style={{fontSize:11,color:'var(--gold)',background:'none',border:'none',cursor:'pointer',fontFamily:'var(--f-body)',fontWeight:600}}>Ver todos →</button>
      </div>
      <div style={{display:'flex',gap:'var(--s4)',paddingLeft:'var(--s6)',overflowX:'auto',paddingBottom:'var(--s2)',scrollbarWidth:'none'}}>
        {NEW_DETECTIONS.map((e,i)=>(
          <div key={e.id} style={{flexShrink:0,width:150}}>
            <MangaCard edition={e} size="sm" shineIndex={i} onClick={()=>navigate('detail',{productId:e.id})}/>
          </div>
        ))}
        <div style={{width:'var(--s4)',flexShrink:0}}/>
      </div>
    </div>
  );
}

/* ── Context-aware Empty State ── */
function EmptyState({ filters, onReset }) {
  let title='El panda no encontró nada';
  let body='Probá con otros filtros — quizás esa edición existe en otro país o idioma.';
  let sub=null;

  if(filters.rarityTier==='ultra_rare'){
    title='No hay Ultra Rare en la selección';
    body='El panda aún no encontró ninguna pieza ultra rara con esos filtros.';
    sub='Quizás existen en otro país, otro formato o idioma — o todavía no fueron registradas.';
  } else if(filters.rarityTier==='super_rare'){
    title='No hay Super Rare aquí';
    body='No se encontraron ediciones de tirada muy reducida con la selección actual.';
    sub='Probá ampliar país o tipo de formato.';
  } else if(filters.rarityTier==='rare'){
    title='Sin ediciones raras';
    body='No hay ediciones limitadas confirmadas con estos filtros.';
    sub=null;
  } else if(filters.limitedStock){
    title='Sin stock limitado';
    body='No hay ediciones con tirada acotada en la selección actual.';
    sub=null;
  } else if(filters.search.trim()){
    title='Sin resultados para esa búsqueda';
    body=`"${filters.search.trim()}" no coincide con ninguna edición del catálogo actual.`;
    sub=null;
  }

  return (
    <div style={{textAlign:'center',padding:'80px var(--s8) var(--s8)'}}>
      <div style={{fontSize:52,marginBottom:'var(--s5)'}}>🐼</div>
      <div style={{fontFamily:'var(--f-display)',fontSize:20,fontWeight:700,color:'var(--text)',marginBottom:'var(--s3)',letterSpacing:'-.02em'}}>{title}</div>
      <div style={{fontSize:13,color:'var(--text-muted)',marginBottom:sub?'var(--s2)':'var(--s6)',maxWidth:360,margin:'0 auto',lineHeight:1.7}}>{body}</div>
      {sub&&<div style={{fontSize:12,color:'var(--text-muted)',opacity:.7,marginBottom:'var(--s6)',maxWidth:360,margin:'var(--s2) auto var(--s6)',lineHeight:1.6}}>{sub}</div>}
      <div style={{height:'var(--s6)'}}/>
      <button onClick={onReset} style={{padding:'8px 20px',background:'var(--gold-dim)',border:'1px solid var(--gold)',borderRadius:'var(--r-md)',color:'var(--gold)',fontSize:12,fontWeight:600,cursor:'pointer',fontFamily:'var(--f-body)'}}>Limpiar filtros</button>
    </div>
  );
}

/* ── Bento Grid ── */
function BentoGrid({ editions, navigate, isMobile }) {
  if(isMobile){
    return (
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--s4)',padding:'var(--s4)'}}>
        {editions.map((e,i)=><MangaCard key={e.id} edition={e} size="sm" shineIndex={i} isMobile onClick={()=>navigate('detail',{productId:e.id})}/>)}
      </div>
    );
  }
  return (
    <div style={{padding:'var(--s6)'}}>
      <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',gap:'var(--s7)'}}>
        {editions.map((e,i)=><MangaCard key={e.id} edition={e} size="md" shineIndex={i} onClick={()=>navigate('detail',{productId:e.id})}/>)}
      </div>
    </div>
  );
}

/* ── Content Header ── */
function ContentHeader({ count, sort, onSort, filters }) {
  const n=filters.types.length+filters.countries.length+(filters.rarityTier?1:0)+(filters.limitedStock?1:0)+(filters.minScore>0?1:0);
  return (
    <div style={{display:'flex',alignItems:'center',gap:'var(--s4)',padding:'var(--s4) var(--s6)',borderBottom:'1px solid var(--border)',background:'var(--bg)'}}>
      <div style={{fontSize:13,color:'var(--text-sec)',flex:1}}>
        <span style={{fontWeight:700,color:'var(--text)'}}>{count}</span> ediciones
        {n>0&&<span style={{marginLeft:8,fontSize:11,color:'var(--gold)',background:'var(--gold-dim)',border:'1px solid var(--gold)',padding:'1px 8px',borderRadius:'var(--r-full)',fontWeight:700}}>{n} filtros activos</span>}
      </div>
      <div style={{display:'flex',alignItems:'center',gap:'var(--s2)'}}>
        <span style={{fontSize:11,color:'var(--text-muted)'}}>Ordenar:</span>
        <select value={sort} onChange={e=>onSort(e.target.value)} style={{padding:'5px 10px',background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text)',fontSize:12,fontFamily:'var(--f-body)',cursor:'pointer',outline:'none'}}>
          {SORT_OPTIONS.map(o=><option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      </div>
    </div>
  );
}

/* ── Pagination ── */
function Pagination({ current, total, onChange }) {
  const pages=total<=7?Array.from({length:total},(_,i)=>i+1):[1,2,3,4,5,'…',total];
  return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'center',gap:'var(--s2)',padding:'var(--s8) var(--s6)',borderTop:'1px solid var(--border)'}}>
      <button onClick={()=>onChange(Math.max(1,current-1))} style={{padding:'7px 14px',background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text-sec)',cursor:'pointer',fontSize:12,fontFamily:'var(--f-body)'}}>← Anterior</button>
      {pages.map((p,i)=>(
        <button key={i} onClick={()=>typeof p==='number'&&onChange(p)} style={{
          width:34,height:34,background:p===current?'var(--gold)':p==='…'?'transparent':'var(--surface-2)',
          border:p===current?'none':'1px solid var(--border)',borderRadius:'var(--r-md)',
          color:p===current?'var(--gold-text)':p==='…'?'var(--text-muted)':'var(--text-sec)',
          cursor:p==='…'?'default':'pointer',fontSize:12,fontWeight:p===current?700:400,
          fontFamily:'var(--f-body)',boxShadow:p===current?'var(--sh-gold)':'none',
        }}>{p}</button>
      ))}
      <button onClick={()=>onChange(Math.min(total,current+1))} style={{padding:'7px 14px',background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text-sec)',cursor:'pointer',fontSize:12,fontFamily:'var(--f-body)'}}>Siguiente →</button>
    </div>
  );
}

/* ── Mobile Filter Sheet ── */
function MobileFilterSheet({ filters, onChange, onClose }) {
  return (
    <div style={{position:'absolute',inset:0,zIndex:200,background:'rgba(0,0,0,.6)',backdropFilter:'blur(4px)',display:'flex',flexDirection:'column',justifyContent:'flex-end'}} onClick={onClose}>
      <div onClick={e=>e.stopPropagation()} style={{background:'var(--surface)',borderRadius:'var(--r-2xl) var(--r-2xl) 0 0',padding:'var(--s6) var(--s5) var(--s8)',maxHeight:'82%',overflowY:'auto'}}>
        <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'var(--s5)'}}>
          <div style={{fontFamily:'var(--f-display)',fontSize:18,fontWeight:700,color:'var(--text)'}}>Filtros</div>
          <button onClick={onClose} style={{width:28,height:28,borderRadius:'50%',border:'none',background:'var(--surface-2)',color:'var(--text-sec)',cursor:'pointer',fontSize:14}}>✕</button>
        </div>

        <div style={{fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)'}}>Tipo de edición</div>
        <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)',marginBottom:'var(--s5)'}}>
          {EDITION_TYPES.map(t=><Chip key={t.key} label={t.label} color={t.color} selected={filters.types.includes(t.key)}
            onClick={()=>onChange({...filters,types:filters.types.includes(t.key)?filters.types.filter(x=>x!==t.key):[...filters.types,t.key]})}/>)}
        </div>

        <div style={{fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)'}}>Rareza</div>
        <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)',marginBottom:'var(--s5)'}}>
          {RARITY_RADIO.map(opt=>(
            <div key={String(opt.value)} onClick={()=>onChange({...filters,rarityTier:opt.value})} style={{
              padding:'5px 11px',borderRadius:'var(--r-full)',fontSize:12,fontWeight:600,cursor:'pointer',
              border:`1px solid ${filters.rarityTier===opt.value?(opt.color||'var(--gold)'):'var(--border-md)'}`,
              background:filters.rarityTier===opt.value?(opt.color?opt.color+'22':'var(--gold-dim)'):'var(--surface-2)',
              color:filters.rarityTier===opt.value?(opt.color||'var(--gold)'):'var(--text-sec)',
            }}>{opt.label}</div>
          ))}
        </div>

        <div style={{fontSize:10,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:'var(--s3)'}}>País</div>
        <div style={{display:'flex',flexWrap:'wrap',gap:'var(--s2)',marginBottom:'var(--s5)'}}>
          {COUNTRIES.map(c=><Chip key={c.code} label={c.label} flag={c.code} selected={filters.countries.includes(c.code)}
            onClick={()=>onChange({...filters,countries:filters.countries.includes(c.code)?filters.countries.filter(x=>x!==c.code):[...filters.countries,c.code]})}/>)}
        </div>

        <label style={{display:'flex',alignItems:'center',gap:'var(--s3)',cursor:'pointer',marginBottom:'var(--s6)'}}>
          <Toggle on={filters.limitedStock} onClick={()=>onChange({...filters,limitedStock:!filters.limitedStock})}/>
          <span style={{fontSize:13,color:'var(--text-sec)'}}>Solo stock limitado</span>
        </label>

        <div style={{display:'flex',gap:'var(--s3)'}}>
          <button onClick={()=>onChange(defaultFilters())} style={{flex:1,padding:'10px',borderRadius:'var(--r-md)',background:'var(--surface-2)',border:'1px solid var(--border-md)',color:'var(--text-sec)',fontSize:13,fontWeight:600,cursor:'pointer',fontFamily:'var(--f-body)'}}>Limpiar</button>
          <button onClick={onClose} style={{flex:2,padding:'10px',borderRadius:'var(--r-md)',background:'var(--gold)',border:'none',color:'var(--gold-text)',fontSize:13,fontWeight:700,cursor:'pointer',fontFamily:'var(--f-body)'}}>Ver resultados</button>
        </div>
      </div>
    </div>
  );
}

/* ═══ CATALOG SCREEN ═══ */
function CatalogScreen({ navigate, isMobile }) {
  const [filters, setFilters] = React.useState(defaultFilters());
  const [sort, setSort] = React.useState('score');
  const [page, setPage] = React.useState(1);
  const [showSheet, setShowSheet] = React.useState(false);
  const filtered = useFilteredEditions(filters, sort);

  if(isMobile){
    const activeFiltersCount=filters.types.length+filters.countries.length+(filters.rarityTier?1:0)+(filters.limitedStock?1:0);
    return (
      <div style={{position:'relative',minHeight:'100%'}}>
        <div style={{padding:'var(--s3) var(--s4)',borderBottom:'1px solid var(--border)'}}>
          <div style={{position:'relative',marginBottom:'var(--s3)'}}>
            <span style={{position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',fontSize:13,color:'var(--text-muted)',pointerEvents:'none'}}>🔍</span>
            <input value={filters.search} onChange={e=>setFilters(f=>({...f,search:e.target.value}))} placeholder="Buscar edición..."
              style={{width:'100%',paddingLeft:32,paddingRight:12,paddingTop:9,paddingBottom:9,background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-full)',color:'var(--text)',fontSize:12,fontFamily:'var(--f-body)',outline:'none'}}/>
          </div>
          <div style={{display:'flex',gap:'var(--s2)',justifyContent:'space-between',alignItems:'center'}}>
            <button onClick={()=>setShowSheet(true)} style={{display:'flex',alignItems:'center',gap:6,padding:'7px 14px',background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-full)',color:'var(--text-sec)',fontSize:12,fontWeight:600,cursor:'pointer',fontFamily:'var(--f-body)'}}>
              🎛 Filtros
              {activeFiltersCount>0&&<span style={{background:'var(--gold)',color:'var(--gold-text)',borderRadius:'var(--r-full)',width:16,height:16,display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,fontWeight:800}}>{activeFiltersCount}</span>}
            </button>
            <select value={sort} onChange={e=>setSort(e.target.value)} style={{padding:'7px 10px',background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-full)',color:'var(--text)',fontSize:11,fontFamily:'var(--f-body)',outline:'none'}}>
              {SORT_OPTIONS.map(o=><option key={o.key} value={o.key}>{o.label}</option>)}
            </select>
          </div>
        </div>

        {/* Mobile discovery strip */}
        <div style={{background:'var(--surface-2)',borderBottom:'1px solid var(--border)',padding:'var(--s3) 0'}}>
          <div style={{padding:'0 var(--s4) var(--s2)',fontSize:11,fontWeight:700,color:'var(--text)',display:'flex',alignItems:'center',gap:'var(--s2)'}}>
            🔍 Nuevos hallazgos
            <span style={{fontSize:8,background:'var(--danger-dim)',color:'var(--danger)',border:'1px solid var(--danger)',borderRadius:'var(--r-full)',padding:'1px 6px',fontWeight:800,textTransform:'uppercase'}}>{NEW_DETECTIONS.length} · 24h</span>
          </div>
          <div style={{display:'flex',gap:'var(--s3)',paddingLeft:'var(--s4)',overflowX:'auto',scrollbarWidth:'none',paddingBottom:'var(--s1)'}}>
            {NEW_DETECTIONS.map((e,i)=>(
              <div key={e.id} onClick={()=>navigate('detail',{productId:e.id})} style={{flexShrink:0,width:86,cursor:'pointer'}}>
                <div style={{height:112,borderRadius:'var(--r-md)',overflow:'hidden',position:'relative',
                  background:COVER_TINTS[e.formatTypes[0]]||'var(--surface-3)',
                  display:'flex',alignItems:'flex-end',justifyContent:'center',paddingBottom:4}}>
                  <span style={{fontSize:7,color:'rgba(255,255,255,.2)',position:'relative',zIndex:2}}>{e.title.slice(0,12)}</span>
                  {e.rarityTier&&<div className={RARITY_META[e.rarityTier].coverClass} style={{zIndex:1}}/>}
                </div>
                <div style={{fontSize:8,fontWeight:600,color:'var(--text)',marginTop:3,lineHeight:1.3,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{e.title}</div>
              </div>
            ))}
          </div>
        </div>

        <div style={{padding:'var(--s4)'}}>
          <div style={{fontSize:11,color:'var(--text-muted)',marginBottom:'var(--s3)'}}>
            <span style={{fontWeight:700,color:'var(--text)'}}>{filtered.length}</span> ediciones
          </div>
          {filtered.length===0
            ? <EmptyState filters={filters} onReset={()=>setFilters(defaultFilters())}/>
            : <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'var(--s4)'}}>
                {filtered.map((e,i)=><MangaCard key={e.id} edition={e} size="sm" shineIndex={i} isMobile onClick={()=>navigate('detail',{productId:e.id})}/>)}
              </div>
          }
        </div>
        {showSheet&&<MobileFilterSheet filters={filters} onChange={setFilters} onClose={()=>setShowSheet(false)}/>}
      </div>
    );
  }

  /* ── Desktop ── */
  return (
    <div className="pw-body">
      <FilterSidebar filters={filters} onChange={setFilters}/>
      <div className="pw-main">
        <DiscoveryStrip navigate={navigate}/>
        <ContentHeader count={filtered.length} sort={sort} onSort={setSort} filters={filters}/>
        {filtered.length===0
          ? <EmptyState filters={filters} onReset={()=>setFilters(defaultFilters())}/>
          : <BentoGrid editions={filtered} navigate={navigate} isMobile={false}/>
        }
        <Pagination current={page} total={Math.max(1,Math.ceil(filtered.length/20))} onChange={setPage}/>
      </div>
    </div>
  );
}

Object.assign(window, { CatalogScreen, defaultFilters, SbLabel, Toggle });
