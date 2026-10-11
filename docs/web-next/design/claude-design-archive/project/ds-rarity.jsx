/* ═══════════════════════════════════════════
   DS-RARITY.JSX — PandaWatch Rarity System
   Categories + Special Status Markers
   Foil effects live on the CARD COVER AREA
═══════════════════════════════════════════ */

/* ═══ RARITY CSS ═══ */
const RARITY_STYLES = `
@keyframes goldSweep {
  0%   { background-position: -200% center; }
  100% { background-position:  200% center; }
}
@keyframes rainbowFlow {
  0%   { background-position: 0% 50%;   filter: hue-rotate(0deg)   saturate(1.4) brightness(1.1); }
  50%  { background-position: 100% 50%; filter: hue-rotate(180deg) saturate(1.6) brightness(1.2); }
  100% { background-position: 0% 50%;   filter: hue-rotate(360deg) saturate(1.4) brightness(1.1); }
}
@keyframes holoFull {
  0%   { background-position: 0%   0%;   filter: hue-rotate(0deg)   brightness(1.1) saturate(1.5); }
  25%  { background-position: 100% 50%;  filter: hue-rotate(90deg)  brightness(1.3) saturate(1.8); }
  50%  { background-position: 100% 100%; filter: hue-rotate(180deg) brightness(1.4) saturate(2.0); }
  75%  { background-position: 0%   50%;  filter: hue-rotate(270deg) brightness(1.3) saturate(1.8); }
  100% { background-position: 0%   0%;   filter: hue-rotate(360deg) brightness(1.1) saturate(1.5); }
}
@keyframes shinePass {
  0%   { left: -80%; opacity: 0; }
  15%  { opacity: 1; }
  85%  { opacity: 1; }
  100% { left: 160%; opacity: 0; }
}

/* ── Badge animations (reference table only) ── */
.badge-kanzenban {
  background: linear-gradient(90deg,
    #9A6800 0%, #C8951C 20%, #F5C242 40%,
    #FFF0A0 52%, #F5C242 64%, #C8951C 80%, #9A6800 100%);
  background-size: 200% 100%;
  animation: goldSweep 2.4s ease-in-out infinite;
  color: #1A1000 !important;
  text-shadow: 0 1px 0 rgba(255,255,255,0.3);
  border-color: transparent !important;
}
.badge-variant {
  background: linear-gradient(90deg,
    hsl(0,90%,62%), hsl(40,90%,58%), hsl(80,85%,52%),
    hsl(160,90%,48%), hsl(200,90%,58%), hsl(255,90%,66%),
    hsl(300,85%,60%), hsl(340,90%,60%), hsl(0,90%,62%));
  background-size: 300% 300%;
  animation: rainbowFlow 3.5s linear infinite;
  color: #fff !important;
  text-shadow: 0 1px 3px rgba(0,0,0,0.45);
  border-color: transparent !important;
  box-shadow: 0 2px 12px rgba(180,100,255,0.4) !important;
}
.badge-ultra {
  background: linear-gradient(135deg,
    hsl(0,100%,65%) 0%, hsl(60,100%,60%) 14%, hsl(120,90%,55%) 28%,
    hsl(180,100%,52%) 42%, hsl(220,100%,62%) 57%,
    hsl(270,100%,65%) 71%, hsl(320,100%,62%) 86%, hsl(0,100%,65%) 100%);
  background-size: 400% 400%;
  animation: holoFull 2.8s ease-in-out infinite;
  color: #fff !important;
  text-shadow: 0 1px 4px rgba(0,0,0,0.55);
  border-color: transparent !important;
  position: relative; overflow: hidden;
  box-shadow: 0 2px 16px rgba(200,120,255,0.5), 0 0 32px rgba(100,150,255,0.2) !important;
}
.badge-ultra::after {
  content: '';
  position: absolute; top: -100%; left: -80%;
  width: 50%; height: 300%;
  background: linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.55) 50%, transparent 70%);
  animation: shinePass 2.8s ease-in-out infinite;
  pointer-events: none;
}

/* ── Cover foil overlays (the real shimmer lives here) ── */
.cover-foil-gold {
  position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
  background: linear-gradient(120deg,
    transparent 15%, rgba(245,194,66,0.55) 38%,
    rgba(255,245,150,0.75) 50%, rgba(245,194,66,0.55) 62%, transparent 85%);
  background-size: 200% 100%;
  animation: goldSweep 2.4s ease-in-out infinite;
  mix-blend-mode: overlay;
}
.cover-foil-variant {
  position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
  background: linear-gradient(135deg,
    hsl(0,90%,62%), hsl(50,90%,60%), hsl(120,85%,55%),
    hsl(180,90%,52%), hsl(240,90%,62%), hsl(300,90%,60%), hsl(0,90%,62%));
  background-size: 400% 400%;
  animation: rainbowFlow 3s linear infinite;
  opacity: 0.32; mix-blend-mode: screen;
}
.cover-foil-ultra {
  position: absolute; inset: 0; pointer-events: none; border-radius: inherit;
  background: linear-gradient(135deg,
    hsl(0,100%,65%), hsl(60,100%,60%), hsl(120,90%,55%),
    hsl(180,100%,52%), hsl(220,100%,62%), hsl(270,100%,65%),
    hsl(320,100%,62%), hsl(0,100%,65%));
  background-size: 400% 400%;
  animation: holoFull 2.5s linear infinite;
  opacity: 0.42; mix-blend-mode: screen;
}
.cover-shine {
  position: absolute; top: -100%; left: -80%; pointer-events: none;
  width: 40%; height: 300%;
  background: linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.45) 50%, transparent 70%);
  animation: shinePass 2.5s ease-in-out infinite;
}
`;

/* ═══ TIER DATA — Categories + Special Status ═══ */
const TIERS = [
  {
    rank: 1, key: 'standard', name: 'Standard', nameEs: 'Estándar',
    color: '#788399', bg: 'rgba(120,131,153,0.14)', border: 'rgba(120,131,153,0.30)', textColor: '#788399',
    desc: 'Tapa blanda estándar, sin acabados especiales. Formato base del catálogo.',
    examples: 'Tankōbon regular · Edición española de bolsillo · Tomos de kiosko',
    availability: 'Fácilmente disponible', effect: 'Sin efecto visual', cssClass: null,
    special: false,
  },
  {
    rank: 2, key: 'deluxe', name: 'Deluxe', nameEs: 'Deluxe / HC',
    color: '#D48A0C', bg: 'rgba(212,138,12,0.14)', border: 'rgba(212,138,12,0.35)', textColor: '#D48A0C',
    desc: 'Tapa dura, papel mejorado, sobrecubierta o laminado especial. La entrada al mundo premium.',
    examples: 'Hardcover · Tapa dura con sobrecubierta · Édition grand format',
    availability: 'Stock regular', effect: 'Tono dorado cálido', cssClass: null,
    special: false,
  },
  {
    rank: 3, key: 'limited', name: 'Limited', nameEs: 'Limitada',
    color: '#E05830', bg: 'rgba(224,88,48,0.14)', border: 'rgba(224,88,48,0.35)', textColor: '#E05830',
    desc: 'Tirada acotada — puede agotarse sin reimpresión. La tensión de la cacería empieza aquí.',
    examples: 'Edición numerada · Print run limitada · Kickstarter exclusive',
    availability: 'Stock sensible al tiempo', effect: 'Rojo-ámbar urgente', cssClass: null,
    special: false,
  },
  {
    rank: 4, key: 'boxset', name: 'Box Set', nameEs: 'Box Set / Estuche',
    color: '#0CA99E', bg: 'rgba(12,169,158,0.14)', border: 'rgba(12,169,158,0.35)', textColor: '#0CA99E',
    desc: 'Colección de tomos en estuche o caja coleccionista. Saga completa en un objeto.',
    examples: 'Slipcase box set · Coffret intégrale · Complete series box',
    availability: 'Tiradas periódicas', effect: 'Teal — agua profunda', cssClass: null,
    special: false,
  },
  {
    rank: 5, key: 'artbook', name: 'Artbook', nameEs: 'Artbook / Fanbook',
    color: '#9540E6', bg: 'rgba(149,64,230,0.14)', border: 'rgba(149,64,230,0.35)', textColor: '#9540E6',
    desc: 'Libros de arte, guías visuales, fanbooks y material suplementario de alta calidad.',
    examples: 'The Art of · Illustration collection · Visual guide oficial',
    availability: 'Especialidad, tiraje bajo', effect: 'Violeta — singularidad', cssClass: null,
    special: false,
  },
  {
    rank: 6, key: 'kanzenban', name: 'Kanzenban', nameEs: 'Kanzenban / Integral',
    color: '#F5C242', bg: 'rgba(245,194,66,0.15)', border: '#F5C242', textColor: '#1A1000',
    desc: 'Edición definitiva y completa. Re-encuadernada en grandes volúmenes con los mejores extras. La versión más cuidada de una obra.',
    examples: 'Kanzenban JP · Édition intégrale FR · Complete omnibus',
    availability: 'Reimpresiones frecuentes (JP)', effect: '✦ Gold sweep — portada con reflejo dorado', cssClass: 'badge-kanzenban',
    special: true,
  },
  {
    rank: 7, key: 'variant', name: 'Variant', nameEs: 'Variant Cover',
    color: '#C46BFF', bg: 'rgba(196,107,255,0.15)', border: '#C46BFF', textColor: '#fff',
    desc: 'Portada alternativa — exclusiva de retailer, del artista, o de evento. Cada variante es una versión distinta del mismo libro.',
    examples: 'Retailer exclusive · Artist variant · Convention cover',
    availability: 'Por evento o retailer', effect: '✦ Rainbow foil — portada con arcoíris animado', cssClass: 'badge-variant',
    special: true,
  },
  {
    rank: 8, key: 'ultra', name: 'Ultra Rare', nameEs: 'Ultra Rara ✦',
    color: '#C46BFF', bg: '#9B3FE0', border: '#C46BFF', textColor: '#fff',
    desc: 'El unicornio del coleccionista. Determinado por research manual o marcado por la comunidad. Primeras ediciones firmadas, exclusivos de exhibición, tiradas de ≤100 copias.',
    examples: 'Signed first print · Galerie exclusive · 100 copies worldwide',
    availability: 'Caza activa requerida', effect: '✦✦ Full holographic — portada con holo completo', cssClass: 'badge-ultra',
    special: true,
  },
];

/* ═══ RARITY BADGE ═══ */
function RarityBadge({ tier, size = 'md' }) {
  const t = TIERS[tier - 1];
  if (!t) return null;
  const sizes = { sm: '2px 8px', md: '4px 12px', lg: '6px 16px' };
  const fs    = { sm: 9, md: 11, lg: 13 };
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    padding: sizes[size], borderRadius: 'var(--r-full)',
    fontSize: fs[size], fontWeight: 800, letterSpacing: '.06em',
    textTransform: 'uppercase', fontFamily: 'var(--f-body)',
    border: `1px solid ${t.border}`, background: t.bg, color: t.textColor,
    position: 'relative', overflow: 'hidden', whiteSpace: 'nowrap', userSelect: 'none',
  };
  return (
    <div className={t.cssClass || ''} style={!t.cssClass ? base : { ...base, background: undefined, border: undefined }}>
      {t.rank >= 6 && <span style={{ fontSize: (fs[size] || 11) - 2 }}>✦</span>}
      {t.name}
    </div>
  );
}

/* ═══ RARITY DEMO CARD ═══ */
function RarityDemoCard({ tier, interactive }) {
  const t = TIERS[tier - 1];
  const cardRef = React.useRef(null);

  const handleMove = React.useCallback((e) => {
    if (!interactive) return;
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top)  / rect.height - 0.5;
    el.style.transform = `perspective(600px) rotateX(${-y * 12}deg) rotateY(${x * 12}deg) translateZ(6px)`;
  }, [interactive]);

  const handleLeave = React.useCallback(() => {
    if (!interactive) return;
    const el = cardRef.current;
    if (!el) return;
    el.style.transition = 'transform .5s cubic-bezier(.23,1,.32,1)';
    el.style.transform = 'perspective(600px) rotateX(0) rotateY(0) translateZ(0)';
    setTimeout(() => { if (el) el.style.transition = ''; }, 500);
  }, [interactive]);

  const borderGlow = {
    6: '1px solid rgba(245,194,66,0.45)',
    7: '1px solid rgba(200,100,255,0.45)',
    8: '1px solid rgba(200,100,255,0.55)',
  };
  const boxGlow = {
    6: '0 4px 20px rgba(245,194,66,0.28), 0 2px 8px rgba(0,0,0,0.4)',
    7: '0 4px 20px rgba(200,100,255,0.35), 0 2px 8px rgba(0,0,0,0.4)',
    8: '0 4px 28px rgba(200,100,255,0.50), 0 0 40px rgba(100,150,255,0.15), 0 2px 8px rgba(0,0,0,0.4)',
  };

  /* Cover base colors per tier */
  const coverBase = {
    6: 'linear-gradient(160deg, #1a1400 0%, #251d00 60%, #1a1400 100%)',
    7: 'linear-gradient(160deg, #12002a 0%, #0a0a32 60%, #22001a 100%)',
    8: 'linear-gradient(160deg, #0a0020 0%, #060818 50%, #140028 100%)',
  };

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      style={{
        width: 110, background: 'var(--surface)',
        borderRadius: 'var(--r-lg)', overflow: 'hidden',
        border: borderGlow[tier] || '1px solid var(--border)',
        boxShadow: boxGlow[tier] || 'var(--sh-md)',
        cursor: 'pointer', willChange: 'transform', position: 'relative',
        flexShrink: 0, transition: 'box-shadow .2s',
      }}
    >
      {/* Cover area — foil effect lives here */}
      <div style={{ height: 140, position: 'relative', overflow: 'hidden',
        background: coverBase[tier] || 'repeating-linear-gradient(45deg,var(--surface-2),var(--surface-2) 4px,var(--surface-3) 4px,var(--surface-3) 8px)',
      }}>
        {/* Cover text label */}
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          fontSize: 8, fontWeight: 600, letterSpacing: '.06em',
          textTransform: 'uppercase', fontFamily: 'var(--f-body)',
          color: tier >= 6 ? 'rgba(255,255,255,0.25)' : 'var(--text-muted)',
          zIndex: 2,
        }}>
          T{tier} · cover
        </div>

        {/* ── Foil overlays for T6 / T7 / T8 ── */}
        {tier === 6 && <div className="cover-foil-gold" />}
        {tier === 7 && <div className="cover-foil-variant" />}
        {tier === 8 && (
          <>
            <div className="cover-foil-ultra" />
            <div className="cover-shine" />
          </>
        )}
      </div>

      {/* Tier badge — CLEAN label, no animation on card */}
      <div style={{ position: 'absolute', top: 6, left: 6, zIndex: 10 }}>
        <div style={{
          padding: '2px 7px', borderRadius: 'var(--r-full)',
          fontSize: 8, fontWeight: 800, letterSpacing: '.06em',
          textTransform: 'uppercase', fontFamily: 'var(--f-body)',
          background: t.rank >= 6 ? 'rgba(0,0,0,0.55)' : t.bg,
          color: t.rank >= 6 ? '#fff' : t.textColor,
          border: t.rank >= 6 ? '1px solid rgba(255,255,255,0.18)' : `1px solid ${t.border}`,
          backdropFilter: 'blur(6px)',
        }}>
          {t.rank >= 7 && '✦ '}{t.name}
        </div>
      </div>

      {/* Card info */}
      <div style={{ padding: '8px 10px 10px' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text)', lineHeight: 1.3, marginBottom: 2 }}>
          {t.nameEs.replace(' ✦', '')}
        </div>
        <div style={{ fontSize: 9, color: 'var(--text-muted)', lineHeight: 1.4 }}>
          {t.availability}
        </div>
      </div>
    </div>
  );
}

/* ═══ RARITY SECTION ═══ */
function RaritySection() {
  const [interactive, setInteractive] = React.useState(true);

  return (
    <section className="section" id="rarity">
      <style>{RARITY_STYLES}</style>

      <div className="section-eyebrow" style={{ color: 'var(--violet)' }}>Sistema de Rareza</div>
      <h2 className="section-title">
        Categorías + marcadores especiales
        <span style={{ marginLeft: 10, fontSize: 26, verticalAlign: 'middle' }}>✦</span>
      </h2>
      <p className="section-desc">
        Los tiers 1–7 son <strong style={{color:'var(--text)'}}>categorías de tipo de edición</strong> — un Kanzenban no es intrínsecamente más raro que un Deluxe, simplemente es un formato distinto. El tier 8 (<strong style={{color:'var(--violet)'}}>Ultra Rara</strong>) es un marcador especial que puede combinarse con cualquier categoría — un Variant puede ser también Ultra Rara. El foil holográfico vive en la imagen de portada, no en el tag.
      </p>

      <div className="demo-label" style={{ marginBottom: 'var(--s4)' }}>
        Hover sobre las cards para tilt 3D
        <button onClick={() => setInteractive(i => !i)} style={{
          marginLeft: 12, fontSize: 10, padding: '2px 10px',
          background: interactive ? 'var(--gold-dim)' : 'var(--surface-2)',
          border: `1px solid ${interactive ? 'var(--gold)' : 'var(--border-md)'}`,
          color: interactive ? 'var(--gold)' : 'var(--text-muted)',
          borderRadius: 'var(--r-full)', cursor: 'pointer',
          fontFamily: 'var(--f-body)', fontWeight: 600,
        }}>
          Tilt {interactive ? 'ON' : 'OFF'}
        </button>
      </div>

      {/* Card demos */}
      <div style={{ display: 'flex', gap: 'var(--s3)', flexWrap: 'wrap', marginBottom: 'var(--s9)' }}>
        {TIERS.map(t => <RarityDemoCard key={t.rank} tier={t.rank} interactive={interactive} />)}
      </div>

      {/* Reference table */}
      <div className="demo-label">Tabla de referencia</div>
      <div className="demo-box" style={{ padding: 0, overflow: 'hidden' }}>
        {TIERS.map((t, i) => (
          <div key={t.rank} style={{
            display: 'grid', gridTemplateColumns: '44px 160px 1fr 180px',
            gap: 'var(--s4)', padding: 'var(--s4) var(--s6)',
            borderBottom: i < TIERS.length - 1 ? '1px solid var(--border)' : 'none',
            alignItems: 'center',
            background: t.rank === 8 ? 'rgba(196,107,255,0.04)'
              : t.rank === 7 ? 'rgba(108,123,255,0.04)'
              : t.rank === 6 ? 'rgba(245,194,66,0.03)' : 'transparent',
          }}>
            {/* Rank */}
            <div style={{
              width: 32, height: 32, borderRadius: 'var(--r-md)',
              background: t.special ? 'var(--gold-dim)' : 'var(--surface-2)',
              border: `1px solid ${t.special ? 'var(--gold)' : 'var(--border)'}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 800,
              color: t.special ? 'var(--gold)' : 'var(--text-muted)',
            }}>T{t.rank}</div>

            {/* Animated badge (reference) */}
            <div>
              <div
                className={t.cssClass || ''}
                style={t.cssClass ? {
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '4px 12px', borderRadius: 'var(--r-full)',
                  fontSize: 11, fontWeight: 800, letterSpacing: '.06em',
                  textTransform: 'uppercase', fontFamily: 'var(--f-body)',
                  position: 'relative', overflow: 'hidden',
                } : {
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '4px 12px', borderRadius: 'var(--r-full)',
                  fontSize: 11, fontWeight: 800, letterSpacing: '.06em',
                  textTransform: 'uppercase', fontFamily: 'var(--f-body)',
                  background: t.bg, color: t.textColor, border: `1px solid ${t.border}`,
                }}
              >
                {t.rank >= 6 && <span style={{ fontSize: 9 }}>✦</span>}
                {t.name}
              </div>
            </div>

            {/* Description */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 2 }}>{t.nameEs}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                {t.desc.slice(0, 88)}…
              </div>
            </div>

            {/* Meta */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
              <div style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '.05em',
                color: t.special ? 'var(--gold)' : 'var(--text-muted)',
                padding: '2px 8px', background: 'var(--surface-2)',
                borderRadius: 'var(--r-full)', border: '1px solid var(--border)',
                display: 'inline-block', width: 'fit-content',
              }}>{t.availability}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', lineHeight: 1.4, paddingLeft: 2 }}>
                {t.effect}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Callout */}
      <div style={{
        marginTop: 'var(--s7)', padding: 'var(--s6)',
        background: 'var(--gold-dim)', border: '1px solid var(--gold)',
        borderRadius: 'var(--r-xl)',
        display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 'var(--s6)',
      }}>
        {[
          { icon: '🎯', title: 'El brillo es escaso', body: 'Foil solo en T6-T8. La calma del ~85% hace que el shimmer sea creíble y valioso. Si todo brillara, nada sería especial.' },
          { icon: '🔀', title: 'Las categorías se combinan', body: 'Un Variant puede ser también Ultra Rara. Un Box Set puede estar marcado como Limited. Las categorías no son excluyentes.' },
          { icon: '🃏', title: 'El foil va en la portada', body: 'Los tags de categoría son siempre limpios. El tratamiento visual especial vive en el área de la imagen — como en una carta física real.' },
        ].map((p, i) => (
          <div key={i}>
            <div style={{ fontSize: 22, marginBottom: 'var(--s2)' }}>{p.icon}</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--gold)', marginBottom: 'var(--s1)' }}>{p.title}</div>
            <div style={{ fontSize: 12, color: 'var(--text-sec)', lineHeight: 1.6 }}>{p.body}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

Object.assign(window, { RarityBadge, RaritySection, TIERS, RARITY_STYLES });
