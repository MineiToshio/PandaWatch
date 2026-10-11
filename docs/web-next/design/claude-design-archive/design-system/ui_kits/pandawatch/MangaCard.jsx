// PandaWatch UI Kit — Manga Card & Collection Card Components
const { useState } = React;

// ── Rarity Badge ─────────────────────────────────────────────
function RarityIcon({ type, size = 12 }) {
  const s = { width: size, height: size, flexShrink: 0 };
  switch (type) {
    case 'circle':   return <svg style={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><circle cx="12" cy="12" r="10"/></svg>;
    case 'star':     return <svg style={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>;
    case 'star2':    return <svg style={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>;
    case 'sparkle':  return <svg style={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z"/><path d="M5 17l.75 2.25L8 20l-2.25.75L5 23l-.75-2.25L2 20l2.25-.75z"/></svg>;
    case 'diamond':  return <svg style={s} viewBox="0 0 24 24" fill="currentColor"><path d="M6 3h12l4 6-10 13L2 9z"/></svg>;
    default:         return <svg style={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>;
  }
}

function RarityBadge({ rarity, size = 'md', glassy = false }) {
  const cfg = RARITY_CONFIG[rarity] || RARITY_CONFIG.unknown;
  const [hover, setHover] = useState(false);
  const sizes = { sm: { padding:'4px 8px', fontSize:10, radius:5, gap:4, iconSize:9 },
                  md: { padding:'4px 9px', fontSize:11, radius:5, gap:5, iconSize:12 },
                  lg: { padding:'6px 12px', fontSize:13, radius:7, gap:6, iconSize:14 } };
  const sz = sizes[size] || sizes.md;
  const style = glassy
    ? { background:'rgba(20,17,14,0.82)', color: cfg.color, borderColor:'rgba(255,255,255,0.12)', backdropFilter:'blur(6px)' }
    : { background: cfg.bg, color: cfg.color, borderColor: cfg.border };

  return (
    <div style={{ position:'relative', display:'inline-flex' }}>
      <div
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        style={{
          display:'inline-flex', alignItems:'center', gap: sz.gap,
          padding: sz.padding, borderRadius: sz.radius,
          fontSize: sz.fontSize, fontWeight:600,
          fontFamily:"'Space Grotesk',sans-serif",
          border:'1px solid', cursor:'default',
          whiteSpace:'nowrap',
          ...style,
        }}
      >
        <RarityIcon type={cfg.icon} size={sz.iconSize} />
        {cfg.label}
      </div>
      {hover && (
        <div style={{
          position:'absolute', top:'calc(100% + 6px)', left:0, zIndex:999,
          background:'#1C1915', color:'#fff', borderRadius:6,
          padding:'6px 10px', fontSize:11, lineHeight:1.4,
          maxWidth:200, whiteSpace:'normal', pointerEvents:'none',
          boxShadow:'0 4px 12px rgba(0,0,0,0.2)',
          fontFamily:"'DM Sans',sans-serif", fontWeight:400,
        }}>
          {cfg.tooltip}
        </div>
      )}
    </div>
  );
}

// ── Cover Placeholder ─────────────────────────────────────────
// Renders a real image when imgSrc is provided (matches the preview spec exactly);
// otherwise falls back to a gradient placeholder keyed by `scheme`.
function CoverPlaceholder({ scheme, series, title, imgSrc, style: extraStyle = {} }) {
  if (imgSrc) {
    return (
      <img
        src={imgSrc}
        alt={title || series || ''}
        style={{
          position:'absolute', inset:0, width:'100%', height:'100%',
          objectFit:'cover', objectPosition:'center top', ...extraStyle,
        }}
      />
    );
  }
  const s = COVER_SCHEMES[scheme] || COVER_SCHEMES['generic-dark'];
  return (
    <div style={{ position:'absolute', inset:0, background: s.grad, ...extraStyle }}>
      <div style={{
        position:'absolute', inset:0,
        backgroundImage:'repeating-linear-gradient(135deg,rgba(255,255,255,0.025) 0px,rgba(255,255,255,0.025) 1px,transparent 1px,transparent 14px)',
      }}/>
      <div style={{
        position:'absolute', top:0, left:0, right:0, height:24,
        background: s.bar, display:'flex', alignItems:'center', padding:'0 8px',
      }}>
        <span style={{
          fontSize:8, letterSpacing:'0.12em', textTransform:'uppercase',
          color: s.barText, fontFamily:"'Space Grotesk',sans-serif", fontWeight:600,
          overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
        }}>{series}</span>
      </div>
    </div>
  );
}

// ── Single Manga Card ─────────────────────────────────────────
function MangaCard({ item, onClick }) {
  const [hovered, setHovered] = useState(false);

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick(item)}
      onKeyDown={e => e.key === 'Enter' && onClick(item)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width:'100%', borderRadius:12, overflow:'hidden',
        background:'#fff', border:'1px solid #E5E0D8',
        boxShadow: hovered ? '0 6px 16px rgba(0,0,0,0.10)' : '0 1px 3px rgba(0,0,0,0.06)',
        transform: hovered ? 'translateY(-3px)' : 'none',
        transition:'transform 180ms cubic-bezier(0.22,1,0.36,1), box-shadow 180ms',
        cursor:'pointer', outline:'none', position:'relative',
      }}
      onFocus={e => e.currentTarget.style.outline = '2px solid #1A8A5A'}
      onBlur={e => e.currentTarget.style.outline = 'none'}
    >
      {/* Cover — clean, no text overlay */}
      <div style={{ width:'100%', aspectRatio:'2/3', position:'relative', overflow:'hidden', borderRadius:'11px 11px 0 0' }}>
        <CoverPlaceholder scheme={item.coverScheme} series="" title="" imgSrc={item.imgSrc} />

        {/* Rarity badge — only unique info on the cover */}
        <div style={{ position:'absolute', top:8, left:8, zIndex:2 }}>
          <RarityBadge rarity={item.rarity} size="sm" glassy />
        </div>

        {/* Status — text badge, not a dot */}
        {item.status && (
          <div style={{
            position:'absolute', top:8, right:8, zIndex:2,
            padding:'3px 7px', borderRadius:4, fontSize:9, fontWeight:700,
            fontFamily:"'Space Grotesk',sans-serif", letterSpacing:'0.04em',
            textTransform:'uppercase',
            background: item.status === 'new' ? '#D93D1A' : 'rgba(158,108,0,0.85)',
            color: item.status === 'new' ? '#fff' : '#FDE68A',
          }}>
            {item.status === 'new' ? 'New' : 'Changed'}
          </div>
        )}

        {/* Hover actions */}
        <div style={{
          position:'absolute', bottom:0, left:0, right:0, zIndex:3,
          background:'rgba(28,25,21,0.88)', backdropFilter:'blur(6px)',
          padding:'8px 10px', display:'flex', gap:6,
          opacity: hovered ? 1 : 0, transition:'opacity 150ms',
          borderRadius:'0 0 11px 11px',
        }}>
          <div style={{ flex:1, textAlign:'center', fontSize:11, fontWeight:500,
            color:'#fff', padding:'5px', borderRadius:4,
            background:'rgba(255,255,255,0.12)',
          }}>View details</div>
          <div style={{ flex:1, textAlign:'center', fontSize:11, fontWeight:500,
            color:'rgba(255,255,255,0.65)', padding:'5px', borderRadius:4,
          }}>Source ↗</div>
        </div>
      </div>

      {/* Info */}
      <div style={{ padding:'10px 12px 12px' }}>
        <div style={{ fontSize:10, color:'#A89E93', fontWeight:500, letterSpacing:'0.06em',
          textTransform:'uppercase', marginBottom:3, overflow:'hidden',
          textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {item.series}
        </div>
        <div style={{ fontSize:13, fontWeight:600, fontFamily:"'Space Grotesk',sans-serif",
          color:'#1C1915', lineHeight:1.25, marginBottom:6,
          display:'-webkit-box', WebkitLineClamp:2,
          WebkitBoxOrient:'vertical', overflow:'hidden' }}>
          {item.shortTitle}
        </div>
        <div style={{ fontSize:11, color:'#8C8178' }}>{item.publisher} · {item.country}</div>
        <div style={{ display:'flex', alignItems:'center', gap:4, marginTop:3 }}>
          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#A89E93" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
          </svg>
          <span style={{ fontSize:10, color:'#A89E93' }}>{item.language}</span>
        </div>
        <div style={{ display:'inline-flex', alignItems:'center', gap:4,
          background:'#F5F1EB', color:'#706560', borderRadius:3,
          padding:'2px 7px', fontSize:10, fontWeight:500, marginTop:7 }}>
          {item.editionType}
        </div>
      </div>
    </div>
  );
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
function CollectionCard({ item, onClick }) {
  const [hovered, setHovered] = useState(false);
  const isBoxSet = item.editionType === 'Box Set' || item.editionType === 'Anniversary Box Set';
  const typeLabel = isBoxSet ? 'Box Set' : 'Collection';
  const unitsLabel = isBoxSet ? 'items' : 'volumes';

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onClick(item)}
      onKeyDown={e => e.key === 'Enter' && onClick(item)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position:'relative',
        width:'100%',          // fills grid cell — same as MangaCard
        boxSizing:'border-box',
        cursor:'pointer', outline:'none',
      }}
      onFocus={e => e.currentTarget.style.outline = '2px solid #1A8A5A'}
      onBlur={e => e.currentTarget.style.outline = 'none'}
    >
      {/* Far back: peeks 12px right and 16px below the main card. Spans the wrapper
          via top+bottom and left+right → same dimensions as the main card, just offset. */}
      <div style={{
        position:'absolute', top:16, left:12, right:-12, bottom:-16,
        zIndex:1, borderRadius:12,
        background:'#D6CFC0', border:'1px solid #BAB2A1',
        boxShadow:'0 1px 6px rgba(0,0,0,0.06)',
      }}/>

      {/* Mid back: peeks 6px right and 8px below. */}
      <div style={{
        position:'absolute', top:8, left:6, right:-6, bottom:-8,
        zIndex:2, borderRadius:12,
        background:'#E2DCCE', border:'1px solid #C9C2B1',
        boxShadow:'0 2px 8px rgba(0,0,0,0.07)',
      }}/>

      {/* Main (front) card — full wrapper width = full grid cell width = same as MangaCard */}
      <div style={{
        position:'relative', zIndex:3,
        borderRadius:12, overflow:'hidden',
        background:'#fff', border:'1px solid #E5E0D8',
        boxShadow: hovered
          ? '0 8px 24px rgba(0,0,0,0.14), 0 2px 6px rgba(0,0,0,0.08)'
          : '0 4px 18px rgba(0,0,0,0.13), 0 1px 4px rgba(0,0,0,0.07)',
        transform: hovered ? 'translateY(-2px)' : 'none',
        transition:'transform 180ms cubic-bezier(0.22,1,0.36,1), box-shadow 180ms',
      }}>
        {/* Cover — clean, no overlays or title */}
        <div style={{ width:'100%', aspectRatio:'2/3', position:'relative', overflow:'hidden', borderRadius:'11px 11px 0 0' }}>
          <CoverPlaceholder scheme={item.coverScheme} series="" title="" imgSrc={item.imgSrc} />

          {/* Rarity — top-LEFT (matches single card) */}
          <div style={{ position:'absolute', top:8, left:8, zIndex:2 }}>
            <RarityBadge rarity={item.rarity} size="sm" glassy />
          </div>

          {/* Status — top-RIGHT (matches single card) */}
          {item.status && (
            <div style={{
              position:'absolute', top:8, right:8, zIndex:2,
              padding:'3px 7px', borderRadius:4, fontSize:9, fontWeight:700,
              fontFamily:"'Space Grotesk',sans-serif", letterSpacing:'0.04em',
              textTransform:'uppercase', whiteSpace:'nowrap',
              background: item.status === 'new' ? '#D93D1A' : 'rgba(158,108,0,0.85)',
              color: item.status === 'new' ? '#fff' : '#FDE68A',
            }}>
              {item.status === 'new' ? 'New' : 'Changed'}
            </div>
          )}
        </div>

        {/* Info section */}
        <div style={{ padding:'11px 13px 13px' }}>
          <div style={{ fontSize:10, color:'#A89E93', fontWeight:500, letterSpacing:'0.06em',
            textTransform:'uppercase', marginBottom:3, overflow:'hidden',
            textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {item.series}
          </div>
          <div style={{ fontSize:13, fontWeight:600, fontFamily:"'Space Grotesk',sans-serif",
            color:'#1C1915', lineHeight:1.25, marginBottom:5,
            display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical', overflow:'hidden' }}>
            {item.shortTitle}
          </div>
          <div style={{ fontSize:11, color:'#8C8178' }}>{item.publisher} · {item.country}</div>

          {/* Footer: Collection/Box Set type tag (moved from cover) + count */}
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between',
            marginTop:10, paddingTop:10, borderTop:'1px solid #EDE9E2', gap:8 }}>
            <div style={{
              display:'inline-flex', alignItems:'center', gap:5,
              padding:'4px 8px', borderRadius:5,
              background:'#F0EDE6', border:'1px solid #DDD8CF',
              fontSize:10, fontWeight:600, fontFamily:"'Space Grotesk',sans-serif",
              color:'#3D3833', letterSpacing:'0.02em', whiteSpace:'nowrap',
            }}>
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
                <rect x="2" y="7" width="20" height="14" rx="2"/>
                <path d="M16 7V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2"/>
              </svg>
              {typeLabel}
            </div>
            <div style={{ fontSize:11, fontWeight:500, color:'#1A8A5A', whiteSpace:'nowrap' }}>
              <strong style={{ fontWeight:700 }}>{item.volumes}</strong> {unitsLabel}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { RarityBadge, RarityIcon, MangaCard, CollectionCard, CoverPlaceholder });
