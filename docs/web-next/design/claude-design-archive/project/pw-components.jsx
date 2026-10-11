/* ═══════════════════════════════════════════
   PW-COMPONENTS.JSX — shared components
   PWLogo · Flag · Chip · RarityBadge
   MangaCard · CoverPlaceholder · MOCK DATA
═══════════════════════════════════════════ */

/* ── Logo ── */
function PWLogo({ size = 32, showWordmark = false, onDark = null }) {
  const body = onDark === null ? 'var(--logo-body)'  : onDark === true ? '#E8ECF8' : '#FFFFFF';
  const ink  = onDark === null ? 'var(--logo-patch)' : onDark === true ? '#0C1628' : '#111A38';
  return (
    <div style={{ display:'flex', alignItems:'center', gap: size * 0.28 }}>
      <svg width={size} height={size} viewBox="0 0 56 56" fill="none"
        style={onDark === false ? { filter:'drop-shadow(0 1px 3px rgba(0,0,0,.10))' } : undefined}>
        <circle cx="11" cy="13" r="9"  fill={ink} />
        <circle cx="45" cy="13" r="9"  fill={ink} />
        <circle cx="28" cy="31" r="21" fill={body} />
        <ellipse cx="18" cy="27" rx="9.5" ry="8.5" transform="rotate(-9 18 27)" fill={ink} />
        <ellipse cx="38" cy="27" rx="9.5" ry="8.5" transform="rotate(9 38 27)"  fill={ink} />
        <circle cx="17.5" cy="27" r="4"   fill={body} />
        <circle cx="38.5" cy="27" r="4"   fill={body} />
        <circle cx="18"   cy="27.5" r="2.1" fill={ink} />
        <circle cx="16.8" cy="26.2" r="0.9" fill={body} opacity="0.55" />
        <path d="M38.5 25.1 L39.2 26.8 L41.0 27.3 L39.2 27.9 L38.5 29.5 L37.8 27.9 L36.0 27.3 L37.8 26.8 Z" fill={ink} />
        <circle cx="38.5" cy="27.3" r="0.95" fill="#F5C242" />
        <ellipse cx="28" cy="36" rx="3.2" ry="2.2" fill={ink} opacity="0.85" />
        <path d="M25.6 38 Q28 39.8 30.4 38" stroke={ink} strokeWidth="1.1" strokeLinecap="round" fill="none" opacity="0.38" />
      </svg>
      {showWordmark && (
        <div style={{
          fontFamily:'var(--f-display)', fontWeight:800,
          fontSize: size * 0.5, letterSpacing:'-0.03em', lineHeight:1,
          userSelect:'none',
        }}>
          <span style={{ color: onDark !== null ? (onDark ? '#E8ECF8' : '#111A38') : 'var(--text)' }}>Panda</span>
          <span style={{ color:'#F5C242' }}>Watch</span>
        </div>
      )}
    </div>
  );
}

/* ── Flag ── */
function Flag({ code, size = 15 }) {
  const flags = { JP:'🇯🇵',FR:'🇫🇷',US:'🇺🇸',ES:'🇪🇸',IT:'🇮🇹',BR:'🇧🇷',
    DE:'🇩🇪',UK:'🇬🇧',KR:'🇰🇷',MX:'🇲🇽',AR:'🇦🇷',CA:'🇨🇦' };
  return <span style={{ fontSize:size, lineHeight:1 }}>{flags[code] || '🌐'}</span>;
}

/* ── Chip ── */
function Chip({ label, selected, onClick, flag, icon, removable, onRemove, color }) {
  return (
    <div
      onClick={onClick}
      style={{
        display:'inline-flex', alignItems:'center', gap:5,
        padding:'5px 11px', borderRadius:'var(--r-full)',
        fontSize:12, fontWeight:600, fontFamily:'var(--f-body)',
        cursor:'pointer', userSelect:'none', whiteSpace:'nowrap',
        transition:'all .12s',
        border:`1px solid ${selected ? (color || 'var(--gold)') : 'var(--border-md)'}`,
        background: selected ? (color ? color + '22' : 'var(--gold-dim)') : 'var(--surface-2)',
        color: selected ? (color || 'var(--gold)') : 'var(--text-sec)',
      }}
      onMouseEnter={e => { if (!selected) { e.currentTarget.style.color='var(--text)'; e.currentTarget.style.borderColor='var(--border-lg)'; }}}
      onMouseLeave={e => { if (!selected) { e.currentTarget.style.color='var(--text-sec)'; e.currentTarget.style.borderColor='var(--border-md)'; }}}
    >
      {flag && <Flag code={flag} size={12} />}
      {icon && <span style={{fontSize:12}}>{icon}</span>}
      <span>{label}</span>
      {removable && selected && (
        <span onClick={e => { e.stopPropagation(); onRemove && onRemove(); }}
          style={{ fontSize:11, opacity:.7, marginLeft:1, lineHeight:1 }}>✕</span>
      )}
    </div>
  );
}

/* ── Rarity Badge ── */
const TIER_META = {
  standard:  { color:'var(--r1)', bg:'rgba(120,131,153,.14)', border:'rgba(120,131,153,.3)',  label:'Standard',  cssClass:null },
  deluxe:    { color:'var(--r2)', bg:'rgba(212,138,12,.14)',  border:'rgba(212,138,12,.35)',  label:'Deluxe',    cssClass:null },
  limited:   { color:'var(--r3)', bg:'rgba(224,88,48,.14)',   border:'rgba(224,88,48,.35)',   label:'Limited',   cssClass:null },
  boxset:    { color:'var(--r4)', bg:'rgba(12,169,158,.14)',  border:'rgba(12,169,158,.35)',  label:'Box Set',   cssClass:null },
  artbook:   { color:'var(--r5)', bg:'rgba(149,64,230,.14)',  border:'rgba(149,64,230,.35)',  label:'Artbook',   cssClass:null },
  kanzenban: { color:'#F5C242',   bg:'rgba(245,194,66,.15)',  border:'#F5C242',               label:'Rare',       cssClass:'badge-kanzenban' },
  variant:   { color:'#C46BFF',   bg:'rgba(196,107,255,.15)', border:'#C46BFF',               label:'Super Rare', cssClass:'badge-variant'   },
  ultra:     { color:'#C46BFF',   bg:'#9B3FE0',               border:'#C46BFF',               label:'Ultra Rare', cssClass:'badge-ultra'     },
};

function RarityBadge({ type, size = 'sm' }) {
  const t = TIER_META[type] || TIER_META.standard;
  const pad = size === 'sm' ? '2px 8px' : '4px 12px';
  const fs  = size === 'sm' ? 9 : 11;
  const special = ['kanzenban','variant','ultra'].includes(type);
  return (
    <div
      className={t.cssClass || ''}
      style={t.cssClass ? {
        display:'inline-flex', alignItems:'center', gap:4,
        padding:pad, borderRadius:'var(--r-full)',
        fontSize:fs, fontWeight:800, letterSpacing:'.06em',
        textTransform:'uppercase', fontFamily:'var(--f-body)',
        position:'relative', overflow:'hidden', whiteSpace:'nowrap',
      } : {
        display:'inline-flex', alignItems:'center', gap:4,
        padding:pad, borderRadius:'var(--r-full)',
        fontSize:fs, fontWeight:800, letterSpacing:'.06em',
        textTransform:'uppercase', fontFamily:'var(--f-body)',
        background:t.bg, color:t.color, border:`1px solid ${t.border}`,
        whiteSpace:'nowrap',
      }}
    >
      {special && <span style={{fontSize:fs-1}}>✦</span>}
      {t.label}
    </div>
  );
}

/* ── Manga Card ── */
function MangaCard({ edition, onClick, size = 'md', isMobile }) {
  const cardRef = React.useRef(null);
  const t = TIER_META[edition.type] || TIER_META.standard;
  const isSpecial = ['kanzenban','variant','ultra'].includes(edition.type);

  const handleMove = React.useCallback((e) => {
    if (isMobile) return;
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top)  / rect.height - 0.5;
    el.style.transform = `perspective(700px) rotateX(${-y*8}deg) rotateY(${x*8}deg) translateZ(4px)`;
  }, [isMobile]);

  const handleLeave = React.useCallback(() => {
    const el = cardRef.current;
    if (!el) return;
    el.style.transition = 'transform .45s cubic-bezier(.23,1,.32,1)';
    el.style.transform = '';
    setTimeout(() => { if (el) el.style.transition = ''; }, 450);
  }, []);

  const coverH = size === 'xl' ? 400 : size === 'lg' ? 340 : size === 'sm' ? 210 : 280;
  const cardClass = `manga-card${edition.spotlight ? ' spotlight' : ''}${edition.type === 'ultra' ? ' foil-ultra' : ''}${edition.type === 'variant' ? ' foil-variant' : ''}`;

  const stockColors = {
    available: { bg:'var(--success-dim)', color:'var(--success)', dot:true },
    low:       { bg:'rgba(245,160,40,.15)', color:'var(--warning)', dot:true },
    preorder:  { bg:'var(--indigo-dim)',   color:'var(--indigo)',   dot:false },
    unavailable:{ bg:'var(--surface-3)',   color:'var(--text-muted)', dot:false },
  };
  const sc = stockColors[edition.stock] || stockColors.available;

  // Cover tint by type
  const coverTints = {
    kanzenban: 'linear-gradient(160deg,#1a1400,#251d00,#1a1400)',
    variant:   'linear-gradient(160deg,#12002a,#0a0a32,#22001a)',
    ultra:     'linear-gradient(160deg,#0a0020,#060818,#140028)',
    artbook:   'linear-gradient(160deg,#1a0030,#120a20,#1a0030)',
    boxset:    'linear-gradient(160deg,#001a1a,#001f1e,#001a1a)',
  };
  const coverBg = coverTints[edition.type] || null;

  return (
    <div
      ref={cardRef}
      className={cardClass}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      onClick={() => onClick && onClick(edition)}
      style={{ animation:'fadeUp .3s ease' }}
    >
      {/* Cover */}
      <div className="cover-ph" style={{ height: coverH, background: coverBg || undefined }}>
        <span style={{ color: coverBg ? 'rgba(255,255,255,.2)' : 'var(--text-muted)' }}>
          {edition.titleJp || edition.title}
        </span>
        {edition.type === 'kanzenban' && <div className="cover-foil-gold" />}
        {edition.type === 'variant'   && <div className="cover-foil-variant" />}
        {edition.type === 'ultra'     && <><div className="cover-foil-ultra" /><div className="cover-shine" /></>}
      </div>

      {/* Type badge */}
      <div style={{ position:'absolute', top:8, left:8, zIndex:5 }}>
        <div style={{
          padding:'2px 7px', borderRadius:'var(--r-full)',
          fontSize:8, fontWeight:800, letterSpacing:'.07em',
          textTransform:'uppercase', fontFamily:'var(--f-body)',
          background: isSpecial ? 'rgba(0,0,0,.55)' : t.bg,
          color: isSpecial ? '#fff' : t.color,
          border: isSpecial ? '1px solid rgba(255,255,255,.18)' : `1px solid ${t.border}`,
          backdropFilter:'blur(6px)',
        }}>
          {isSpecial && '✦ '}{t.label}
        </div>
      </div>

      {/* Country flag */}
      <div style={{ position:'absolute', top:8, right:8 }}>
        <Flag code={edition.country} size={14} />
      </div>

      {/* New badge */}
      {edition.isNew && (
        <div style={{
          position:'absolute', top:32, left:8,
          padding:'1px 6px', borderRadius:'var(--r-full)',
          fontSize:7, fontWeight:800, letterSpacing:'.08em',
          background:'var(--gold)', color:'var(--gold-text)',
          textTransform:'uppercase',
        }}>NUEVO</div>
      )}

      {/* Card info */}
      <div style={{ padding:'10px 12px 12px' }}>
        <div style={{
          fontSize: size === 'xl' ? 14 : 12,
          fontWeight:700, color:'var(--text)', lineHeight:1.3,
          marginBottom:2, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
        }}>{edition.title}</div>
        {edition.titleJp && (
          <div style={{ fontFamily:'var(--f-cjk)', fontSize:10, color:'var(--text-muted)', marginBottom:3, lineHeight:1.4 }}>
            {edition.titleJp}
          </div>
        )}
        <div style={{ fontSize:10, color:'var(--text-muted)', marginBottom:6 }}>
          {edition.publisher} · {edition.volumes} vols.
        </div>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
          <div style={{ fontSize:12, fontWeight:700, color:'var(--gold)' }}>
            {edition.priceMin ? `desde $${edition.priceMin}` : <span style={{ color:'var(--text-muted)', fontSize:10 }}>Sin precio</span>}
          </div>
          <div style={{
            fontSize:9, fontWeight:800, padding:'2px 6px',
            borderRadius:'var(--r-full)',
            background: edition.score >= 85 ? 'var(--success-dim)' : 'var(--surface-2)',
            color: edition.score >= 85 ? 'var(--success)' : 'var(--text-muted)',
            border:`1px solid ${edition.score >= 85 ? 'var(--success)' : 'var(--border)'}`,
          }}>{edition.score}</div>
        </div>
        {edition.limited && (
          <div style={{ marginTop:5, fontSize:9, fontWeight:700, color:'var(--r3)', display:'flex', alignItems:'center', gap:3, letterSpacing:'.05em', textTransform:'uppercase' }}>
            ◆ Tirada limitada
          </div>
        )}
      </div>
    </div>
  );
}

/* ═══ MOCK DATA ═══ */
const MOCK_EDITIONS = [
  { id:1,  title:'Berserk Kanzenban',      titleJp:'ベルセルク完全版',           type:'kanzenban', country:'JP', publisher:'Hakusensha', volumes:40, priceMin:112, stock:'available', score:97, isNew:false, spotlight:true,  limited:false },
  { id:2,  title:'Vinland Saga Deluxe',    titleJp:'ヴィンランド・サガ',          type:'deluxe',    country:'JP', publisher:'Kodansha',   volumes:11, priceMin:78,  stock:'low',       score:91, isNew:true,  spotlight:true,  limited:false },
  { id:3,  title:'One Piece Coffret',      titleJp:null,                          type:'boxset',    country:'FR', publisher:'Glénat',     volumes:12, priceMin:55,  stock:'available', score:84, isNew:false, spotlight:false, limited:false },
  { id:4,  title:'Chainsaw Man Box Set',   titleJp:'チェンソーマン',              type:'boxset',    country:'US', publisher:'Viz Media',  volumes:11, priceMin:89,  stock:'low',       score:88, isNew:false, spotlight:false, limited:false },
  { id:5,  title:'AoT Artbook Collection', titleJp:'進撃の巨人 画集',             type:'artbook',   country:'JP', publisher:'Kodansha',   volumes:3,  priceMin:45,  stock:'available', score:82, isNew:true,  spotlight:false, limited:false },
  { id:6,  title:'Dragon Ball Kanzenban',  titleJp:'ドラゴンボール完全版',        type:'kanzenban', country:'JP', publisher:'Shueisha',   volumes:34, priceMin:98,  stock:'available', score:94, isNew:false, spotlight:false, limited:false },
  { id:7,  title:'Akira Big Comic Deluxe', titleJp:'AKIRA',                       type:'deluxe',    country:'JP', publisher:'Kodansha',   volumes:6,  priceMin:180, stock:'low',       score:99, isNew:false, spotlight:false, limited:false },
  { id:8,  title:'Naruto Box Set',         titleJp:null,                          type:'boxset',    country:'US', publisher:'Viz Media',  volumes:27, priceMin:65,  stock:'available', score:79, isNew:false, spotlight:false, limited:false },
  { id:9,  title:'JoJo HC Vol. 1–4',      titleJp:'ジョジョの奇妙な冒険',       type:'deluxe',    country:'US', publisher:'Viz Media',  volumes:4,  priceMin:55,  stock:'available', score:85, isNew:false, spotlight:false, limited:false },
  { id:10, title:'Vagabond Deluxe',        titleJp:'バガボンド',                  type:'deluxe',    country:'JP', publisher:'Kodansha',   volumes:37, priceMin:95,  stock:'low',       score:98, isNew:false, spotlight:false, limited:false },
  { id:11, title:'Dungeon Meshi Artbook',  titleJp:'ダンジョン飯 ワールドガイド', type:'artbook',   country:'JP', publisher:'Enterbrain', volumes:1,  priceMin:35,  stock:'available', score:88, isNew:true,  spotlight:false, limited:false },
  { id:12, title:'Oshi no Ko Variant',     titleJp:'推しの子 特装版',             type:'variant',   country:'JP', publisher:'Shueisha',   volumes:1,  priceMin:28,  stock:'low',       score:86, isNew:true,  spotlight:false, limited:true  },
  { id:13, title:'Sailor Moon Kanzenban',  titleJp:'美少女戦士セーラームーン完全版',type:'kanzenban',country:'JP', publisher:'Kodansha',   volumes:12, priceMin:72,  stock:'available', score:87, isNew:false, spotlight:false, limited:false },
  { id:14, title:'Evangelion Coffret',     titleJp:null,                          type:'boxset',    country:'FR', publisher:'Glénat',     volumes:7,  priceMin:48,  stock:'available', score:81, isNew:false, spotlight:false, limited:false },
  { id:15, title:'FMA Box Set 3-in-1',     titleJp:null,                          type:'boxset',    country:'US', publisher:'Viz Media',  volumes:27, priceMin:58,  stock:'available', score:77, isNew:false, spotlight:false, limited:false },
  { id:16, title:'Trigun Maximum HC',      titleJp:'トライガンマキシマム',        type:'deluxe',    country:'US', publisher:'Dark Horse',  volumes:14, priceMin:42,  stock:'available', score:78, isNew:false, spotlight:false, limited:false },
  { id:17, title:'Blue Period Deluxe',     titleJp:'ブルーピリオド',              type:'deluxe',    country:'JP', publisher:'Kodansha',   volumes:15, priceMin:65,  stock:'low',       score:89, isNew:true,  spotlight:false, limited:false },
  { id:18, title:'Claymore HC Ultra',      titleJp:'クレイモア',                  type:'ultra',     country:'JP', publisher:'Shueisha',   volumes:1,  priceMin:320, stock:'low',       score:95, isNew:false, spotlight:false, limited:true  },
  { id:19, title:'Pluto Deluxe Edition',   titleJp:'プルートゥ',                  type:'deluxe',    country:'JP', publisher:'Shogakukan', volumes:8,  priceMin:62,  stock:'available', score:90, isNew:false, spotlight:false, limited:false },
  { id:20, title:'Spy x Family Box Set',   titleJp:'SPY×FAMILY',                 type:'boxset',    country:'US', publisher:'Viz Media',  volumes:12, priceMin:52,  stock:'available', score:76, isNew:true,  spotlight:false, limited:false },
];

const NEW_DETECTIONS = [
  ...MOCK_EDITIONS.filter(e => e.isNew),
  ...MOCK_EDITIONS.filter(e => e.type === 'ultra' || e.type === 'variant'),
].filter((e, i, arr) => arr.findIndex(x => x.id === e.id) === i).slice(0, 7);

/* Export */
Object.assign(window, {
  PWLogo, Flag, Chip, RarityBadge, MangaCard,
  TIER_META, MOCK_EDITIONS, NEW_DETECTIONS,
});
