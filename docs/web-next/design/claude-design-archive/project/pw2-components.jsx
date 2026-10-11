/* ═══════════════════════════════════════════
   PW2-COMPONENTS.JSX — v2 shared primitives
   Two-axis: FORMAT (flat chips) + RARITY (static foil)
   isCJK · FORMAT_META · RARITY_META
   PWLogo · Flag · Chip · FormatBadge · RarityBadge
   ProximamenteBadge · StackedWrapper · MangaCard
   MOCK_EDITIONS · NEW_DETECTIONS
═══════════════════════════════════════════ */

/* ── CJK script detection ── */
function isCJK(text) {
  if (!text) return false;
  return /[\u3000-\u9fff\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uff00-\uffef]/.test(text);
}

/* ── AXIS 1: FORMAT CATEGORIES (multi-value, flat, no foil) ── */
const FORMAT_META = {
  standard:  { label:'Standard',  color:'#788399', bg:'rgba(120,131,153,.15)', border:'rgba(120,131,153,.32)' },
  deluxe:    { label:'Deluxe',    color:'#D48A0C', bg:'rgba(212,138,12,.15)',  border:'rgba(212,138,12,.40)' },
  limited:   { label:'Limited',   color:'#E05830', bg:'rgba(224,88,48,.15)',   border:'rgba(224,88,48,.38)' },
  boxset:    { label:'Box Set',   color:'#0CA99E', bg:'rgba(12,169,158,.15)',  border:'rgba(12,169,158,.38)' },
  artbook:   { label:'Artbook',   color:'#9540E6', bg:'rgba(149,64,230,.15)',  border:'rgba(149,64,230,.38)' },
  kanzenban: { label:'Kanzenban', color:'#C8951C', bg:'rgba(200,149,28,.15)',  border:'rgba(200,149,28,.44)' },
  variant:   { label:'Variant',   color:'#C46BFF', bg:'rgba(196,107,255,.15)', border:'rgba(196,107,255,.42)' },
  omnibus:   { label:'Omnibus',   color:'#7A9CC0', bg:'rgba(122,156,192,.15)', border:'rgba(122,156,192,.38)' },
};

/* ── AXIS 2: RARITY TIERS (single value, static visual state + one-shot shine) ── */
const RARITY_META = {
  rare: {
    label:'Rare', icon:'◆',
    badgeColor:'#F5C242', badgeBg:'rgba(245,194,66,.13)', badgeBorder:'rgba(245,194,66,.52)',
    cardBorder:'rgba(245,194,66,.48)',
    cardShadow:'0 0 0 1px rgba(245,194,66,.08), 0 4px 22px rgba(245,194,66,.2), 0 2px 8px rgba(0,0,0,.42)',
    coverClass:'cover-rarity-rare',
    shineDuration:'.4s', shinePeak:.40,
  },
  super_rare: {
    label:'Super Rare', icon:'◆◆',
    badgeColor:'#FFB84A', badgeBg:'rgba(255,184,74,.13)', badgeBorder:'rgba(255,184,74,.52)',
    cardBorder:'rgba(240,160,40,.65)',
    cardShadow:'0 0 0 1px rgba(255,160,60,.10), 0 4px 28px rgba(220,140,40,.28), 0 2px 8px rgba(0,0,0,.46)',
    coverClass:'cover-rarity-super',
    shineDuration:'.5s', shinePeak:.60,
  },
  ultra_rare: {
    label:'Ultra Rare', icon:'✦',
    badgeColor:'#C46BFF', badgeBg:'rgba(196,107,255,.13)', badgeBorder:'rgba(196,107,255,.52)',
    cardBorder:'rgba(196,107,255,.52)',
    cardShadow:'0 0 0 1.5px rgba(196,107,255,.18), 0 4px 32px rgba(196,107,255,.44), 0 0 56px rgba(100,140,255,.1), 0 2px 8px rgba(0,0,0,.5)',
    coverClass:'cover-rarity-ultra',
    shineDuration:'.6s', shinePeak:.85,
  },
};

/* ── Logo ── */
function PWLogo({ size=32, showWordmark=false, wordmarkVariant='panda', onDark=null }) {
  const body = onDark===null?'var(--logo-body)':onDark===true?'#E8ECF8':'#FFFFFF';
  const ink  = onDark===null?'var(--logo-patch)':onDark===true?'#0C1628':'#111A38';
  const txt  = onDark!==null?(onDark?'#E8ECF8':'#111A38'):'var(--text)';
  return (
    <div style={{display:'flex',alignItems:'center',gap:size*.28}}>
      <svg width={size} height={size} viewBox="0 0 56 56" fill="none"
        style={onDark===false?{filter:'drop-shadow(0 1px 3px rgba(0,0,0,.10))'}:undefined}>
        <circle cx="11" cy="13" r="9" fill={ink}/>
        <circle cx="45" cy="13" r="9" fill={ink}/>
        <circle cx="28" cy="31" r="21" fill={body}/>
        <ellipse cx="18" cy="27" rx="9.5" ry="8.5" transform="rotate(-9 18 27)" fill={ink}/>
        <ellipse cx="38" cy="27" rx="9.5" ry="8.5" transform="rotate(9 38 27)" fill={ink}/>
        <circle cx="17.5" cy="27" r="4" fill={body}/>
        <circle cx="38.5" cy="27" r="4" fill={body}/>
        <circle cx="18" cy="27.5" r="2.1" fill={ink}/>
        <circle cx="16.8" cy="26.2" r=".9" fill={body} opacity=".55"/>
        <path d="M38.5 25.1L39.2 26.8L41 27.3L39.2 27.9L38.5 29.5L37.8 27.9L36 27.3L37.8 26.8Z" fill={ink}/>
        <circle cx="38.5" cy="27.3" r=".95" fill="#F5C242"/>
        <ellipse cx="28" cy="36" rx="3.2" ry="2.2" fill={ink} opacity=".85"/>
        <path d="M25.6 38Q28 39.8 30.4 38" stroke={ink} strokeWidth="1.1" strokeLinecap="round" fill="none" opacity=".38"/>
      </svg>
      {showWordmark && (
        <div style={{fontFamily:'var(--f-display)',fontWeight:800,fontSize:size*.5,letterSpacing:'-.03em',lineHeight:1,userSelect:'none'}}>
          {wordmarkVariant==='panda'
            ? <><span style={{color:txt}}>Panda</span><span style={{color:'#F5C242'}}>Watch</span></>
            : <><span style={{color:txt}}>Manga</span><span style={{color:'var(--text-sec)',fontWeight:700}}>Watch</span></>
          }
        </div>
      )}
    </div>
  );
}

/* ── Flag ── */
function Flag({ code, size=15 }) {
  const f={JP:'🇯🇵',FR:'🇫🇷',US:'🇺🇸',ES:'🇪🇸',IT:'🇮🇹',BR:'🇧🇷',DE:'🇩🇪',UK:'🇬🇧',KR:'🇰🇷',MX:'🇲🇽',AR:'🇦🇷',CA:'🇨🇦'};
  return <span style={{fontSize:size,lineHeight:1}}>{f[code]||'🌐'}</span>;
}

/* ── Chip ── */
function Chip({ label, selected, onClick, flag, icon, color }) {
  return (
    <div onClick={onClick} style={{
      display:'inline-flex',alignItems:'center',gap:5,
      padding:'5px 11px',borderRadius:'var(--r-full)',
      fontSize:12,fontWeight:600,fontFamily:'var(--f-body)',
      cursor:'pointer',userSelect:'none',whiteSpace:'nowrap',transition:'all .12s',
      border:`1px solid ${selected?(color||'var(--gold)'):'var(--border-md)'}`,
      background:selected?(color?color+'22':'var(--gold-dim)'):'var(--surface-2)',
      color:selected?(color||'var(--gold)'):'var(--text-sec)',
    }}
    onMouseEnter={e=>{if(!selected){e.currentTarget.style.color='var(--text)';e.currentTarget.style.borderColor='var(--border-lg)';}}}
    onMouseLeave={e=>{if(!selected){e.currentTarget.style.color='var(--text-sec)';e.currentTarget.style.borderColor='var(--border-md)';}}}
    >
      {flag&&<Flag code={flag} size={12}/>}
      {icon&&<span style={{fontSize:12}}>{icon}</span>}
      <span>{label}</span>
    </div>
  );
}

/* ── Format Badge — flat, no animation (Axis 1) ── */
function FormatBadge({ type, size='sm' }) {
  const m=FORMAT_META[type]||FORMAT_META.standard;
  return (
    <div style={{
      display:'inline-flex',alignItems:'center',
      padding:size==='sm'?'2px 7px':'3px 10px',
      borderRadius:'var(--r-full)',
      fontSize:size==='sm'?9:11,fontWeight:700,letterSpacing:'.05em',
      textTransform:'uppercase',fontFamily:'var(--f-body)',
      background:m.bg,color:m.color,border:`1px solid ${m.border}`,
      whiteSpace:'nowrap',backdropFilter:'blur(4px)',
    }}>{m.label}</div>
  );
}

/* ── Rarity Badge — static visual, no loop (Axis 2) ── */
function RarityBadge({ tier, size='sm' }) {
  if (!tier) return null;
  const m=RARITY_META[tier]; if (!m) return null;
  const fs=size==='sm'?9:11;
  return (
    <div style={{
      display:'inline-flex',alignItems:'center',gap:3,
      padding:size==='sm'?'2px 7px':'3px 10px',
      borderRadius:'var(--r-full)',
      fontSize:fs,fontWeight:800,letterSpacing:'.06em',
      textTransform:'uppercase',fontFamily:'var(--f-body)',
      background:m.badgeBg,color:m.badgeColor,border:`1px solid ${m.badgeBorder}`,
      whiteSpace:'nowrap',
    }}>
      <span style={{fontSize:fs-1}}>{m.icon}</span>{m.label}
    </div>
  );
}

/* ── Consistent "Próximamente" badge ── */
function ProximamenteBadge() {
  return (
    <span style={{
      display:'inline-flex',alignItems:'center',
      fontSize:9,fontWeight:800,letterSpacing:'.07em',textTransform:'uppercase',
      fontFamily:'var(--f-body)',background:'var(--indigo-dim)',
      color:'var(--indigo)',border:'1px solid var(--indigo)',
      borderRadius:'var(--r-full)',padding:'1px 7px',whiteSpace:'nowrap',
    }}>Próximamente</span>
  );
}

/* ── Stacked card wrapper — multi-tome paper stack effect ── */
function StackedWrapper({ isMultiTome, children }) {
  if (!isMultiTome) return <>{children}</>;
  return (
    <div style={{position:'relative',marginTop:7,marginRight:7}}>
      <div style={{position:'absolute',inset:0,zIndex:0,borderRadius:'var(--r-lg)',
        transform:'translate(7px,-7px)',background:'var(--surface-3)',border:'1px solid var(--border)',opacity:.65}}/>
      <div style={{position:'absolute',inset:0,zIndex:1,borderRadius:'var(--r-lg)',
        transform:'translate(3.5px,-3.5px)',background:'var(--surface-2)',border:'1px solid var(--border)',opacity:.82}}/>
      <div style={{position:'relative',zIndex:2}}>{children}</div>
    </div>
  );
}

/* ── Cover tints by primary format ── */
const COVER_TINTS = {
  kanzenban:'linear-gradient(160deg,#1a1400,#251d00,#1a1400)',
  variant:'linear-gradient(160deg,#12002a,#0a0a32,#22001a)',
  artbook:'linear-gradient(160deg,#1a0030,#120a20,#1a0030)',
  boxset:'linear-gradient(160deg,#001a1a,#001f1e,#001a1a)',
  deluxe:'linear-gradient(160deg,#1a1200,#1f1600,#1a1200)',
  limited:'linear-gradient(160deg,#200a08,#1c0a08,#200a08)',
  omnibus:'linear-gradient(160deg,#0a1020,#0e1428,#0a1020)',
  ultra_rare_bg:'linear-gradient(160deg,#0a0020,#060818,#140028)',
};

/* ── Manga Card ── */
function MangaCard({ edition, onClick, size='md', isMobile, shineIndex=0 }) {
  const cardRef = React.useRef(null);
  const coolRef = React.useRef(false);
  const rm = RARITY_META[edition.rarityTier];
  const formats = edition.formatTypes||['standard'];
  const coverH = size==='xl'?400:size==='lg'?340:size==='sm'?210:280;
  const pf = formats[0]||'standard';
  const coverBg = rm?.shinePeak===.85 ? COVER_TINTS.ultra_rare_bg : (COVER_TINTS[pf]||null);

  /* One-shot shine system */
  React.useEffect(()=>{
    const el=cardRef.current;
    if (!el||!edition.rarityTier) return;
    if (window.matchMedia('(prefers-reduced-motion:reduce)').matches) return;
    const trigger=(delay=0)=>{
      setTimeout(()=>{
        if (!el) return;
        el.style.setProperty('--shine-duration',rm.shineDuration);
        el.style.setProperty('--shine-peak',rm.shinePeak);
        el.classList.add('shine-active');
        const done=()=>el.classList.remove('shine-active');
        el.addEventListener('animationend',done,{once:true});
        setTimeout(done,(parseFloat(rm.shineDuration)*1000)+200);
      },delay);
    };
    const obs=new IntersectionObserver(([e])=>{
      if(e.isIntersecting){trigger(shineIndex*80);obs.disconnect();}
    },{threshold:.3});
    obs.observe(el);
    const onEnter=()=>{
      if(coolRef.current) return;
      coolRef.current=true; trigger(0);
      setTimeout(()=>{coolRef.current=false;},1500);
    };
    el.addEventListener('mouseenter',onEnter);
    return()=>{obs.disconnect();el.removeEventListener('mouseenter',onEnter);};
  },[edition.rarityTier,shineIndex]);

  /* Tilt + shine-position tracking */
  const onMove=React.useCallback((e)=>{
    if(isMobile) return;
    const el=cardRef.current; if(!el) return;
    const r=el.getBoundingClientRect();
    const x=(e.clientX-r.left)/r.width,y=(e.clientY-r.top)/r.height;
    el.style.transform=`perspective(700px) rotateX(${-(y-.5)*8}deg) rotateY(${(x-.5)*8}deg) translateZ(4px)`;
    el.style.setProperty('--shine-x',x);
    el.style.setProperty('--shine-y',y);
  },[isMobile]);

  const onLeave=React.useCallback(()=>{
    const el=cardRef.current; if(!el) return;
    el.style.transition='transform .45s cubic-bezier(.23,1,.32,1)';
    el.style.transform='';
    setTimeout(()=>{if(el)el.style.transition='';},450);
  },[]);

  return (
    <StackedWrapper isMultiTome={edition.isMultiTome&&(edition.volumes||0)>1}>
      <div ref={cardRef} onMouseMove={onMove} onMouseLeave={onLeave}
        onClick={()=>onClick&&onClick(edition)}
        style={{
          background:'var(--surface)',borderRadius:'var(--r-lg)',overflow:'hidden',
          border:rm?`1.5px solid ${rm.cardBorder}`:'1px solid var(--border)',
          boxShadow:rm?rm.cardShadow:'var(--sh-sm)',
          cursor:'pointer',position:'relative',
          transition:'box-shadow .2s,border-color .2s',
          animation:'fadeUp .3s ease',
        }}>

        {/* Cover area */}
        <div style={{height:coverH,position:'relative',overflow:'hidden',
          background:coverBg||'repeating-linear-gradient(45deg,var(--surface-2),var(--surface-2) 3px,var(--surface-3) 3px,var(--surface-3) 6px)',
          display:'flex',alignItems:'flex-end',justifyContent:'center',paddingBottom:8,
        }}>
          <span style={{fontSize:8,fontWeight:600,letterSpacing:'.08em',textTransform:'uppercase',
            color:coverBg?'rgba(255,255,255,.18)':'var(--text-muted)',position:'relative',zIndex:2,
            fontFamily:isCJK(edition.title_original)?'var(--f-cjk)':'var(--f-body)',
          }}>
            {isCJK(edition.title_original)?edition.title_original:(edition.title_original||edition.title)}
          </span>
          {rm&&<div className={rm.coverClass}/>}
          {rm&&<div className="cover-shine-beam"/>}
        </div>

        {/* Format chips — top-left, flat */}
        <div style={{position:'absolute',top:8,left:8,zIndex:5,display:'flex',flexWrap:'wrap',gap:3,maxWidth:'68%'}}>
          {formats.slice(0,2).map(f=><FormatBadge key={f} type={f} size="sm"/>)}
          {formats.length>2&&<div style={{padding:'2px 5px',borderRadius:'var(--r-full)',fontSize:8,fontWeight:700,background:'var(--surface-2)',color:'var(--text-muted)',border:'1px solid var(--border)'}}>+{formats.length-2}</div>}
        </div>

        {/* Country + rarity — top-right */}
        <div style={{position:'absolute',top:8,right:8,zIndex:5,display:'flex',flexDirection:'column',alignItems:'flex-end',gap:3}}>
          <Flag code={edition.country} size={14}/>
          {rm&&<RarityBadge tier={edition.rarityTier} size="sm"/>}
        </div>

        {/* NEW badge */}
        {edition.isNew&&(
          <div style={{position:'absolute',top:rm?34:28,left:8,zIndex:5,padding:'1px 6px',borderRadius:'var(--r-full)',fontSize:7,fontWeight:800,letterSpacing:'.08em',background:'var(--gold)',color:'var(--gold-text)',textTransform:'uppercase'}}>NUEVO</div>
        )}

        {/* Card info */}
        <div style={{padding:'10px 12px 12px'}}>
          <div style={{fontSize:12,fontWeight:700,color:'var(--text)',lineHeight:1.3,marginBottom:2,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{edition.title}</div>
          {edition.title_original&&edition.title_original!==edition.title&&(
            <div style={{fontFamily:isCJK(edition.title_original)?'var(--f-cjk)':'var(--f-body)',fontSize:10,color:'var(--text-muted)',marginBottom:3,lineHeight:1.4,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{edition.title_original}</div>
          )}
          <div style={{fontSize:10,color:'var(--text-muted)',marginBottom:6}}>{edition.publisher}{edition.volumes>1?` · ${edition.volumes} vols.`:''}</div>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between'}}>
            <div style={{fontSize:11,fontWeight:700,color:rm?rm.badgeColor:'var(--gold)'}}>
              {edition.price||<span style={{color:'var(--text-muted)',fontSize:10,fontWeight:400}}>Sin precio</span>}
            </div>
            <div style={{fontSize:9,fontWeight:800,padding:'2px 6px',borderRadius:'var(--r-full)',
              background:edition.score>=85?'var(--success-dim)':'var(--surface-2)',
              color:edition.score>=85?'var(--success)':'var(--text-muted)',
              border:`1px solid ${edition.score>=85?'var(--success)':'var(--border)'}`}}>{edition.score}</div>
          </div>
          {edition.stock_type==='limited'&&(
            <div style={{marginTop:4,fontSize:9,fontWeight:700,color:'var(--r3)',letterSpacing:'.04em',textTransform:'uppercase'}}>◆ Tirada limitada</div>
          )}
        </div>
      </div>
    </StackedWrapper>
  );
}

/* ═══ MOCK DATA v2 — two-axis system ═══ */
const MOCK_EDITIONS = [
  { id:1,  title:'Berserk Kanzenban',       title_original:'ベルセルク完全版',              formatTypes:['kanzenban'],         rarityTier:null,         printRun:null, country:'JP', publisher:'Hakusensha',  volumes:40, price:'¥3,200',       stock_type:'available', score:97, isNew:false, isMultiTome:true  },
  { id:2,  title:'Vinland Saga Deluxe',     title_original:'ヴィンランド・サガ',            formatTypes:['deluxe'],            rarityTier:null,         printRun:null, country:'JP', publisher:'Kodansha',    volumes:11, price:'$78.00 USD',    stock_type:'available', score:91, isNew:true,  isMultiTome:true  },
  { id:3,  title:'One Piece Coffret',       title_original:null,                            formatTypes:['boxset'],            rarityTier:'rare',       printRun:null, country:'FR', publisher:'Glénat',      volumes:12, price:'desde 55€',     stock_type:'limited',   score:84, isNew:false, isMultiTome:true  },
  { id:4,  title:'Chainsaw Man Box Set',    title_original:'チェンソーマン',               formatTypes:['boxset'],            rarityTier:null,         printRun:null, country:'US', publisher:'Viz Media',   volumes:11, price:'$89.00 USD',    stock_type:'available', score:88, isNew:false, isMultiTome:true  },
  { id:5,  title:'AoT Artbook Collection',  title_original:'進撃の巨人 画集',              formatTypes:['artbook'],           rarityTier:null,         printRun:null, country:'JP', publisher:'Kodansha',    volumes:3,  price:'¥4,500',        stock_type:'available', score:82, isNew:true,  isMultiTome:false },
  { id:6,  title:'Dragon Ball Kanzenban',   title_original:'ドラゴンボール完全版',         formatTypes:['kanzenban'],         rarityTier:null,         printRun:null, country:'JP', publisher:'Shueisha',    volumes:34, price:'¥3,080',        stock_type:'available', score:94, isNew:false, isMultiTome:true  },
  { id:7,  title:'Akira Big Comic Deluxe',  title_original:'AKIRA',                         formatTypes:['deluxe'],            rarityTier:'super_rare', printRun:300,  country:'JP', publisher:'Kodansha',    volumes:6,  price:'desde ¥12,000', stock_type:'limited',   score:99, isNew:false, isMultiTome:true  },
  { id:8,  title:'Naruto Box Set',          title_original:null,                            formatTypes:['boxset'],            rarityTier:null,         printRun:null, country:'US', publisher:'Viz Media',   volumes:27, price:'$65.00 USD',    stock_type:'available', score:79, isNew:false, isMultiTome:true  },
  { id:9,  title:'JoJo HC Omnibus',         title_original:'ジョジョの奇妙な冒険',         formatTypes:['omnibus','deluxe'],  rarityTier:null,         printRun:null, country:'US', publisher:'Viz Media',   volumes:4,  price:'$55.00 USD',    stock_type:'available', score:85, isNew:false, isMultiTome:true  },
  { id:10, title:'Vagabond Deluxe',         title_original:'バガボンド',                    formatTypes:['deluxe'],            rarityTier:'rare',       printRun:null, country:'JP', publisher:'Kodansha',    volumes:37, price:'desde ¥4,800',  stock_type:'limited',   score:98, isNew:false, isMultiTome:true  },
  { id:11, title:'Dungeon Meshi Artbook',   title_original:'ダンジョン飯 ワールドガイド',  formatTypes:['artbook'],           rarityTier:null,         printRun:null, country:'JP', publisher:'Enterbrain',  volumes:1,  price:'¥3,800',        stock_type:'available', score:88, isNew:true,  isMultiTome:false },
  { id:12, title:'Oshi no Ko Variant',      title_original:'推しの子 特装版',              formatTypes:['variant'],           rarityTier:'super_rare', printRun:500,  country:'JP', publisher:'Shueisha',    volumes:1,  price:'¥8,500',        stock_type:'limited',   score:86, isNew:true,  isMultiTome:false },
  { id:13, title:'Sailor Moon Kanzenban',   title_original:'美少女戦士セーラームーン完全版',formatTypes:['kanzenban'],         rarityTier:null,         printRun:null, country:'JP', publisher:'Kodansha',    volumes:12, price:'¥2,860',        stock_type:'available', score:87, isNew:false, isMultiTome:true  },
  { id:14, title:'Evangelion Coffret',      title_original:null,                            formatTypes:['boxset'],            rarityTier:null,         printRun:null, country:'FR', publisher:'Glénat',      volumes:7,  price:'48€',           stock_type:'available', score:81, isNew:false, isMultiTome:true  },
  { id:15, title:'FMA Box Set Omnibus',     title_original:null,                            formatTypes:['omnibus','boxset'],  rarityTier:null,         printRun:null, country:'US', publisher:'Viz Media',   volumes:27, price:'$58.00 USD',    stock_type:'available', score:77, isNew:false, isMultiTome:true  },
  { id:16, title:'Blue Period Deluxe',      title_original:'ブルーピリオド',                formatTypes:['deluxe'],            rarityTier:'rare',       printRun:null, country:'JP', publisher:'Kodansha',    volumes:15, price:'¥3,520',        stock_type:'limited',   score:89, isNew:true,  isMultiTome:true  },
  { id:17, title:'Claymore HC — Firmado',   title_original:'クレイモア',                   formatTypes:['deluxe','limited'],  rarityTier:'ultra_rare', printRun:null, country:'JP', publisher:'Shueisha',    volumes:1,  price:'~¥85,000',      stock_type:'limited',   score:95, isNew:false, isMultiTome:false },
  { id:18, title:'Pluto Deluxe Edition',    title_original:'プルートゥ',                    formatTypes:['deluxe'],            rarityTier:null,         printRun:null, country:'JP', publisher:'Shogakukan',  volumes:8,  price:'¥3,200',        stock_type:'available', score:90, isNew:false, isMultiTome:true  },
  { id:19, title:'Spy x Family Box Set',    title_original:'SPY×FAMILY',                   formatTypes:['boxset'],            rarityTier:null,         printRun:null, country:'US', publisher:'Viz Media',   volumes:12, price:'$52.00 USD',    stock_type:'available', score:76, isNew:true,  isMultiTome:true  },
  { id:20, title:'JJK Variant — Exclusiva', title_original:'呪術廻戦 作家版',              formatTypes:['variant','limited'], rarityTier:'ultra_rare', printRun:150,  country:'JP', publisher:'Shueisha',    volumes:1,  price:'~¥60,000',      stock_type:'limited',   score:92, isNew:false, isMultiTome:false },
  { id:21, title:'Mugen no Juunin Kanzenban',title_original:'無限の住人 完全版',            formatTypes:['kanzenban'],         rarityTier:'ultra_rare', printRun:75,   country:'JP', publisher:'Kodansha',    volumes:1,  price:'~¥120,000',     stock_type:'limited',   score:94, isNew:false, isMultiTome:false },
  { id:22, title:"Les Carnets Apothicaire", title_original:'薬屋のひとりごと',              formatTypes:['standard'],          rarityTier:'super_rare', printRun:350,  country:'FR', publisher:'Kurokawa',    volumes:1,  price:'42€',           stock_type:'limited',   score:88, isNew:false, isMultiTome:false },
];

const NEW_DETECTIONS = [
  ...MOCK_EDITIONS.filter(e=>e.isNew),
  ...MOCK_EDITIONS.filter(e=>e.rarityTier==='ultra_rare'||e.rarityTier==='super_rare'),
].filter((e,i,a)=>a.findIndex(x=>x.id===e.id)===i).slice(0,8);

Object.assign(window, {
  isCJK, FORMAT_META, RARITY_META, COVER_TINTS,
  PWLogo, Flag, Chip, FormatBadge, RarityBadge, ProximamenteBadge,
  StackedWrapper, MangaCard,
  MOCK_EDITIONS, NEW_DETECTIONS,
});
