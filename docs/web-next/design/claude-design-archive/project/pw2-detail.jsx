/* ═══════════════════════════════════════════
   PW2-DETAIL.JSX — v2 Edition (A2) + Detail (A3)
   + ProximamenteScreen for future tabs
═══════════════════════════════════════════ */

/* ── Adaptive grid columns by volume count ── */
function gridCols(n) {
  if (n<=3)  return Math.max(1,n);
  if (n<=6)  return 3;
  if (n<=12) return 4;
  if (n<=20) return 5;
  return 8;
}

/* ── Volume list with gap placeholders ── */
function getVolumes(editionId) {
  const ed = MOCK_EDITIONS.find(e=>e.id===editionId);
  if (!ed) return [];
  // Demo gaps for series with >8 vols: vols 3 and 9 are undetected
  const gapSet = ed.volumes > 8 ? new Set([3, 9]) : new Set();
  return Array.from({length:ed.volumes}, (_,i)=>{
    const vol = i+1;
    if (gapSet.has(vol)) return { vol, isGap:true };
    return {
      vol, isGap:false,
      title:`${ed.title} Vol. ${vol}`,
      title_original: ed.title_original ? `${ed.title_original} 第${vol}巻` : null,
      formatTypes: ed.formatTypes, rarityTier: ed.rarityTier,
      country: ed.country, publisher: ed.publisher, price: ed.price,
      stock_type: vol===5?'limited':vol===8?'unavailable':'available',
      score: ed.score,
    };
  });
}

/* ── Source rows for detail view ── */
function getSources(productId) {
  const sources = [
    { name:'Mandarake',       country:'JP', lang:'JP', price:'¥2,948',  fee:'Envío desde $6',      stock:'available',   isCheapest:true  },
    { name:'Amazon JP',       country:'JP', lang:'JP', price:'¥3,200',  fee:'Envío gratis',         stock:'available',   isCheapest:false },
    { name:'CDJapan',         country:'JP', lang:'JP', price:'¥3,424',  fee:'Envío desde $4',       stock:'low',         isCheapest:false },
    { name:'Book Depository', country:'UK', lang:'EN', price:'$41.50',  fee:'Envío gratis mundial', stock:'available',   isCheapest:false },
    { name:'Amazon FR',       country:'FR', lang:'FR', price:'42,90 €', fee:'Envío desde 3 €',      stock:'unavailable', isCheapest:false },
  ];
  return sources;
}

/* ── Back button ── */
function BackBtn({ onClick, label='Volver' }) {
  return (
    <button onClick={onClick} style={{
      display:'flex',alignItems:'center',gap:6,
      padding:'7px 14px',background:'var(--surface-2)',
      border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',
      color:'var(--text-sec)',fontSize:12,fontWeight:600,
      cursor:'pointer',fontFamily:'var(--f-body)',transition:'color .12s',
    }}
    onMouseEnter={e=>e.currentTarget.style.color='var(--text)'}
    onMouseLeave={e=>e.currentTarget.style.color='var(--text-sec)'}>
      ← {label}
    </button>
  );
}

/* ── Collection progress block ── */
function CollectionProgress({ owned, total }) {
  const pct = total>0?Math.round((owned/total)*100):0;
  return (
    <div style={{padding:'var(--s4) var(--s5)',background:'var(--surface-2)',border:'1px solid var(--border)',borderRadius:'var(--r-lg)'}}>
      <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'var(--s3)'}}>
        <div style={{fontSize:12,fontWeight:700,color:'var(--text)'}}>Completá tu set</div>
        <div style={{display:'flex',alignItems:'center',gap:6}}>
          <span style={{fontSize:12,fontWeight:700,color:'var(--gold)'}}>{owned}</span>
          <span style={{fontSize:11,color:'var(--text-muted)'}}>de {total}</span>
          <ProximamenteBadge/>
        </div>
      </div>
      <div style={{height:6,background:'var(--surface-3)',borderRadius:'var(--r-full)',overflow:'hidden'}}>
        <div style={{height:'100%',width:pct+'%',borderRadius:'var(--r-full)',
          background:pct===100?'var(--success)':'var(--gold)',
          transition:'width .6s cubic-bezier(.34,1.56,.64,1)',
          boxShadow:pct>0?'0 0 8px var(--gold-glow)':'none'}}/>
      </div>
      <div style={{fontSize:10,color:'var(--text-muted)',marginTop:'var(--s2)'}}>{total-owned} tomos faltantes · {pct}% completado</div>
    </div>
  );
}

/* ── Stock badge ── */
function StockBadge({ stock }) {
  const map = {
    available:   { bg:'var(--success-dim)',              color:'var(--success)',     label:'En stock',   dot:true  },
    low:         { bg:'rgba(245,160,40,.14)',             color:'var(--warning)',     label:'Stock bajo', dot:true  },
    unavailable: { bg:'var(--surface-3)',                 color:'var(--text-muted)', label:'Agotado',    dot:false },
    preorder:    { bg:'var(--indigo-dim)',                color:'var(--indigo)',      label:'Pre-orden',  dot:false },
  };
  const s=map[stock]||map.available;
  return (
    <div style={{display:'inline-flex',alignItems:'center',gap:4,padding:'2px 8px',borderRadius:'var(--r-full)',
      fontSize:10,fontWeight:700,background:s.bg,color:s.color,border:`1px solid ${s.color}40`}}>
      {s.dot&&<div style={{width:5,height:5,borderRadius:'50%',background:s.color}}/>}
      {s.label}
    </div>
  );
}

/* ── Print run badge (for Super Rare / Ultra Rare) ── */
function PrintRunBadge({ printRun }) {
  if (!printRun) return null;
  return (
    <div style={{display:'inline-flex',alignItems:'center',gap:8,padding:'6px 14px',
      background:'var(--gold-dim)',border:'1px solid var(--gold)',borderRadius:'var(--r-md)'}}>
      <div style={{fontSize:9,fontWeight:800,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--gold)'}}>Print run</div>
      <div style={{fontSize:13,fontWeight:800,color:'var(--text)'}}>{printRun.toLocaleString()} (numerado)</div>
    </div>
  );
}

/* ── Próximamente placeholder screens ── */
const PROX_SCREENS = {
  calendar: {
    icon:'📅', title:'Calendario de lanzamientos',
    desc:'Seguí los lanzamientos confirmados y fechas de preventa de ediciones especiales en los países que rastreás.',
    features:['Vista mensual de pre-órdenes activas y fechas confirmadas','Alertas automáticas 7 días antes del lanzamiento','Sincronización con tu lista de seguimiento y alertas de precio'],
  },
  collection: {
    icon:'📚', title:'Mi colección',
    desc:'Registrá los tomos que tenés, seguí tu progreso por serie y recibí sugerencias de las piezas que faltan.',
    features:['Inventario por serie y tomo con estado de adquisición','Progreso visual de completitud y valor estimado de mercado','Sugerencias de compra basadas en tu historial y wishlist'],
  },
  alerts: {
    icon:'🔔', title:'Sistema de alertas',
    desc:'Notificaciones inteligentes cuando bajan precios, hay reimpresiones o el panda encuentra algo nuevo para vos.',
    features:['Alerta cuando baja el precio de un ítem en tu lista','Notificaciones de stock bajo, reimpresiones y nuevos hallazgos','Alertas de nuevas detecciones en tus países y formatos favoritos'],
  },
};

function ProximamenteScreen({ type }) {
  const s = PROX_SCREENS[type]||PROX_SCREENS.calendar;
  return (
    <div style={{display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',
      minHeight:'calc(100vh - var(--nav-h))',padding:'var(--s10) var(--s8)',textAlign:'center'}}>
      {/* Panda illustration */}
      <div style={{marginBottom:'var(--s5)',opacity:.28}}>
        <PWLogo size={80}/>
      </div>
      <div style={{fontSize:40,marginBottom:'var(--s4)'}}>{s.icon}</div>
      <h2 style={{fontFamily:'var(--f-display)',fontSize:26,fontWeight:800,color:'var(--text)',
        letterSpacing:'-.025em',marginBottom:'var(--s3)',lineHeight:1.1}}>{s.title}</h2>
      <p style={{fontSize:14,color:'var(--text-sec)',maxWidth:400,lineHeight:1.75,marginBottom:'var(--s7)',
        fontFamily:'var(--f-body)'}}>{s.desc}</p>

      <div style={{display:'flex',flexDirection:'column',gap:'var(--s3)',alignItems:'flex-start',
        background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--r-xl)',
        padding:'var(--s5) var(--s6)',maxWidth:400,width:'100%',marginBottom:'var(--s7)',
        boxShadow:'var(--sh-sm)'}}>
        {s.features.map((f,i)=>(
          <div key={i} style={{display:'flex',alignItems:'flex-start',gap:'var(--s3)'}}>
            <div style={{width:18,height:18,borderRadius:'50%',background:'var(--indigo-dim)',
              border:'1px solid var(--indigo)',display:'flex',alignItems:'center',justifyContent:'center',
              flexShrink:0,marginTop:2}}>
              <div style={{width:5,height:5,borderRadius:'50%',background:'var(--indigo)'}}/>
            </div>
            <span style={{fontSize:13,color:'var(--text-sec)',lineHeight:1.6,fontFamily:'var(--f-body)',textAlign:'left'}}>{f}</span>
          </div>
        ))}
      </div>

      <div style={{display:'inline-flex',alignItems:'center',gap:'var(--s3)',
        padding:'var(--s3) var(--s5)',background:'var(--indigo-dim)',
        border:'1px solid var(--indigo)',borderRadius:'var(--r-full)'}}>
        <ProximamenteBadge/>
        <span style={{fontSize:12,color:'var(--text-sec)',fontFamily:'var(--f-body)'}}>Esta sección estará disponible pronto</span>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   A2 — EDITION VIEW
═══════════════════════════════════════════ */
function EditionScreen({ navigate, editionId, isMobile }) {
  const ed = MOCK_EDITIONS.find(e=>e.id===editionId)||MOCK_EDITIONS[0];
  const volumes = getVolumes(ed.id);
  const rm = RARITY_META[ed.rarityTier];
  const [ownedCount] = React.useState(3);
  const cols = gridCols(ed.volumes);

  const CoverArea = ({ h, radius='var(--r-xl)' }) => (
    <div style={{
      height:h, width:isMobile?'100%':220, position:'relative', overflow:'hidden',
      borderRadius:radius, flexShrink:0,
      background: rm?.shinePeak===.85 ? 'linear-gradient(160deg,#0a0020,#060818,#140028)' :
        (COVER_TINTS[ed.formatTypes[0]]||'repeating-linear-gradient(45deg,var(--surface-2),var(--surface-2) 3px,var(--surface-3) 3px,var(--surface-3) 6px)'),
      boxShadow: isMobile?'none':'var(--sh-lg)',
      border: rm ? `1.5px solid ${rm.cardBorder}` : undefined,
      display:'flex', alignItems:'flex-end', justifyContent:'center', paddingBottom:10,
    }}>
      <span style={{fontSize:10,color:'rgba(255,255,255,.22)',position:'relative',zIndex:2,
        fontFamily:isCJK(ed.title_original)?'var(--f-cjk)':'var(--f-body)'}}>
        {ed.title_original||ed.title}
      </span>
      {rm&&<div className={rm.coverClass} style={{borderRadius:radius}}/>}
      {rm&&<div className="cover-shine-beam"/>}
    </div>
  );

  if (isMobile) {
    return (
      <div>
        <div style={{position:'relative',background:'var(--surface-2)'}}>
          <CoverArea h={260} radius="0"/>
          <div style={{position:'absolute',bottom:0,left:0,right:0,height:80,
            background:'linear-gradient(transparent,var(--bg))',pointerEvents:'none'}}/>
          <div style={{position:'absolute',top:'var(--s4)',left:'var(--s4)'}}>
            <BackBtn onClick={()=>navigate('catalog')} label=""/>
          </div>
        </div>
        <div style={{padding:'var(--s5) var(--s4)'}}>
          {ed.title_original&&<div style={{fontFamily:isCJK(ed.title_original)?'var(--f-cjk)':'var(--f-body)',fontSize:12,color:'var(--text-muted)',marginBottom:4}}>{ed.title_original}</div>}
          <div style={{fontFamily:'var(--f-display)',fontSize:20,fontWeight:800,color:'var(--text)',letterSpacing:'-.02em',marginBottom:'var(--s3)'}}>{ed.title}</div>
          <div style={{display:'flex',gap:'var(--s2)',flexWrap:'wrap',marginBottom:'var(--s4)'}}>
            {ed.formatTypes.map(f=><FormatBadge key={f} type={f}/>)}
            {rm&&<RarityBadge tier={ed.rarityTier}/>}
          </div>
          {ed.printRun&&<div style={{marginBottom:'var(--s4)'}}><PrintRunBadge printRun={ed.printRun}/></div>}
          <CollectionProgress owned={ownedCount} total={ed.volumes}/>
        </div>
        <div style={{padding:'0 var(--s4) var(--s7)'}}>
          <div style={{fontSize:12,fontWeight:700,color:'var(--text)',marginBottom:'var(--s4)'}}>
            {ed.volumes} tomos
          </div>
          <div style={{display:'grid',gridTemplateColumns:`repeat(${Math.min(cols,3)},1fr)`,gap:'var(--s3)'}}>
            {volumes.slice(0,12).map(v=>(
              v.isGap
                ? <div key={v.vol} style={{background:'var(--surface-2)',border:'2px dashed var(--border-md)',borderRadius:'var(--r-md)',display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',height:80,opacity:.55,cursor:'default'}}>
                    <div style={{fontSize:14,marginBottom:2}}>?</div>
                    <div style={{fontSize:8,color:'var(--text-muted)',textAlign:'center',lineHeight:1.3}}>Vol. {v.vol}<br/>no detectado</div>
                  </div>
                : <div key={v.vol} onClick={()=>navigate('detail',{productId:ed.id})}
                    style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--r-md)',overflow:'hidden',cursor:'pointer',opacity:v.stock_type==='unavailable'?.45:1}}>
                    <div style={{height:80,background:COVER_TINTS[v.formatTypes[0]]||'var(--surface-3)',
                      position:'relative',display:'flex',alignItems:'flex-end',justifyContent:'center',paddingBottom:3}}>
                      <span style={{fontSize:7,color:'rgba(255,255,255,.22)',position:'relative',zIndex:2}}>Vol.{v.vol}</span>
                      {v.rarityTier&&<div className={RARITY_META[v.rarityTier].coverClass}/>}
                    </div>
                    <div style={{padding:'3px 6px 5px',fontSize:8,fontWeight:600,color:'var(--text-sec)',textAlign:'center'}}>Vol. {v.vol}</div>
                  </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  /* ── Desktop Edition ── */
  return (
    <div style={{padding:'var(--s7) var(--s9)'}}>
      <div style={{marginBottom:'var(--s6)'}}><BackBtn onClick={()=>navigate('catalog')}/></div>

      <div style={{display:'flex',gap:'var(--s8)',marginBottom:'var(--s9)',alignItems:'flex-start'}}>
        <CoverArea h={300}/>
        <div style={{flex:1}}>
          {ed.title_original&&(
            <div style={{fontFamily:isCJK(ed.title_original)?'var(--f-cjk)':'var(--f-body)',fontSize:16,color:'var(--text-muted)',marginBottom:'var(--s2)',lineHeight:1.4}}>{ed.title_original}</div>
          )}
          <h1 style={{fontFamily:'var(--f-display)',fontSize:34,fontWeight:800,color:'var(--text)',letterSpacing:'-.03em',lineHeight:1.05,marginBottom:'var(--s4)'}}>{ed.title}</h1>

          <div style={{display:'flex',gap:'var(--s2)',flexWrap:'wrap',alignItems:'center',marginBottom:'var(--s5)'}}>
            {ed.formatTypes.map(f=><FormatBadge key={f} type={f} size="md"/>)}
            {rm&&<RarityBadge tier={ed.rarityTier} size="md"/>}
            <div style={{display:'inline-flex',alignItems:'center',gap:6,padding:'4px 12px',borderRadius:'var(--r-full)',fontSize:11,background:'var(--surface-2)',border:'1px solid var(--border-md)',color:'var(--text-sec)'}}>
              <Flag code={ed.country} size={13}/> {ed.country} · {ed.publisher}
            </div>
            <div style={{padding:'4px 12px',borderRadius:'var(--r-full)',fontSize:11,fontWeight:700,background:'var(--success-dim)',color:'var(--success)',border:'1px solid var(--success)'}}>Score {ed.score}</div>
          </div>

          {ed.printRun&&<div style={{marginBottom:'var(--s5)'}}><PrintRunBadge printRun={ed.printRun}/></div>}

          <div style={{display:'grid',gridTemplateColumns:'repeat(3,auto)',gap:'var(--s4) var(--s7)',marginBottom:'var(--s5)',width:'fit-content'}}>
            {[['Tomos',ed.volumes],['Desde',ed.price||'—'],['Editorial',ed.publisher]].map(([k,v])=>(
              <div key={k}>
                <div style={{fontSize:9,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:2}}>{k}</div>
                <div style={{fontSize:14,fontWeight:600,color:'var(--text)'}}>{v}</div>
              </div>
            ))}
          </div>

          <div style={{maxWidth:440,marginBottom:'var(--s5)'}}><CollectionProgress owned={ownedCount} total={ed.volumes}/></div>

          <button style={{padding:'9px 20px',borderRadius:'var(--r-md)',background:'var(--indigo-dim)',border:'1px solid var(--indigo)',color:'var(--indigo)',fontSize:13,fontWeight:600,cursor:'pointer',fontFamily:'var(--f-body)',display:'flex',alignItems:'center',gap:8}}>
            + Seguir serie <ProximamenteBadge/>
          </button>
        </div>
      </div>

      {/* Volumes grid */}
      <div style={{borderTop:'1px solid var(--border)',paddingTop:'var(--s7)'}}>
        <div style={{fontFamily:'var(--f-display)',fontSize:22,fontWeight:700,color:'var(--text)',letterSpacing:'-.02em',marginBottom:'var(--s5)'}}>
          {ed.volumes} tomos
          {volumes.filter(v=>v.isGap).length>0&&(
            <span style={{marginLeft:10,fontSize:12,fontWeight:500,color:'var(--text-muted)'}}>
              · {volumes.filter(v=>v.isGap).length} no detectado{volumes.filter(v=>v.isGap).length>1?'s':''}
            </span>
          )}
        </div>
        <div style={{display:'grid',gridTemplateColumns:`repeat(${cols},1fr)`,gap:'var(--s4)'}}>
          {volumes.map(v=>(
            v.isGap
              ? <div key={v.vol} style={{background:'var(--surface-2)',border:'2px dashed var(--border-md)',borderRadius:'var(--r-md)',display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center',height:120,opacity:.5,cursor:'default'}}>
                  <div style={{fontSize:18,marginBottom:4,color:'var(--text-muted)'}}>?</div>
                  <div style={{fontSize:9,color:'var(--text-muted)',textAlign:'center',lineHeight:1.4}}>Vol. {v.vol}<br/>no detectado</div>
                </div>
              : <div key={v.vol} onClick={()=>navigate('detail',{productId:ed.id})}
                  style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--r-md)',overflow:'hidden',cursor:'pointer',opacity:v.stock_type==='unavailable'?.45:1,transition:'all .15s',position:'relative'}}
                  onMouseEnter={e=>{e.currentTarget.style.borderColor='var(--border-md)';e.currentTarget.style.transform='translateY(-2px)';e.currentTarget.style.boxShadow='var(--sh-md)';}}
                  onMouseLeave={e=>{e.currentTarget.style.borderColor='var(--border)';e.currentTarget.style.transform='';e.currentTarget.style.boxShadow='';}}>
                  <div style={{height:100,position:'relative',overflow:'hidden',background:COVER_TINTS[v.formatTypes[0]]||'var(--surface-3)',display:'flex',alignItems:'flex-end',justifyContent:'center',paddingBottom:3}}>
                    <span style={{fontSize:8,color:'rgba(255,255,255,.22)',position:'relative',zIndex:2}}>Vol.{v.vol}</span>
                    {v.rarityTier&&<div className={RARITY_META[v.rarityTier].coverClass}/>}
                  </div>
                  <div style={{padding:'5px 7px 7px'}}>
                    <div style={{fontSize:9,fontWeight:700,color:'var(--text-sec)',marginBottom:2}}>Vol. {v.vol}</div>
                    {v.stock_type==='low'&&<div style={{fontSize:7,color:'var(--warning)',fontWeight:700}}>🔥 Pocas</div>}
                    {v.stock_type==='unavailable'&&<div style={{fontSize:7,color:'var(--text-muted)',fontWeight:700}}>Agotado</div>}
                  </div>
                  {v.vol<=ownedCount&&<div style={{position:'absolute',top:4,right:4,width:16,height:16,borderRadius:'50%',background:'var(--success)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:9,color:'#fff',fontWeight:800}}>✓</div>}
                </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════
   A3 — DETAIL VIEW
═══════════════════════════════════════════ */
function DetailScreen({ navigate, productId, isMobile }) {
  const ed = MOCK_EDITIONS.find(e=>e.id===productId)||MOCK_EDITIONS[0];
  const sources = getSources(ed.id);
  const rm = RARITY_META[ed.rarityTier];
  const [showFeedback, setShowFeedback] = React.useState(false);
  const [feedbackText, setFeedbackText] = React.useState('');
  const [feedbackSent, setFeedbackSent] = React.useState(false);
  const [alertPrice, setAlertPrice] = React.useState('');
  const [showAlertModal, setShowAlertModal] = React.useState(false);
  const shineRef = React.useRef(null);

  /* Entry shine on load for detail cover */
  React.useEffect(()=>{
    const el=shineRef.current;
    if(!el||!ed.rarityTier) return;
    if(window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;
    setTimeout(()=>{
      el.style.setProperty('--shine-duration',rm.shineDuration.replace('.','.').replace('s','')+'s');
      el.style.setProperty('--shine-peak',rm.shinePeak);
      el.classList.add('shine-active');
      const done=()=>el.classList.remove('shine-active');
      el.addEventListener('animationend',done,{once:true});
      setTimeout(done,900);
    },400);
  },[ed.id]);

  /* Tilt on detail cover */
  const onCoverMove = React.useCallback((e)=>{
    const el=shineRef.current; if(!el) return;
    const r=el.getBoundingClientRect();
    const x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
    el.style.setProperty('--shine-x',x);
    el.style.setProperty('--shine-y',y);
    el.style.transform=`perspective(800px) rotateX(${-(y-.5)*6}deg) rotateY(${(x-.5)*6}deg) translateZ(6px)`;
  },[]);
  const onCoverLeave=React.useCallback(()=>{
    const el=shineRef.current; if(!el) return;
    el.style.transition='transform .5s cubic-bezier(.23,1,.32,1)';
    el.style.transform='';
    setTimeout(()=>{if(el)el.style.transition='';},500);
  },[]);
  const onCoverClick=React.useCallback(()=>{
    const el=shineRef.current; if(!el||!ed.rarityTier) return;
    if(window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;
    el.style.setProperty('--shine-duration',rm.shineDuration);
    el.style.setProperty('--shine-peak',rm.shinePeak);
    el.classList.add('shine-active');
    const done=()=>el.classList.remove('shine-active');
    el.addEventListener('animationend',done,{once:true});
    setTimeout(done,900);
  },[ed.rarityTier]);

  const CoverPanel = ({ h }) => (
    <div ref={shineRef} onMouseMove={onCoverMove} onMouseLeave={onCoverLeave} onClick={onCoverClick}
      style={{
        width:isMobile?'100%':220, height:h, flexShrink:0,
        borderRadius:isMobile?0:'var(--r-xl)', overflow:'hidden', position:'relative',
        background: rm?.shinePeak===.85 ? 'linear-gradient(160deg,#0a0020,#060818,#140028)' :
          (COVER_TINTS[ed.formatTypes[0]]||'repeating-linear-gradient(45deg,var(--surface-2),var(--surface-2) 3px,var(--surface-3) 3px,var(--surface-3) 6px)'),
        boxShadow: isMobile?'none':(rm?rm.cardShadow:'var(--sh-lg)'),
        border: !isMobile&&rm ? `1.5px solid ${rm.cardBorder}` : undefined,
        cursor:'pointer',
        display:'flex',alignItems:'flex-end',justifyContent:'center',paddingBottom:10,
      }}>
      <span style={{fontSize:10,color:'rgba(255,255,255,.22)',position:'relative',zIndex:2,
        fontFamily:isCJK(ed.title_original)?'var(--f-cjk)':'var(--f-body)'}}>{ed.title_original||ed.title}</span>
      {rm&&<div className={rm.coverClass}/>}
      {rm&&<div className="cover-shine-beam"/>}
    </div>
  );

  const SourceRow = ({ src }) => (
    <div style={{
      display:'grid',gridTemplateColumns:isMobile?'1fr auto':'180px 100px 1fr auto auto',
      gap:'var(--s4)',alignItems:'center',padding:'var(--s4) var(--s5)',
      background:src.isCheapest?'var(--gold-dim)':'transparent',
      borderBottom:'1px solid var(--border)',
      borderLeft:`3px solid ${src.isCheapest?'var(--gold)':'transparent'}`,
    }}>
      <div style={{display:'flex',alignItems:'center',gap:'var(--s3)'}}>
        {src.isCheapest&&<div style={{fontSize:9,fontWeight:800,color:'var(--gold)',background:'var(--gold-dim)',border:'1px solid var(--gold)',borderRadius:'var(--r-full)',padding:'1px 6px',letterSpacing:'.05em',textTransform:'uppercase',whiteSpace:'nowrap'}}>★ Mejor precio</div>}
        <Flag code={src.country} size={13}/>
        <div>
          <div style={{fontSize:13,fontWeight:600,color:'var(--text)'}}>{src.name}</div>
          {!isMobile&&<div style={{fontSize:10,color:'var(--text-muted)'}}>{src.fee}</div>}
        </div>
      </div>
      <div style={{fontSize:16,fontWeight:800,color:src.isCheapest?'var(--gold)':'var(--text)',letterSpacing:'-.01em'}}>{src.price}</div>
      {!isMobile&&<div><StockBadge stock={src.stock}/></div>}
      {!isMobile&&<div style={{fontSize:10,fontWeight:600,color:'var(--text-muted)',padding:'2px 8px',background:'var(--surface-2)',border:'1px solid var(--border)',borderRadius:'var(--r-full)'}}>{src.lang}</div>}
      <a href={src.url||'#'} style={{padding:isMobile?'6px 12px':'7px 16px',borderRadius:'var(--r-md)',fontSize:12,fontWeight:700,
        background:src.isCheapest?'var(--gold)':'var(--surface-2)',
        border:`1px solid ${src.isCheapest?'var(--gold)':'var(--border-md)'}`,
        color:src.isCheapest?'var(--gold-text)':'var(--text-sec)',
        cursor:'pointer',fontFamily:'var(--f-body)',whiteSpace:'nowrap',textDecoration:'none',display:'inline-block',
      }}>Ver →</a>
    </div>
  );

  if (isMobile) {
    return (
      <div style={{paddingBottom:80}}>
        <div style={{position:'relative'}}>
          <CoverPanel h={280}/>
          <div style={{position:'absolute',top:'var(--s4)',left:'var(--s4)'}}><BackBtn onClick={()=>navigate('catalog')} label=""/></div>
          <div style={{position:'absolute',bottom:0,left:0,right:0,height:80,background:'linear-gradient(transparent,var(--bg))',pointerEvents:'none'}}/>
        </div>
        <div style={{padding:'var(--s5) var(--s4)'}}>
          {ed.title_original&&<div style={{fontFamily:isCJK(ed.title_original)?'var(--f-cjk)':'var(--f-body)',fontSize:12,color:'var(--text-muted)',marginBottom:4}}>{ed.title_original}</div>}
          <div style={{fontFamily:'var(--f-display)',fontSize:22,fontWeight:800,color:'var(--text)',letterSpacing:'-.02em',marginBottom:'var(--s3)'}}>{ed.title} Vol. 1</div>
          <div style={{display:'flex',gap:'var(--s2)',flexWrap:'wrap',marginBottom:'var(--s4)'}}>
            {ed.formatTypes.map(f=><FormatBadge key={f} type={f} size="sm"/>)}
            {rm&&<RarityBadge tier={ed.rarityTier} size="sm"/>}
            <StockBadge stock={ed.stock_type}/>
          </div>
          {ed.printRun&&<div style={{marginBottom:'var(--s4)'}}><PrintRunBadge printRun={ed.printRun}/></div>}

          <div style={{background:'var(--surface-2)',border:'1px solid var(--border)',borderRadius:'var(--r-lg)',padding:'var(--s4)',marginBottom:'var(--s4)'}}>
            <div style={{fontSize:11,fontWeight:700,color:'var(--text)',marginBottom:'var(--s2)'}}>Mejor precio disponible</div>
            <div style={{fontSize:22,fontWeight:800,color:'var(--gold)',letterSpacing:'-.02em',marginBottom:'var(--s3)'}}>{sources[0]?.price}</div>
            <button onClick={()=>setShowAlertModal(true)} style={{width:'100%',padding:'10px',borderRadius:'var(--r-md)',background:'var(--gold-dim)',border:'1px solid var(--gold)',color:'var(--gold)',fontSize:13,fontWeight:700,cursor:'pointer',fontFamily:'var(--f-body)',display:'flex',alignItems:'center',justifyContent:'center',gap:6}}>
              🔔 Alertarme si baja de precio
            </button>
          </div>

          <div style={{fontFamily:'var(--f-display)',fontSize:16,fontWeight:700,color:'var(--text)',marginBottom:'var(--s4)'}}>📍 Dónde conseguirlo</div>
          <div style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--r-lg)',overflow:'hidden',marginBottom:'var(--s5)'}}>
            {sources.map((s,i)=><SourceRow key={i} src={s}/>)}
          </div>

          <button onClick={()=>setShowFeedback(!showFeedback)} style={{background:'none',border:'none',color:'var(--text-muted)',fontSize:11,cursor:'pointer',fontFamily:'var(--f-body)',textDecoration:'underline'}}>
            ⚠ Reportar un problema
          </button>
        </div>
      </div>
    );
  }

  /* ── Desktop Detail ── */
  return (
    <div style={{padding:'var(--s7) var(--s9)'}}>
      <div style={{marginBottom:'var(--s6)',display:'flex',gap:'var(--s3)'}}>
        <BackBtn onClick={()=>navigate('catalog')}/>
        <BackBtn onClick={()=>navigate('edition',{editionId:ed.id})} label={`${ed.title} · ${ed.volumes} vols.`}/>
      </div>

      <div style={{display:'grid',gridTemplateColumns:'220px 1fr',gap:'var(--s9)',alignItems:'flex-start',marginBottom:'var(--s9)'}}>
        <div>
          <CoverPanel h={300}/>
          {rm&&<div style={{marginTop:'var(--s3)',fontSize:10,color:'var(--text-muted)',textAlign:'center',fontStyle:'italic'}}>Click para replay del shine</div>}
          <div style={{marginTop:'var(--s4)',display:'flex',alignItems:'center',gap:'var(--s3)'}}>
            <div style={{width:52,height:52,borderRadius:'var(--r-lg)',background:ed.score>=90?'var(--success-dim)':'var(--surface-2)',border:`2px solid ${ed.score>=90?'var(--success)':'var(--border-md)'}`,display:'flex',flexDirection:'column',alignItems:'center',justifyContent:'center'}}>
              <div style={{fontSize:20,fontWeight:800,color:ed.score>=90?'var(--success)':'var(--text)',lineHeight:1}}>{ed.score}</div>
              <div style={{fontSize:7,color:'var(--text-muted)',fontWeight:700,letterSpacing:'.06em'}}>SCORE</div>
            </div>
            <div style={{fontSize:11,color:'var(--text-muted)',lineHeight:1.5}}>Basado en {Math.floor(Math.random()*80)+20} señales de múltiples fuentes</div>
          </div>
        </div>

        <div>
          {ed.title_original&&(
            <div style={{fontFamily:isCJK(ed.title_original)?'var(--f-cjk)':'var(--f-body)',fontSize:17,color:'var(--text-muted)',marginBottom:'var(--s2)',lineHeight:1.4}}>{ed.title_original} — 第1巻</div>
          )}
          <h1 style={{fontFamily:'var(--f-display)',fontSize:30,fontWeight:800,color:'var(--text)',letterSpacing:'-.03em',marginBottom:'var(--s4)',lineHeight:1.1}}>{ed.title} Vol. 1</h1>

          <div style={{display:'flex',gap:'var(--s2)',flexWrap:'wrap',marginBottom:'var(--s5)'}}>
            {ed.formatTypes.map(f=><FormatBadge key={f} type={f} size="md"/>)}
            {rm&&<RarityBadge tier={ed.rarityTier} size="md"/>}
            <div style={{display:'inline-flex',alignItems:'center',gap:6,padding:'4px 12px',borderRadius:'var(--r-full)',fontSize:11,background:'var(--surface-2)',border:'1px solid var(--border-md)',color:'var(--text-sec)'}}><Flag code={ed.country} size={13}/> {ed.country} · {ed.publisher}</div>
            <StockBadge stock={ed.stock_type}/>
          </div>

          {ed.printRun&&<div style={{marginBottom:'var(--s5)'}}><PrintRunBadge printRun={ed.printRun}/></div>}

          {/* Metadata grid */}
          <div style={{display:'grid',gridTemplateColumns:'repeat(4,auto)',gap:'var(--s4) var(--s7)',marginBottom:'var(--s6)',width:'fit-content'}}>
            {[['Tipo',FORMAT_META[ed.formatTypes[0]]?.label||'—'],['Editorial',ed.publisher],['País',ed.country],['Idioma',ed.country==='FR'?'Francés':ed.country==='JP'?'Japonés':'Inglés'],['Score',ed.score],['Tomos',ed.volumes],['Precio desde',ed.price||'—'],['ISBN','978-'+String(Math.random()).slice(2,12)]].map(([k,v])=>(
              <div key={k}>
                <div style={{fontSize:9,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:2}}>{k}</div>
                <div style={{fontSize:13,fontWeight:600,color:'var(--text)'}}>{v}</div>
              </div>
            ))}
          </div>

          {/* Price alert */}
          <div style={{padding:'var(--s4) var(--s5)',background:'var(--surface-2)',border:'1px solid var(--border)',borderRadius:'var(--r-lg)',display:'flex',alignItems:'center',gap:'var(--s5)',marginBottom:'var(--s6)'}}>
            <div>
              <div style={{fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:2}}>Alerta de precio</div>
              <div style={{fontSize:12,color:'var(--text-sec)'}}>Avisame si baja de</div>
            </div>
            <div style={{position:'relative'}}>
              <input type="text" value={alertPrice} onChange={e=>setAlertPrice(e.target.value)}
                placeholder="ej: ¥2,500"
                style={{padding:'7px 10px',background:'var(--surface)',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text)',fontSize:13,fontWeight:700,width:110,outline:'none',fontFamily:'var(--f-body)'}}/>
            </div>
            <button onClick={()=>setShowAlertModal(true)} style={{padding:'7px 16px',borderRadius:'var(--r-md)',background:'var(--gold-dim)',border:'1px solid var(--gold)',color:'var(--gold)',fontSize:12,fontWeight:700,cursor:'pointer',fontFamily:'var(--f-body)',display:'flex',alignItems:'center',gap:6}}>
              🔔 Crear alerta
            </button>
          </div>
        </div>
      </div>

      {/* Sources table */}
      <div style={{marginBottom:'var(--s8)'}}>
        <div style={{display:'flex',alignItems:'center',gap:'var(--s4)',marginBottom:'var(--s5)'}}>
          <h2 style={{fontFamily:'var(--f-display)',fontSize:24,fontWeight:700,color:'var(--text)',letterSpacing:'-.02em'}}>📍 Dónde conseguirlo</h2>
          <div style={{fontSize:11,color:'var(--text-muted)'}}>{sources.length} fuentes · Actualizado hace 2h</div>
        </div>
        <div style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--r-xl)',overflow:'hidden'}}>
          <div style={{display:'grid',gridTemplateColumns:'180px 100px 1fr auto auto',gap:'var(--s4)',padding:'var(--s3) var(--s5)',background:'var(--surface-2)',borderBottom:'1px solid var(--border)'}}>
            {['Fuente','Precio','Stock','Idioma',''].map((h,i)=>(
              <div key={i} style={{fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)'}}>{h}</div>
            ))}
          </div>
          {sources.map((s,i)=><SourceRow key={i} src={s}/>)}
        </div>
      </div>

      {/* Feedback */}
      <div style={{borderTop:'1px solid var(--border)',paddingTop:'var(--s6)'}}>
        {!showFeedback&&!feedbackSent&&(
          <button onClick={()=>setShowFeedback(true)} style={{background:'none',border:'none',color:'var(--text-muted)',fontSize:12,cursor:'pointer',fontFamily:'var(--f-body)',textDecoration:'underline',display:'flex',alignItems:'center',gap:4}}>
            ⚠ ¿Algo incorrecto? Reportar un problema
          </button>
        )}
        {showFeedback&&!feedbackSent&&(
          <div style={{background:'var(--surface-2)',border:'1px solid var(--border)',borderRadius:'var(--r-lg)',padding:'var(--s5)',maxWidth:500,animation:'fadeUp .2s ease'}}>
            <div style={{fontSize:12,fontWeight:700,color:'var(--text)',marginBottom:'var(--s2)'}}>¿Qué está mal?</div>
            <div style={{fontSize:11,color:'var(--text-muted)',marginBottom:'var(--s3)'}}>Describí el problema. Tu feedback se usa para curar el catálogo.</div>
            <textarea value={feedbackText} onChange={e=>setFeedbackText(e.target.value)} rows={3}
              placeholder="Ej: esta edición no es kanzenban, es una impresión regular. El tiraje debería ser 300, no 500..."
              style={{width:'100%',padding:'var(--s3)',background:'var(--surface)',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text)',fontSize:12,fontFamily:'var(--f-body)',resize:'vertical',outline:'none',lineHeight:1.5}}/>
            <div style={{display:'flex',gap:'var(--s3)',marginTop:'var(--s4)'}}>
              <button onClick={()=>setShowFeedback(false)} style={{padding:'7px 14px',background:'none',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text-muted)',fontSize:12,cursor:'pointer',fontFamily:'var(--f-body)'}}>Cancelar</button>
              <button onClick={()=>{if(feedbackText.trim()){setFeedbackSent(true);setShowFeedback(false);}}} style={{padding:'7px 16px',background:feedbackText.trim()?'var(--gold-dim)':'var(--surface-2)',border:`1px solid ${feedbackText.trim()?'var(--gold)':'var(--border)'}`,borderRadius:'var(--r-md)',color:feedbackText.trim()?'var(--gold)':'var(--text-muted)',fontSize:12,fontWeight:600,cursor:feedbackText.trim()?'pointer':'default',fontFamily:'var(--f-body)'}}>
                Enviar feedback 👎
              </button>
            </div>
          </div>
        )}
        {feedbackSent&&(
          <div style={{display:'flex',alignItems:'center',gap:'var(--s3)',animation:'fadeUp .2s ease'}}>
            <div style={{width:28,height:28,borderRadius:'50%',background:'var(--success-dim)',border:'1px solid var(--success)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:13,color:'var(--success)',fontWeight:800}}>✓</div>
            <div style={{fontSize:12,color:'var(--text-sec)'}}>Gracias — revisamos pronto.</div>
          </div>
        )}
      </div>

      {/* Price alert modal */}
      {showAlertModal&&(
        <div style={{position:'fixed',inset:0,zIndex:1000,background:'rgba(0,0,0,.65)',backdropFilter:'blur(4px)',display:'flex',alignItems:'center',justifyContent:'center'}} onClick={()=>setShowAlertModal(false)}>
          <div onClick={e=>e.stopPropagation()} style={{background:'var(--surface)',border:'1px solid var(--border)',borderRadius:'var(--r-2xl)',padding:'var(--s9)',maxWidth:360,width:'90%',textAlign:'center',boxShadow:'var(--sh-xl)'}}>
            <div style={{fontSize:44,marginBottom:'var(--s4)'}}>🔔</div>
            <h3 style={{fontFamily:'var(--f-display)',fontSize:22,fontWeight:800,color:'var(--text)',marginBottom:'var(--s3)',letterSpacing:'-.02em'}}>Alertas de precio</h3>
            <p style={{fontSize:13,color:'var(--text-muted)',lineHeight:1.7,marginBottom:'var(--s5)'}}>Te notificaremos cuando el precio baje del umbral que configuraste. Esta función llegará pronto.</p>
            <div style={{marginBottom:'var(--s6)'}}><ProximamenteBadge/></div>
            <button onClick={()=>setShowAlertModal(false)} style={{width:'100%',padding:'10px 24px',background:'var(--surface-2)',border:'1px solid var(--border-md)',borderRadius:'var(--r-md)',color:'var(--text-sec)',fontSize:13,fontWeight:600,cursor:'pointer',fontFamily:'var(--f-body)'}}>Entendido</button>
          </div>
        </div>
      )}
    </div>
  );
}

Object.assign(window, {
  EditionScreen, DetailScreen, ProximamenteScreen,
  getVolumes, getSources, BackBtn, CollectionProgress, StockBadge, PrintRunBadge,
});
