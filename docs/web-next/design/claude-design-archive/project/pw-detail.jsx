/* ═══════════════════════════════════════════
   PW-DETAIL.JSX — A2 Edition View + A3 Product Detail
═══════════════════════════════════════════ */

/* ── Mock volume data for edition view ── */
function getVolumes(editionId) {
  const ed = MOCK_EDITIONS.find(e => e.id === editionId);
  if (!ed) return [];
  return Array.from({ length: ed.volumes }, (_, i) => ({
    id: i + 1, vol: i + 1,
    title: `${ed.title} Vol. ${i + 1}`,
    titleJp: ed.titleJp ? `${ed.titleJp} 第${i + 1}巻` : null,
    type: ed.type, country: ed.country, publisher: ed.publisher,
    priceMin: ed.priceMin ? Math.round(ed.priceMin / ed.volumes * 1.1) : null,
    stock: i === 3 ? 'low' : i === 7 ? 'unavailable' : 'available',
    score: ed.score,
    isNew: false, spotlight: false,
  }));
}

/* ── Mock sources for product detail ── */
function getSources(productId) {
  const bases = [
    { name:'Amazon JP',       country:'JP', lang:'JP', badge:'Amazon',      fee:'Envío gratis',        markup: 1.00 },
    { name:'CDJapan',         country:'JP', lang:'JP', badge:'CDJapan',     fee:'Desde $4 de envío',   markup: 1.07 },
    { name:'Mandarake',       country:'JP', lang:'JP', badge:'Mandarake',   fee:'Desde $6 de envío',   markup: 0.92 },
    { name:'Book Depository', country:'UK', lang:'EN', badge:'BookDep.',    fee:'Envío gratis mundial', markup: 1.12 },
    { name:'Amazon FR',       country:'FR', lang:'FR', badge:'Amazon',      fee:'Desde €3 de envío',   markup: 1.18 },
    { name:'Fnac',            country:'FR', lang:'FR', badge:'Fnac',        fee:'Retiro en tienda',    markup: 1.22 },
    { name:'Amazon US',       country:'US', lang:'EN', badge:'Amazon',      fee:'Envío gratis Prime',  markup: 1.35 },
  ];
  const ed = MOCK_EDITIONS.find(e => e.id === productId);
  const base = ed?.priceMin || 30;
  return bases.slice(0, 5).map((s, i) => ({
    ...s,
    price: Math.round(base * s.markup),
    currency: s.country === 'JP' ? 'USD' : s.country === 'FR' ? 'EUR' : 'USD',
    stock: i === 2 ? 'low' : i === 4 ? 'unavailable' : 'available',
    url: '#',
    isCheapest: i === 0,
  })).sort((a, b) => a.price - b.price);
}

/* ── Back button ── */
function BackBtn({ onClick, label = 'Volver al catálogo' }) {
  return (
    <button onClick={onClick} style={{
      display:'flex', alignItems:'center', gap:6,
      padding:'7px 14px', background:'var(--surface-2)',
      border:'1px solid var(--border-md)', borderRadius:'var(--r-md)',
      color:'var(--text-sec)', fontSize:12, fontWeight:600,
      cursor:'pointer', fontFamily:'var(--f-body)',
      transition:'all .12s',
    }}
    onMouseEnter={e => { e.currentTarget.style.color='var(--text)'; }}
    onMouseLeave={e => { e.currentTarget.style.color='var(--text-sec)'; }}
    >
      ← {label}
    </button>
  );
}

/* ── Collection Progress (future feature placeholder) ── */
function CollectionProgress({ owned, total }) {
  const pct = total > 0 ? Math.round((owned / total) * 100) : 0;
  return (
    <div style={{
      padding:'var(--s4) var(--s5)', background:'var(--surface-2)',
      border:'1px solid var(--border)', borderRadius:'var(--r-lg)',
    }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:'var(--s3)' }}>
        <div style={{ fontSize:12, fontWeight:700, color:'var(--text)' }}>
          Completá tu set
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:6 }}>
          <span style={{ fontSize:12, fontWeight:700, color:'var(--gold)' }}>{owned}</span>
          <span style={{ fontSize:11, color:'var(--text-muted)' }}>de {total}</span>
          <span style={{
            fontSize:9, fontWeight:800, padding:'1px 7px',
            background:'var(--indigo-dim)', color:'var(--indigo)',
            border:'1px solid var(--indigo)', borderRadius:'var(--r-full)',
            letterSpacing:'.06em', textTransform:'uppercase',
          }}>Próximamente</span>
        </div>
      </div>
      <div style={{ height:6, background:'var(--surface-3)', borderRadius:'var(--r-full)', overflow:'hidden' }}>
        <div style={{
          height:'100%', width: pct + '%', borderRadius:'var(--r-full)',
          background: pct === 100 ? 'var(--success)' : 'var(--gold)',
          transition:'width .6s cubic-bezier(.34,1.56,.64,1)',
          boxShadow: pct > 0 ? '0 0 8px var(--gold-glow)' : 'none',
        }} />
      </div>
      <div style={{ fontSize:10, color:'var(--text-muted)', marginTop:'var(--s2)' }}>
        {total - owned} tomos faltantes — {pct}% completado
      </div>
    </div>
  );
}

/* ═══ A2 — EDITION VIEW ═══ */
function EditionScreen({ navigate, editionId, isMobile }) {
  const ed = MOCK_EDITIONS.find(e => e.id === editionId) || MOCK_EDITIONS[0];
  const volumes = getVolumes(ed.id);
  const [ownedCount] = React.useState(3);

  const CoverArea = ({ h }) => (
    <div className="cover-ph" style={{
      height: h, borderRadius:'var(--r-xl)', overflow:'hidden',
      background: ed.type === 'ultra' ? 'linear-gradient(160deg,#0a0020,#060818)' :
        ed.type === 'kanzenban' ? 'linear-gradient(160deg,#1a1400,#251d00)' :
        ed.type === 'variant' ? 'linear-gradient(160deg,#12002a,#0a0a32)' : undefined,
      boxShadow:'var(--sh-lg)',
      flexShrink:0,
    }}>
      <span style={{ fontSize:10, color:'rgba(255,255,255,.25)' }}>{ed.titleJp || ed.title}</span>
      {ed.type === 'kanzenban' && <div className="cover-foil-gold" />}
      {ed.type === 'variant'   && <div className="cover-foil-variant" />}
      {ed.type === 'ultra'     && <><div className="cover-foil-ultra" /><div className="cover-shine" /></>}
    </div>
  );

  if (isMobile) {
    return (
      <div>
        {/* Hero cover */}
        <div style={{ position:'relative', background:'var(--surface-2)' }}>
          <CoverArea h={260} />
          <div style={{
            position:'absolute', bottom:0, left:0, right:0,
            background:'linear-gradient(transparent, var(--bg))',
            height:80, pointerEvents:'none',
          }} />
          <div style={{ position:'absolute', top:'var(--s4)', left:'var(--s4)' }}>
            <BackBtn onClick={() => navigate('catalog')} label="" />
          </div>
        </div>

        {/* Info */}
        <div style={{ padding:'var(--s5) var(--s4)' }}>
          <div style={{ fontFamily:'var(--f-cjk)', fontSize:13, color:'var(--text-muted)', marginBottom:4 }}>{ed.titleJp}</div>
          <div style={{ fontFamily:'var(--f-display)', fontSize:20, fontWeight:800, color:'var(--text)', letterSpacing:'-0.02em', marginBottom:'var(--s3)' }}>
            {ed.title}
          </div>
          <div style={{ display:'flex', gap:'var(--s2)', flexWrap:'wrap', marginBottom:'var(--s4)' }}>
            <RarityBadge type={ed.type} size="sm" />
            <div style={{
              display:'inline-flex', alignItems:'center', gap:4,
              padding:'2px 8px', borderRadius:'var(--r-full)',
              fontSize:9, fontWeight:700, background:'var(--surface-2)',
              border:'1px solid var(--border-md)', color:'var(--text-sec)',
            }}>
              <Flag code={ed.country} size={12} /> {ed.country} · {ed.publisher}
            </div>
          </div>
          <CollectionProgress owned={ownedCount} total={ed.volumes} />
        </div>

        {/* Volumes grid */}
        <div style={{ padding:'0 var(--s4) var(--s7)' }}>
          <div style={{ fontSize:12, fontWeight:700, color:'var(--text)', marginBottom:'var(--s4)' }}>
            {ed.volumes} tomos
          </div>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:'var(--s3)' }}>
            {volumes.slice(0, 12).map(v => (
              <div key={v.id} onClick={() => navigate('detail', { productId: ed.id })}
                style={{
                  background:'var(--surface)', border:'1px solid var(--border)',
                  borderRadius:'var(--r-md)', overflow:'hidden', cursor:'pointer',
                  opacity: v.stock === 'unavailable' ? 0.5 : 1,
                }}>
                <div className="cover-ph" style={{
                  height:80, fontSize:7,
                  background: ed.type === 'kanzenban' ? 'linear-gradient(160deg,#1a1400,#251d00)' : undefined,
                }}>
                  <span style={{ color:'rgba(255,255,255,.2)', fontSize:7 }}>Vol.{v.vol}</span>
                  {ed.type === 'kanzenban' && <div className="cover-foil-gold" />}
                </div>
                <div style={{ padding:'4px 6px 6px', fontSize:9, fontWeight:600, color:'var(--text-muted)', textAlign:'center' }}>
                  Vol. {v.vol}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  /* DESKTOP */
  return (
    <div style={{ padding:'var(--s7) var(--s9)' }}>
      <div style={{ marginBottom:'var(--s6)' }}>
        <BackBtn onClick={() => navigate('catalog')} />
      </div>

      {/* Header */}
      <div style={{ display:'flex', gap:'var(--s8)', marginBottom:'var(--s9)', alignItems:'flex-start' }}>
        <CoverArea h={320} />
        <div style={{ flex:1 }}>
          {ed.titleJp && (
            <div style={{ fontFamily:'var(--f-cjk)', fontSize:16, color:'var(--text-muted)', marginBottom:'var(--s2)', lineHeight:1.4 }}>
              {ed.titleJp}
            </div>
          )}
          <h1 style={{
            fontFamily:'var(--f-display)', fontSize:36, fontWeight:800,
            color:'var(--text)', letterSpacing:'-0.03em', lineHeight:1.05, marginBottom:'var(--s4)',
          }}>{ed.title}</h1>

          <div style={{ display:'flex', gap:'var(--s3)', flexWrap:'wrap', alignItems:'center', marginBottom:'var(--s6)' }}>
            <RarityBadge type={ed.type} />
            <div style={{
              display:'inline-flex', alignItems:'center', gap:6,
              padding:'4px 12px', borderRadius:'var(--r-full)',
              fontSize:11, background:'var(--surface-2)',
              border:'1px solid var(--border-md)', color:'var(--text-sec)',
            }}>
              <Flag code={ed.country} size={14} />
              {ed.country} · {ed.publisher}
            </div>
            <div style={{
              padding:'4px 12px', borderRadius:'var(--r-full)',
              fontSize:11, fontWeight:700,
              background:'var(--success-dim)', color:'var(--success)',
              border:'1px solid var(--success)',
            }}>
              Score {ed.score}
            </div>
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'repeat(3, auto)', gap:'var(--s4) var(--s7)', marginBottom:'var(--s6)', width:'fit-content' }}>
            {[
              ['Tomos', ed.volumes],
              ['Desde', `$${ed.priceMin} USD`],
              ['Editorial', ed.publisher],
            ].map(([k,v]) => (
              <div key={k}>
                <div style={{ fontSize:10, fontWeight:700, letterSpacing:'.08em', textTransform:'uppercase', color:'var(--text-muted)', marginBottom:2 }}>{k}</div>
                <div style={{ fontSize:14, fontWeight:600, color:'var(--text)' }}>{v}</div>
              </div>
            ))}
          </div>

          <div style={{ maxWidth:440, marginBottom:'var(--s6)' }}>
            <CollectionProgress owned={ownedCount} total={ed.volumes} />
          </div>

          <div style={{ display:'flex', gap:'var(--s3)' }}>
            <button style={{
              padding:'9px 20px', borderRadius:'var(--r-md)',
              background:'var(--indigo-dim)', border:'1px solid var(--indigo)',
              color:'var(--indigo)', fontSize:13, fontWeight:600,
              cursor:'pointer', fontFamily:'var(--f-body)',
              display:'flex', alignItems:'center', gap:6,
            }}>
              + Seguir serie
              <span style={{ fontSize:9, background:'var(--indigo-dim)', border:'1px solid var(--indigo)',
                borderRadius:'var(--r-full)', padding:'1px 6px', letterSpacing:'.06em', textTransform:'uppercase' }}>
                Próximamente
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Volumes grid */}
      <div style={{ borderTop:'1px solid var(--border)', paddingTop:'var(--s7)' }}>
        <div style={{ fontFamily:'var(--f-display)', fontSize:22, fontWeight:700, color:'var(--text)', letterSpacing:'-0.02em', marginBottom:'var(--s5)' }}>
          {ed.volumes} tomos
        </div>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(8, 1fr)', gap:'var(--s4)' }}>
          {volumes.map(v => (
            <div key={v.id} onClick={() => navigate('detail', { productId: ed.id })}
              style={{
                background:'var(--surface)', border:'1px solid var(--border)',
                borderRadius:'var(--r-md)', overflow:'hidden', cursor:'pointer',
                opacity: v.stock === 'unavailable' ? 0.45 : 1,
                transition:'all .15s', position:'relative',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor='var(--border-md)'; e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='var(--sh-md)'; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor='var(--border)'; e.currentTarget.style.transform=''; e.currentTarget.style.boxShadow=''; }}
            >
              <div className="cover-ph" style={{
                height:100, fontSize:8,
                background: ed.type === 'kanzenban' ? 'linear-gradient(160deg,#1a1400,#251d00)' :
                  ed.type === 'ultra' ? 'linear-gradient(160deg,#0a0020,#060818)' : undefined,
              }}>
                <span style={{ color:'rgba(255,255,255,.22)', fontSize:8 }}>Vol.{v.vol}</span>
                {ed.type === 'kanzenban' && <div className="cover-foil-gold" />}
                {ed.type === 'ultra' && <><div className="cover-foil-ultra" /><div className="cover-shine" /></>}
              </div>
              <div style={{ padding:'5px 7px 7px' }}>
                <div style={{ fontSize:9, fontWeight:700, color:'var(--text-sec)', marginBottom:2 }}>Vol. {v.vol}</div>
                {v.stock === 'low' && <div style={{ fontSize:7, color:'var(--warning)', fontWeight:700 }}>🔥 Pocas</div>}
                {v.stock === 'unavailable' && <div style={{ fontSize:7, color:'var(--text-muted)', fontWeight:700 }}>Agotado</div>}
              </div>
              {v.vol <= ownedCount && (
                <div style={{
                  position:'absolute', top:4, right:4,
                  width:16, height:16, borderRadius:'50%',
                  background:'var(--success)', display:'flex',
                  alignItems:'center', justifyContent:'center',
                  fontSize:9, color:'#fff', fontWeight:800,
                }}>✓</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ═══ A3 — PRODUCT DETAIL ═══ */
function DetailScreen({ navigate, productId, isMobile }) {
  const ed = MOCK_EDITIONS.find(e => e.id === productId) || MOCK_EDITIONS[0];
  const sources = getSources(ed.id);
  const [showFeedback, setShowFeedback] = React.useState(false);
  const [feedbackSent, setFeedbackSent] = React.useState(false);
  const [priceAlert, setPriceAlert] = React.useState(false);
  const [alertPrice, setAlertPrice] = React.useState(Math.round(sources[0]?.price * 0.85));

  const stockBadge = (stock) => {
    const map = {
      available:   { bg:'var(--success-dim)', color:'var(--success)',  label:'En stock',   dot:true },
      low:         { bg:'rgba(245,160,40,.14)', color:'var(--warning)', label:'Stock bajo',  dot:true },
      unavailable: { bg:'var(--surface-3)',    color:'var(--text-muted)', label:'Agotado',   dot:false },
      preorder:    { bg:'var(--indigo-dim)',   color:'var(--indigo)',   label:'Pre-orden',  dot:false },
    };
    const s = map[stock] || map.available;
    return (
      <div style={{
        display:'inline-flex', alignItems:'center', gap:4,
        padding:'2px 8px', borderRadius:'var(--r-full)',
        fontSize:10, fontWeight:700, background:s.bg, color:s.color,
        border:`1px solid ${s.color}40`,
      }}>
        {s.dot && <div style={{ width:5,height:5,borderRadius:'50%',background:s.color }} />}
        {s.label}
      </div>
    );
  };

  const SourceRow = ({ src, isCheapest }) => (
    <div style={{
      display:'grid', gridTemplateColumns: isMobile ? '1fr auto' : '180px 100px 1fr auto auto',
      gap:'var(--s4)', alignItems:'center',
      padding:'var(--s4) var(--s5)',
      background: isCheapest ? 'var(--gold-dim)' : 'transparent',
      borderBottom:'1px solid var(--border)',
      borderLeft: isCheapest ? '3px solid var(--gold)' : '3px solid transparent',
      transition:'background .12s',
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:'var(--s3)' }}>
        {isCheapest && (
          <div style={{ fontSize:9,fontWeight:800,color:'var(--gold)',
            background:'var(--gold-dim)',border:'1px solid var(--gold)',
            borderRadius:'var(--r-full)',padding:'1px 6px',letterSpacing:'.06em',
            textTransform:'uppercase',whiteSpace:'nowrap' }}>★ Mejor precio</div>
        )}
        <Flag code={src.country} size={14} />
        <div>
          <div style={{ fontSize:13,fontWeight:600,color:'var(--text)' }}>{src.name}</div>
          {!isMobile && <div style={{ fontSize:10,color:'var(--text-muted)' }}>{src.fee}</div>}
        </div>
      </div>
      <div style={{ fontSize:16,fontWeight:800,color: isCheapest ? 'var(--gold)' : 'var(--text)',
        letterSpacing:'-0.01em' }}>
        ${src.price} <span style={{ fontSize:10,fontWeight:500,color:'var(--text-muted)' }}>USD</span>
      </div>
      {!isMobile && <div>{stockBadge(src.stock)}</div>}
      {!isMobile && (
        <div style={{ fontSize:10,fontWeight:600,color:'var(--text-muted)',
          padding:'2px 8px',background:'var(--surface-2)',
          border:'1px solid var(--border)',borderRadius:'var(--r-full)' }}>
          {src.lang}
        </div>
      )}
      <button style={{
        padding: isMobile ? '6px 12px' : '7px 16px',
        borderRadius:'var(--r-md)', fontSize:12, fontWeight:700,
        background: isCheapest ? 'var(--gold)' : 'var(--surface-2)',
        border:`1px solid ${isCheapest ? 'var(--gold)' : 'var(--border-md)'}`,
        color: isCheapest ? 'var(--gold-text)' : 'var(--text-sec)',
        cursor:'pointer', fontFamily:'var(--f-body)', whiteSpace:'nowrap',
      }}>
        Ver →
      </button>
    </div>
  );

  const CoverPanel = ({ h }) => (
    <div style={{ flexShrink:0 }}>
      <div className="cover-ph" style={{
        width: isMobile ? '100%' : 220, height: h,
        borderRadius: isMobile ? 0 : 'var(--r-xl)',
        boxShadow: isMobile ? 'none' : 'var(--sh-lg)',
        background: ed.type === 'ultra' ? 'linear-gradient(160deg,#0a0020,#060818)' :
          ed.type === 'kanzenban' ? 'linear-gradient(160deg,#1a1400,#251d00)' :
          ed.type === 'variant' ? 'linear-gradient(160deg,#12002a,#0a0a32)' : undefined,
      }}>
        <span style={{ fontSize:10, color:'rgba(255,255,255,.25)' }}>{ed.titleJp || ed.title}</span>
        {ed.type === 'kanzenban' && <div className="cover-foil-gold" />}
        {ed.type === 'variant'   && <div className="cover-foil-variant" />}
        {ed.type === 'ultra'     && <><div className="cover-foil-ultra" /><div className="cover-shine" /></>}
      </div>

      {/* Score */}
      {!isMobile && (
        <div style={{ marginTop:'var(--s4)', display:'flex', alignItems:'center', gap:'var(--s3)' }}>
          <div style={{
            width:56, height:56, borderRadius:'var(--r-lg)',
            background: ed.score >= 90 ? 'var(--success-dim)' : 'var(--surface-2)',
            border:`2px solid ${ed.score >= 90 ? 'var(--success)' : 'var(--border-md)'}`,
            display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center',
          }}>
            <div style={{ fontSize:22, fontWeight:800, color: ed.score >= 90 ? 'var(--success)' : 'var(--text)', lineHeight:1 }}>
              {ed.score}
            </div>
            <div style={{ fontSize:8, color:'var(--text-muted)', fontWeight:700, letterSpacing:'.06em' }}>SCORE</div>
          </div>
          <div style={{ fontSize:11, color:'var(--text-muted)', lineHeight:1.5 }}>
            Basado en {Math.floor(Math.random()*80)+20} señales de {Math.floor(Math.random()*6)+2} fuentes
          </div>
        </div>
      )}
    </div>
  );

  if (isMobile) {
    return (
      <div style={{ paddingBottom:80 }}>
        {/* Cover */}
        <div style={{ position:'relative' }}>
          <CoverPanel h={280} />
          <div style={{ position:'absolute', top:'var(--s4)', left:'var(--s4)' }}>
            <BackBtn onClick={() => navigate('catalog')} label="" />
          </div>
          <div style={{ position:'absolute', bottom:0, left:0, right:0, height:80,
            background:'linear-gradient(transparent,var(--bg))', pointerEvents:'none' }} />
        </div>

        <div style={{ padding:'var(--s5) var(--s4)' }}>
          {ed.titleJp && <div style={{ fontFamily:'var(--f-cjk)', fontSize:12, color:'var(--text-muted)', marginBottom:4 }}>{ed.titleJp}</div>}
          <div style={{ fontFamily:'var(--f-display)', fontSize:22, fontWeight:800, color:'var(--text)', letterSpacing:'-0.02em', marginBottom:'var(--s3)' }}>
            {ed.title}
          </div>
          <div style={{ display:'flex', gap:'var(--s2)', flexWrap:'wrap', marginBottom:'var(--s5)' }}>
            <RarityBadge type={ed.type} size="sm" />
            <div style={{ display:'inline-flex', alignItems:'center', gap:4, padding:'2px 8px',
              borderRadius:'var(--r-full)', fontSize:9, background:'var(--surface-2)',
              border:'1px solid var(--border-md)', color:'var(--text-sec)', fontWeight:700 }}>
              <Flag code={ed.country} size={11} /> {ed.country} · {ed.publisher}
            </div>
            <div style={{ display:'inline-flex', alignItems:'center', gap:4, padding:'2px 8px',
              borderRadius:'var(--r-full)', fontSize:9, background:'var(--success-dim)',
              border:'1px solid var(--success)', color:'var(--success)', fontWeight:700 }}>
              Score {ed.score}
            </div>
          </div>

          {/* Price alert */}
          <div style={{ background:'var(--surface-2)', border:'1px solid var(--border)', borderRadius:'var(--r-lg)', padding:'var(--s4)', marginBottom:'var(--s5)' }}>
            <div style={{ fontSize:11, fontWeight:700, color:'var(--text)', marginBottom:'var(--s2)' }}>Mejor precio disponible</div>
            <div style={{ fontSize:24, fontWeight:800, color:'var(--gold)', letterSpacing:'-0.02em', marginBottom:'var(--s3)' }}>
              ${sources[0]?.price} <span style={{ fontSize:11, color:'var(--text-muted)', fontWeight:500 }}>USD</span>
            </div>
            <button onClick={() => setPriceAlert(!priceAlert)} style={{
              width:'100%', padding:'10px', borderRadius:'var(--r-md)',
              background: priceAlert ? 'var(--gold)' : 'var(--gold-dim)',
              border:'1px solid var(--gold)',
              color: priceAlert ? 'var(--gold-text)' : 'var(--gold)',
              fontSize:13, fontWeight:700, cursor:'pointer', fontFamily:'var(--f-body)',
            }}>
              {priceAlert ? '🔔 Alerta creada' : '🔔 Alertarme si baja de precio'}
            </button>
          </div>

          <div style={{ fontFamily:'var(--f-display)', fontSize:16, fontWeight:700, color:'var(--text)', marginBottom:'var(--s4)' }}>
            📍 Dónde conseguirlo
          </div>
          <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--r-lg)', overflow:'hidden', marginBottom:'var(--s5)' }}>
            {sources.map((s,i) => <SourceRow key={i} src={s} isCheapest={s.isCheapest} />)}
          </div>

          <button onClick={() => setShowFeedback(!showFeedback)} style={{
            background:'none', border:'none', color:'var(--text-muted)', fontSize:11,
            cursor:'pointer', fontFamily:'var(--f-body)', textDecoration:'underline',
          }}>
            ⚠ Reportar un problema con esta página
          </button>
        </div>
      </div>
    );
  }

  /* DESKTOP */
  return (
    <div style={{ padding:'var(--s7) var(--s9)' }}>
      <div style={{ marginBottom:'var(--s6)', display:'flex', gap:'var(--s3)' }}>
        <BackBtn onClick={() => navigate('catalog')} />
        <BackBtn onClick={() => navigate('edition', { editionId: ed.id })} label={`${ed.title} · ${ed.volumes} vols.`} />
      </div>

      <div style={{ display:'grid', gridTemplateColumns:'220px 1fr', gap:'var(--s9)', alignItems:'flex-start', marginBottom:'var(--s9)' }}>
        <CoverPanel h={300} />

        <div>
          {ed.titleJp && (
            <div style={{ fontFamily:'var(--f-cjk)', fontSize:18, color:'var(--text-muted)', marginBottom:'var(--s2)', lineHeight:1.4 }}>
              {ed.titleJp} — 第1巻
            </div>
          )}
          <h1 style={{
            fontFamily:'var(--f-display)', fontSize:32, fontWeight:800,
            color:'var(--text)', letterSpacing:'-0.03em', marginBottom:'var(--s4)', lineHeight:1.1,
          }}>
            {ed.title} Vol. 1
          </h1>

          <div style={{ display:'flex', gap:'var(--s2)', flexWrap:'wrap', marginBottom:'var(--s6)' }}>
            <RarityBadge type={ed.type} />
            <div style={{ display:'inline-flex', alignItems:'center', gap:6, padding:'4px 12px',
              borderRadius:'var(--r-full)', fontSize:11, background:'var(--surface-2)',
              border:'1px solid var(--border-md)', color:'var(--text-sec)', fontWeight:600 }}>
              <Flag code={ed.country} size={13} /> {ed.country} · {ed.publisher}
            </div>
            {stockBadge(ed.stock)}
          </div>

          {/* Metadata grid */}
          <div style={{ display:'grid', gridTemplateColumns:'repeat(4,auto)', gap:'var(--s5) var(--s8)', marginBottom:'var(--s7)', width:'fit-content' }}>
            {[
              ['Tipo', TIER_META[ed.type]?.label || ed.type],
              ['Editorial', ed.publisher],
              ['País', ed.country],
              ['Idioma', ed.country === 'FR' ? 'Francés' : ed.country === 'JP' ? 'Japonés' : 'Inglés'],
              ['Score', ed.score],
              ['Tomos', ed.volumes],
              ['Precio desde', `$${ed.priceMin} USD`],
              ['ISBN', '978-' + Math.floor(Math.random()*9e9+1e9)],
            ].map(([k,v]) => (
              <div key={k}>
                <div style={{ fontSize:9,fontWeight:700,letterSpacing:'.1em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:2 }}>{k}</div>
                <div style={{ fontSize:13,fontWeight:600,color:'var(--text)' }}>{v}</div>
              </div>
            ))}
          </div>

          {/* Price alert */}
          <div style={{
            padding:'var(--s4) var(--s5)', background:'var(--surface-2)',
            border:'1px solid var(--border)', borderRadius:'var(--r-lg)',
            display:'flex', alignItems:'center', gap:'var(--s5)',
            marginBottom:'var(--s6)',
          }}>
            <div>
              <div style={{ fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)',marginBottom:2 }}>Alerta de precio</div>
              <div style={{ fontSize:12,color:'var(--text-sec)' }}>Avisame si baja de</div>
            </div>
            <div style={{ position:'relative' }}>
              <span style={{ position:'absolute',left:10,top:'50%',transform:'translateY(-50%)',fontSize:12,fontWeight:700,color:'var(--text-muted)' }}>$</span>
              <input type="number" value={alertPrice} onChange={e => setAlertPrice(+e.target.value)} style={{
                paddingLeft:22,paddingRight:8,paddingTop:7,paddingBottom:7,
                background:'var(--surface)',border:'1px solid var(--border-md)',
                borderRadius:'var(--r-md)',color:'var(--text)',fontSize:13,fontWeight:700,
                width:90,outline:'none',fontFamily:'var(--f-body)',
              }} />
            </div>
            <span style={{ fontSize:11,color:'var(--text-muted)' }}>USD</span>
            <button onClick={() => setPriceAlert(!priceAlert)} style={{
              padding:'7px 16px', borderRadius:'var(--r-md)',
              background: priceAlert ? 'var(--gold)' : 'var(--gold-dim)',
              border:'1px solid var(--gold)',
              color: priceAlert ? 'var(--gold-text)' : 'var(--gold)',
              fontSize:12, fontWeight:700, cursor:'pointer', fontFamily:'var(--f-body)',
            }}>
              {priceAlert ? '🔔 Alerta activa' : '🔔 Crear alerta'}
            </button>
          </div>
        </div>
      </div>

      {/* Sources */}
      <div style={{ marginBottom:'var(--s8)' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'var(--s4)', marginBottom:'var(--s5)' }}>
          <h2 style={{ fontFamily:'var(--f-display)', fontSize:24, fontWeight:700, color:'var(--text)', letterSpacing:'-0.02em' }}>
            📍 Dónde conseguirlo
          </h2>
          <div style={{ fontSize:11,color:'var(--text-muted)' }}>{sources.length} fuentes disponibles · Actualizado hace 2h</div>
        </div>
        <div style={{ background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--r-xl)', overflow:'hidden' }}>
          <div style={{ display:'grid', gridTemplateColumns:'180px 100px 1fr auto auto',
            gap:'var(--s4)', padding:'var(--s3) var(--s5)',
            background:'var(--surface-2)', borderBottom:'1px solid var(--border)' }}>
            {['Fuente','Precio','Stock','Idioma',''].map((h,i) => (
              <div key={i} style={{ fontSize:10,fontWeight:700,letterSpacing:'.08em',textTransform:'uppercase',color:'var(--text-muted)' }}>{h}</div>
            ))}
          </div>
          {sources.map((s,i) => <SourceRow key={i} src={s} isCheapest={s.isCheapest} />)}
        </div>
      </div>

      {/* Feedback */}
      <div style={{ borderTop:'1px solid var(--border)', paddingTop:'var(--s6)' }}>
        {!showFeedback && !feedbackSent && (
          <button onClick={() => setShowFeedback(true)} style={{
            background:'none', border:'none', color:'var(--text-muted)', fontSize:12,
            cursor:'pointer', fontFamily:'var(--f-body)', textDecoration:'underline',
            display:'flex', alignItems:'center', gap:4,
          }}>
            ⚠ ¿Algo incorrecto en esta página? Reportar
          </button>
        )}
        {showFeedback && !feedbackSent && (
          <div style={{
            background:'var(--surface-2)', border:'1px solid var(--border)',
            borderRadius:'var(--r-lg)', padding:'var(--s5)', maxWidth:400,
            animation:'fadeUp .2s ease',
          }}>
            <div style={{ fontSize:12,fontWeight:700,color:'var(--text)',marginBottom:'var(--s3)' }}>
              ¿Qué está mal?
            </div>
            <div style={{ display:'flex', flexDirection:'column', gap:'var(--s2)', marginBottom:'var(--s4)' }}>
              {['No debería estar acá','Precio incorrecto','Editorial o país equivocado','Otro'].map(opt => (
                <button key={opt} onClick={() => setFeedbackSent(true)} style={{
                  padding:'7px 12px', background:'var(--surface-3)',
                  border:'1px solid var(--border-md)', borderRadius:'var(--r-md)',
                  color:'var(--text-sec)', fontSize:12, cursor:'pointer',
                  fontFamily:'var(--f-body)', textAlign:'left',
                  transition:'all .12s',
                }}
                onMouseEnter={e => { e.currentTarget.style.color='var(--text)'; e.currentTarget.style.borderColor='var(--border-lg)'; }}
                onMouseLeave={e => { e.currentTarget.style.color='var(--text-sec)'; e.currentTarget.style.borderColor='var(--border-md)'; }}
                >{opt}</button>
              ))}
            </div>
            <button onClick={() => setShowFeedback(false)} style={{
              background:'none',border:'none',color:'var(--text-muted)',
              fontSize:11,cursor:'pointer',fontFamily:'var(--f-body)',
            }}>Cancelar</button>
          </div>
        )}
        {feedbackSent && (
          <div style={{ display:'flex', alignItems:'center', gap:'var(--s3)', animation:'fadeUp .2s ease' }}>
            <div style={{ width:28,height:28,borderRadius:'50%',background:'var(--success-dim)',
              border:'1px solid var(--success)',display:'flex',alignItems:'center',justifyContent:'center',
              fontSize:13,color:'var(--success)',fontWeight:800 }}>✓</div>
            <div style={{ fontSize:12,color:'var(--text-sec)' }}>
              Gracias — lo revisamos pronto.
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

Object.assign(window, { EditionScreen, DetailScreen });
