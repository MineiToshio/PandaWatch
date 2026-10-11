// PandaWatch UI Kit — Manga Detail View
const { useState } = React;

function MetaRow({ label, value, mono = false }) {
  if (!value) return null;
  return (
    <div style={{ display:'grid', gridTemplateColumns:'140px 1fr', gap:8, padding:'8px 0', borderBottom:'1px solid #EDE9E2', alignItems:'start' }}>
      <div style={{ fontSize:11, fontWeight:500, color:'#A89E93', letterSpacing:'0.06em', textTransform:'uppercase', paddingTop:1 }}>{label}</div>
      <div style={{ fontSize:13, color:'#1C1915', fontFamily: mono ? "'JetBrains Mono',monospace" : "'DM Sans',sans-serif", wordBreak:'break-all' }}>{value}</div>
    </div>
  );
}

function SignalCard({ signal }) {
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
    'special-cover': 'Non-standard cover treatment — foil, embossing, alternate art, etc.',
  };
  const colors = {
    'fanbook': { bg:'#EDFAF3', color:'#1A8A5A', border:'#A6DFCA' },
    'deluxe': { bg:'#EEF2FF', color:'#2D52CC', border:'#C7D2FE' },
    'box-set': { bg:'#F5F3FF', color:'#7C3AED', border:'#DDD6FE' },
    'variant-cover': { bg:'#FFFBEB', color:'#9E6C00', border:'#FDE68A' },
    'limited': { bg:'#FEF3EF', color:'#D93D1A', border:'#FABEAD' },
    'limited-print': { bg:'#FEF3EF', color:'#D93D1A', border:'#FABEAD' },
  };
  const c = colors[signal] || { bg:'#F5F1EB', color:'#706560', border:'#DDD8CF' };
  return (
    <div style={{ background: c.bg, border:`1px solid ${c.border}`, borderRadius:8, padding:'10px 12px' }}>
      <div style={{ fontSize:12, fontWeight:600, color: c.color, fontFamily:"'Space Grotesk',sans-serif", marginBottom:3, textTransform:'capitalize' }}>
        {signal.replace(/-/g, ' ')}
      </div>
      <div style={{ fontSize:11, color:'#706560', lineHeight:1.5 }}>
        {descriptions[signal] || 'Distinctive signal detected by PandaWatch.'}
      </div>
    </div>
  );
}

function DetailView({ item, onBack, isMobile }) {
  const [activeSection, setActiveSection] = useState(null);

  const toggleSection = (s) => setActiveSection(activeSection === s ? null : s);

  const SourceBadge = ({ cls }) => {
    const map = {
      trusted_media: { label:'Trusted Media', color:'#1A8A5A', bg:'#EDFAF3', border:'#A6DFCA' },
      publisher: { label:'Publisher Direct', color:'#2D52CC', bg:'#EEF2FF', border:'#C7D2FE' },
      marketplace: { label:'Marketplace Signal', color:'#9E6C00', bg:'#FFFBEB', border:'#FDE68A' },
    };
    const m = map[cls] || { label: cls, color:'#9CA3AF', bg:'#F9FAFB', border:'#E5E7EB' };
    return (
      <div style={{ display:'inline-flex', alignItems:'center', gap:5, padding:'3px 9px',
        borderRadius:5, border:`1px solid ${m.border}`, background: m.bg,
        fontSize:11, fontWeight:500, color: m.color }}>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        {m.label}
      </div>
    );
  };

  const SectionHeader = ({ id, title, children }) => (
    <div style={{ marginBottom:16 }}>
      <div
        onClick={() => isMobile && toggleSection(id)}
        style={{
          display:'flex', alignItems:'center', justifyContent:'space-between',
          marginBottom: (!isMobile || activeSection === id || activeSection === null) ? 12 : 0,
          cursor: isMobile ? 'pointer' : 'default',
          paddingBottom: 8, borderBottom:'1px solid #E5E0D8',
        }}
      >
        <div style={{ fontSize:14, fontWeight:600, color:'#1C1915', fontFamily:"'Space Grotesk',sans-serif" }}>{title}</div>
        {isMobile && <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#A89E93" strokeWidth="2"
          style={{ transform:(activeSection===id||!isMobile)?'rotate(180deg)':'none', transition:'transform 150ms' }}>
          <polyline points="6 9 12 15 18 9"/>
        </svg>}
      </div>
      {(!isMobile || activeSection === id || activeSection === null) && children}
    </div>
  );

  return (
    <div style={{ minHeight:'100vh' }}>
      <div style={{ background:'#fff', borderBottom:'1px solid #E5E0D8', padding: isMobile ? '16px 16px 0' : '20px 32px 0' }}>
        <Breadcrumb crumbs={[
          { label:'Catalog', onClick: onBack },
          { label: item.series },
          { label: item.shortTitle },
        ]} />
      </div>

      <div style={{ maxWidth:1200, margin:'0 auto', padding: isMobile ? '16px 12px' : '28px 32px' }}>
        <div style={{ display:'flex', gap:40, alignItems:'flex-start', flexWrap: isMobile ? 'wrap' : 'nowrap' }}>

          {/* LEFT — Cover */}
          <div style={{ width: isMobile ? '100%' : 300, flexShrink:0 }}>
            <div style={{ borderRadius:12, overflow:'hidden', border:'1px solid #E5E0D8', boxShadow:'0 4px 16px rgba(0,0,0,0.08)', aspectRatio:'2/3', position:'relative', marginBottom:14, maxWidth: isMobile ? 200 : '100%', margin: isMobile ? '0 auto 14px' : '0 0 14px' }}>
              <CoverPlaceholder scheme={item.coverScheme} series={item.series} title={item.shortTitle} />
            </div>

            {/* Source */}
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              <a
                href={item.sourceUrl || '#'}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  display:'flex', alignItems:'center', justifyContent:'center', gap:6,
                  padding:'10px', border:'1.5px solid #DDD8CF', borderRadius:8,
                  fontSize:13, fontWeight:500, color:'#554D49', textDecoration:'none',
                  background:'#fff',
                }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                  <polyline points="15 3 21 3 21 9"/>
                  <line x1="10" y1="14" x2="21" y2="3"/>
                </svg>
                View original source
              </a>
            </div>
          </div>

          {/* RIGHT — Info */}
          <div style={{ flex:1, minWidth:0 }}>
            <div style={{ marginBottom:6, fontSize:12, color:'#A89E93', fontWeight:500, letterSpacing:'0.06em', textTransform:'uppercase' }}>
              {item.series}
            </div>
            <h1 style={{ fontFamily:"'Space Grotesk',sans-serif", fontSize: isMobile ? 20 : 24, fontWeight:700, color:'#1C1915', letterSpacing:'-0.02em', marginBottom:12, lineHeight:1.25 }}>
              {item.title}
            </h1>

            <div style={{ display:'flex', flexWrap:'wrap', gap:8, marginBottom:16, alignItems:'center' }}>
              <RarityBadge rarity={item.rarity} size="md" />
              <div style={{ padding:'4px 10px', borderRadius:5, background:'#F5F1EB', color:'#554D49', fontSize:12, fontWeight:500, fontFamily:"'DM Sans',sans-serif" }}>
                {item.editionType}
              </div>
              {item.status && (
                <div style={{ padding:'4px 10px', borderRadius:999, fontSize:11, fontWeight:600,
                  background: item.status === 'new' ? '#FEF3EF' : '#FFFBEB',
                  color: item.status === 'new' ? '#D93D1A' : '#9E6C00',
                  border:`1px solid ${item.status === 'new' ? '#FABEAD' : '#FDE68A'}` }}>
                  {item.status === 'new' ? '● New' : '↻ Changed'}
                </div>
              )}
            </div>

            {/* Core metadata */}
            <div style={{ marginBottom:24 }}>
              <MetaRow label="Series" value={item.series} />
              <MetaRow label="Edition" value={item.editionType} />
              <MetaRow label="Publisher" value={item.publisher} />
              <MetaRow label="Country" value={item.country} />
              <MetaRow label="Language" value={item.language} />
              <MetaRow label="ISBN" value={item.isbn} mono />
              <MetaRow label="Price" value={item.price} />
              <MetaRow label="Published" value={item.publishedAt} />
            </div>

            {/* Why it was detected */}
            <SectionHeader id="signals" title="Why it was detected">
              <p style={{ fontSize:13, color:'#8C8178', lineHeight:1.6, marginBottom:12 }}>
                Rarity estimated from signals, source class, and availability data. PandaWatch flagged this edition for the following reasons:
              </p>
              <div style={{ display:'grid', gridTemplateColumns: isMobile ? '1fr' : '1fr 1fr', gap:8 }}>
                {(item.signals || []).map(sig => <SignalCard key={sig} signal={sig} />)}
              </div>
            </SectionHeader>

            {/* Collector notes */}
            <SectionHeader id="notes" title="Collector Notes">
              <div style={{
                background:'#F5F1EB', border:'1px dashed #C6BEB4', borderRadius:8,
                padding:'16px', display:'flex', alignItems:'center', gap:10, color:'#A89E93',
              }}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
                <div>
                  <div style={{ fontSize:12, fontWeight:500, color:'#8C8178', marginBottom:2 }}>Wishlist & notes coming soon</div>
                  <div style={{ fontSize:11, color:'#A89E93' }}>Track your collection, add personal notes, and mark items as owned or wanted.</div>
                </div>
              </div>
            </SectionHeader>

            {/* Data confidence */}
            <SectionHeader id="confidence" title="Data Confidence">
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
                  <div style={{ fontSize:12, color:'#8C8178' }}>Source class</div>
                  <SourceBadge cls={item.sourceClass} />
                </div>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', paddingTop:8, borderTop:'1px solid #EDE9E2' }}>
                  <div style={{ fontSize:12, color:'#8C8178' }}>Source</div>
                  <div style={{ fontSize:12, color:'#1C1915', fontWeight:500 }}>{item.source}</div>
                </div>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', paddingTop:8, borderTop:'1px solid #EDE9E2' }}>
                  <div style={{ fontSize:12, color:'#8C8178' }}>Detected at</div>
                  <div style={{ fontSize:12, color:'#1C1915', fontFamily:"'JetBrains Mono',monospace" }}>{item.detectedAt}</div>
                </div>
                <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', paddingTop:8, borderTop:'1px solid #EDE9E2' }}>
                  <div style={{ fontSize:12, color:'#8C8178' }}>Rarity score</div>
                  <div style={{ fontSize:12, fontFamily:"'JetBrains Mono',monospace", fontWeight:500, color:'#1C1915' }}>
                    {item.score ?? 'n/a'} / 100
                  </div>
                </div>
                <div style={{ display:'flex', flexWrap:'wrap', gap:6, paddingTop:8, borderTop:'1px solid #EDE9E2' }}>
                  {(item.tags || []).map(tag => (
                    <div key={tag} style={{ padding:'2px 7px', borderRadius:3, background:'#EDE9E2', color:'#706560', fontSize:10, fontFamily:"'JetBrains Mono',monospace" }}>
                      {tag}
                    </div>
                  ))}
                </div>
              </div>
            </SectionHeader>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { DetailView });
