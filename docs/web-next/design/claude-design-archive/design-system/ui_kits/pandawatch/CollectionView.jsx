// PandaWatch UI Kit — Collection Detail View
const { useState } = React;

function Breadcrumb({ crumbs, onNavigate }) {
  return (
    <div style={{ display:'flex', alignItems:'center', gap:6, marginBottom:20, flexWrap:'wrap' }}>
      {crumbs.map((crumb, i) => (
        <React.Fragment key={i}>
          {i > 0 && <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#C6BEB4" strokeWidth="2"><polyline points="9 18 15 12 9 6"/></svg>}
          <span
            onClick={() => crumb.onClick && crumb.onClick()}
            style={{
              fontSize:13, color: crumb.onClick ? '#1A8A5A' : '#1C1915',
              fontWeight: crumb.onClick ? 400 : 500,
              cursor: crumb.onClick ? 'pointer' : 'default',
              fontFamily:"'DM Sans',sans-serif",
            }}
          >{crumb.label}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

function CollectionView({ item, onSelectItem, onBack, isMobile }) {
  const [innerFilter, setInnerFilter] = useState('all');
  const covers = item.volumeCovers || [item.coverScheme, item.coverScheme, item.coverScheme];

  // Generate fake volumes for demo
  const volumes = Array.from({ length: item.volumes || 3 }, (_, i) => ({
    ...item,
    id: `${item.id}-vol-${i+1}`,
    type: 'single',
    title: `${item.series} ${item.editionType} Vol. ${i + 1}`,
    shortTitle: `Vol. ${i + 1}`,
    coverScheme: covers[i % covers.length] || item.coverScheme,
    score: Math.max(10, item.score - (i * 2)),
    rarity: scoreToRarity(Math.max(10, item.score - (i * 2))),
    rarityConfig: RARITY_CONFIG[scoreToRarity(Math.max(10, item.score - (i * 2)))],
    isbn: `978${Math.floor(Math.random()*9000000000+1000000000)}`,
    publishedAt: `${2018 + Math.floor(i/2)}-${String((i % 12) + 1).padStart(2,'0')}-01`,
    status: i === 0 ? 'new' : (i === 1 ? 'changed' : null),
  }));

  return (
    <div style={{ minHeight:'100vh' }}>
      <div style={{ background:'#fff', borderBottom:'1px solid #E5E0D8', padding: isMobile ? '20px 16px' : '28px 32px' }}>
        <Breadcrumb crumbs={[
          { label:'Catalog', onClick: onBack },
          { label:'Collections' },
          { label: item.title },
        ]} onNavigate={onBack} />

        <div style={{ display:'flex', gap: isMobile ? 16 : 32, alignItems:'flex-start', flexWrap: isMobile ? 'wrap' : 'nowrap' }}>
          {/* Stacked covers header — front is the real cover, backs are plain solid containers (matches CollectionCard pattern) */}
          <div style={{
            position:'relative', flexShrink:0,
            width: isMobile ? 116 : 156,            // card_width + max right peek (12)
            paddingRight: 12, paddingBottom: 16,    // gutter for back peeks
            boxSizing:'border-box',
          }}>
            {/* Far back */}
            <div style={{
              position:'absolute', top:16, left:12, right:0, bottom:0,
              zIndex:1, borderRadius:10,
              background:'#D6CFC0', border:'1px solid #BAB2A1',
              boxShadow:'0 1px 6px rgba(0,0,0,0.06)',
            }}/>
            {/* Mid back */}
            <div style={{
              position:'absolute', top:8, left:6, right:6, bottom:8,
              zIndex:2, borderRadius:10,
              background:'#E2DCCE', border:'1px solid #C9C2B1',
              boxShadow:'0 2px 8px rgba(0,0,0,0.07)',
            }}/>
            {/* Main cover */}
            <div style={{
              position:'relative', zIndex:3,
              width:'100%', aspectRatio:'2/3',
              borderRadius:10, overflow:'hidden',
              border:'1px solid #E5E0D8',
              boxShadow:'0 4px 18px rgba(0,0,0,0.13), 0 1px 4px rgba(0,0,0,0.07)',
            }}>
              <CoverPlaceholder scheme={covers[0]} series="" title="" />
            </div>
          </div>

          {/* Info */}
          <div style={{ flex:1 }}>
            <div style={{ fontSize:11, color:'#A89E93', fontWeight:500, letterSpacing:'0.07em', textTransform:'uppercase', marginBottom:4 }}>
              {item.series}
            </div>
            <h1 style={{ fontFamily:"'Space Grotesk',sans-serif", fontSize: isMobile ? 20 : 26, fontWeight:700, color:'#1C1915', letterSpacing:'-0.02em', marginBottom:10, lineHeight:1.2 }}>
              {item.title}
            </h1>
            <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:14, alignItems:'center' }}>
              <RarityBadge rarity={item.rarity} size="md" />
              <div style={{ display:'inline-flex', alignItems:'center', gap:5, padding:'4px 10px', borderRadius:5, background:'#F5F1EB', color:'#554D49', fontSize:12, fontWeight:500 }}>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
                {item.volumes} volumes
              </div>
              {item.status && (
                <div style={{ padding:'4px 10px', borderRadius:999, fontSize:11, fontWeight:600,
                  background: item.status === 'new' ? '#FEF3EF' : '#FFFBEB',
                  color: item.status === 'new' ? '#D93D1A' : '#9E6C00',
                  border: `1px solid ${item.status === 'new' ? '#FABEAD' : '#FDE68A'}` }}>
                  {item.status === 'new' ? 'New' : 'Changed'}
                </div>
              )}
            </div>

            <div style={{ display:'grid', gridTemplateColumns: isMobile ? '1fr 1fr' : 'repeat(4,auto)', gap:'8px 20px', marginBottom:14 }}>
              {[
                { icon:'globe', label:'Publisher', value: item.publisher },
                { icon:'map', label:'Country', value: item.country },
                { icon:'lang', label:'Language', value: item.language },
                { icon:'cal', label:'First Release', value: item.publishedAt?.slice(0,4) },
              ].map(m => (
                <div key={m.label}>
                  <div style={{ fontSize:10, color:'#A89E93', fontWeight:500, letterSpacing:'0.07em', textTransform:'uppercase', marginBottom:2 }}>{m.label}</div>
                  <div style={{ fontSize:13, fontWeight:500, color:'#1C1915' }}>{m.value}</div>
                </div>
              ))}
            </div>

            <div style={{ display:'flex', flexWrap:'wrap', gap:6 }}>
              {item.signals.map(sig => (
                <div key={sig} style={{ padding:'3px 8px', borderRadius:999, background:'#EDE9E2', color:'#706560', fontSize:11, fontWeight:500 }}>{sig}</div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Volumes grid */}
      <div style={{ padding: isMobile ? '16px 12px' : '20px 32px', maxWidth:1440, margin:'0 auto' }}>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', marginBottom:16 }}>
          <div style={{ fontSize:15, fontWeight:600, fontFamily:"'Space Grotesk',sans-serif", color:'#1C1915', whiteSpace:'nowrap' }}>
            All {item.volumes} Volumes
          </div>
          <div style={{ display:'flex', gap:6 }}>
            {['all','new','changed'].map(f => (
              <div key={f} onClick={() => setInnerFilter(f)} style={{
                padding:'4px 12px', borderRadius:999, fontSize:11, fontWeight:500,
                border:`1.5px solid ${innerFilter===f ? '#1A8A5A' : '#DDD8CF'}`,
                background: innerFilter===f ? '#EDFAF3' : '#fff',
                color: innerFilter===f ? '#1A8A5A' : '#706560',
                cursor:'pointer', textTransform:'capitalize',
              }}>{f}</div>
            ))}
          </div>
        </div>

        <div style={{
          display:'grid',
          gridTemplateColumns: isMobile ? 'repeat(2,1fr)' : 'repeat(5,1fr)',
          gap: isMobile ? 10 : 16, alignItems:'start',
        }}>
          {volumes
            .filter(v => innerFilter === 'all' || v.status === innerFilter)
            .map(vol => (
              <MangaCard key={vol.id} item={vol} onClick={onSelectItem} />
            ))
          }
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { CollectionView, Breadcrumb });
