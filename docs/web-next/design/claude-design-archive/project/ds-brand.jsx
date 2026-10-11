/* ═══════════════════════════════════════════
   DS-BRAND.JSX
   PandaLogo · BrandSection · ColorsSection
   TypographySection · SpacingSection · ShadowSection
═══════════════════════════════════════════ */

/* ── Logo SVG ── */
function PandaLogo({ size = 40, showWordmark = false, onDark = null }) {
  // onDark=null → use CSS vars; onDark=true → white face for dark bg; onDark=false → dark face for light bg
  const body  = onDark === null ? 'var(--logo-body)'  : onDark  ? '#E8ECF8' : '#FFFFFF';
  const ink   = onDark === null ? 'var(--logo-patch)' : onDark  ? '#0C1628' : '#111A38';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: size * 0.28 }}>
      <svg
        width={size} height={size} viewBox="0 0 56 56" fill="none"
        xmlns="http://www.w3.org/2000/svg"
        style={onDark === false ? { filter: 'drop-shadow(0 1px 4px rgba(0,0,0,0.10))' } : undefined}
      >
        {/* ── Ears: clearly round, slightly behind face ── */}
        <circle cx="11"  cy="13" r="9"  fill={ink} />
        <circle cx="45"  cy="13" r="9"  fill={ink} />

        {/* ── Face: cream/white circle ── */}
        <circle cx="28"  cy="31" r="21" fill={body} />

        {/* ── Eye patches: large, tilted ovals — the defining panda feature ── */}
        <ellipse cx="18" cy="27" rx="9.5" ry="8.5"
          transform="rotate(-9 18 27)" fill={ink} />
        <ellipse cx="38" cy="27" rx="9.5" ry="8.5"
          transform="rotate(9 38 27)" fill={ink} />

        {/* ── White iris rings inside patches ── */}
        <circle cx="17.5" cy="27"   r="4"   fill={body} />
        <circle cx="38.5" cy="27"   r="4"   fill={body} />

        {/* ── Left eye: round pupil (normal) ── */}
        <circle cx="18"   cy="27.5" r="2.1" fill={ink} />
        {/* Left eye highlight */}
        <circle cx="16.8" cy="26.2" r="0.9" fill={body} opacity="0.55" />

        {/* ── Right eye: 4-point star pupil — the Watch eye ── */}
        <path
          d="M38.5 25.1 L39.2 26.8 L41.0 27.3 L39.2 27.9 L38.5 29.5 L37.8 27.9 L36.0 27.3 L37.8 26.8 Z"
          fill={ink}
        />
        {/* Gold glint at star center — the treasure hunter's eye */}
        <circle cx="38.5" cy="27.3" r="0.95" fill="#F5C242" />

        {/* ── Nose ── */}
        <ellipse cx="28" cy="36"   rx="3.2" ry="2.2" fill={ink} opacity="0.85" />

        {/* ── Subtle smile ── */}
        <path d="M25.6 38 Q28 39.8 30.4 38"
          stroke={ink} strokeWidth="1.1" strokeLinecap="round"
          fill="none" opacity="0.38" />
      </svg>

      {showWordmark && (
        <div style={{
          fontFamily: 'var(--f-display)',
          fontWeight: 800,
          fontSize: size * 0.50,
          letterSpacing: '-0.03em',
          lineHeight: 1,
          display: 'flex',
          alignItems: 'baseline',
          userSelect: 'none',
        }}>
          <span style={{ color: onDark !== null ? (onDark ? '#E8ECF8' : '#111A38') : 'var(--text)' }}>Panda</span>
          <span style={{ color: '#F5C242' }}>Watch</span>
        </div>
      )}
    </div>
  );
}

/* ── Brand Section ── */
function BrandSection() {
  return (
    <section className="section" id="brand">
      <div className="section-eyebrow">Brand & Logo</div>
      <h2 className="section-title">Marca PandaWatch</h2>
      <p className="section-desc">
        El isotipo es una cara de panda geométrica donde el ojo derecho es una estrella de cuatro puntas — el ojo del cazador que ve la rareza antes que nadie. El wordmark combina peso regular en "Panda" y dorado en "Watch", creando jerarquía dentro del nombre.
      </p>

      {/* Logo on 3 backgrounds */}
      <div className="grid-3" style={{ marginBottom: 'var(--s7)' }}>
        {/* Dark bg */}
        <div style={{
          background: '#0E1424', borderRadius: 'var(--r-xl)',
          padding: 'var(--s8)', display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: 'var(--s7)',
          border: '1px solid rgba(255,255,255,0.06)'
        }}>
          <div className="demo-label" style={{ alignSelf: 'flex-start', marginBottom: 0 }}>Dark background</div>
          <PandaLogo size={48} showWordmark onDark={true} />
          <PandaLogo size={32} onDark={true} />
        </div>

        {/* Light bg */}
        <div style={{
          background: '#F6F4EF', borderRadius: 'var(--r-xl)',
          padding: 'var(--s8)', display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: 'var(--s7)',
          border: '1px solid rgba(0,0,0,0.07)'
        }}>
          <div className="demo-label" style={{ alignSelf: 'flex-start', color: 'rgba(26,34,56,0.45)', marginBottom: 0 }}>Light background</div>
          <PandaLogo size={48} showWordmark onDark={false} />
          <PandaLogo size={32} onDark={false} />
        </div>

        {/* Pure black */}
        <div style={{
          background: '#000000', borderRadius: 'var(--r-xl)',
          padding: 'var(--s8)', display: 'flex', flexDirection: 'column',
          alignItems: 'center', gap: 'var(--s7)',
        }}>
          <div className="demo-label" style={{ alignSelf: 'flex-start', marginBottom: 0 }}>Black / high contrast</div>
          <PandaLogo size={48} showWordmark onDark={true} />
          <div style={{
            fontFamily: 'var(--f-display)', fontWeight: 800, fontSize: 24,
            letterSpacing: '-0.03em', color: '#FFFFFF', userSelect: 'none'
          }}>Panda<span style={{ color: '#F5C242' }}>Watch</span></div>
        </div>
      </div>

      {/* Favicon + clearspace note */}
      <div style={{ display: 'flex', gap: 'var(--s5)', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--r-lg)', padding: 'var(--s5)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--s3)'
        }}>
          <div className="demo-label" style={{ marginBottom: 0 }}>Favicon 32px</div>
          <div style={{
            width: 32, height: 32, background: '#0E1424',
            borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center'
          }}>
            <PandaLogo size={24} onDark={true} />
          </div>
        </div>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--r-lg)', padding: 'var(--s5)',
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--s3)'
        }}>
          <div className="demo-label" style={{ marginBottom: 0 }}>App icon 64px</div>
          <div style={{
            width: 64, height: 64, background: 'linear-gradient(135deg,#0E1424,#1A2238)',
            borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: 'var(--sh-md)'
          }}>
            <PandaLogo size={44} onDark={true} />
          </div>
        </div>
        <div style={{
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: 'var(--r-lg)', padding: 'var(--s5)',
          flex: 1, minWidth: 200
        }}>
          <div className="demo-label" style={{ marginBottom: 'var(--s2)' }}>Clearspace</div>
          <div style={{ fontSize: 13, color: 'var(--text-sec)', lineHeight: 1.7 }}>
            Espacio mínimo alrededor del logo = <span style={{ color: 'var(--gold)' }}>½ altura de la "P"</span>. No distorsionar, no recolorear (solo variantes aprobadas), no añadir efectos.
          </div>
        </div>
      </div>
    </section>
  );
}

/* ── Colors Section ── */
const COLOR_TOKENS = [
  { name: 'Background',    dark: '#0E1424', light: '#F6F4EF',  token: '--bg',        usage: 'Page base' },
  { name: 'Surface',       dark: '#1A2238', light: '#FFFFFF',  token: '--surface',   usage: 'Cards, panels' },
  { name: 'Surface 2',     dark: '#1F2A40', light: '#F0EDE7',  token: '--surface-2', usage: 'Inputs, hover' },
  { name: 'Surface 3',     dark: '#253048', light: '#E6E2DA',  token: '--surface-3', usage: 'Active states' },
  { name: 'Border',        dark: 'rgba(234,235,242,.07)', light: 'rgba(26,34,56,.07)', token: '--border', usage: 'Dividers' },
  { name: 'Text Primary',  dark: '#EAEBF2', light: '#1A2238',  token: '--text',      usage: 'Headings, body' },
  { name: 'Text Secondary',dark: 'rgba(234,235,242,.60)', light: 'rgba(26,34,56,.60)', token: '--text-sec', usage: 'Labels, captions' },
  { name: 'Text Muted',    dark: 'rgba(234,235,242,.35)', light: 'rgba(26,34,56,.35)', token: '--text-muted', usage: 'Placeholder, disabled' },
];

const BRAND_COLORS = [
  { name: 'Gold',    dark: '#F5C242', light: '#C8951C', token: '--gold',   note: 'Primary actions, CTA, gold shimmer' },
  { name: 'Indigo',  dark: '#6C7BFF', light: '#4453E6', token: '--indigo', note: 'Accent, links, progress' },
  { name: 'Violet',  dark: '#C46BFF', light: '#A040E0', token: '--violet', note: 'Rare signal, special editions' },
  { name: 'Success', dark: '#3ECF9A', light: '#1EA876', token: '--success',note: 'In stock, confirmed, positive' },
  { name: 'Danger',  dark: '#FF5F6D', light: '#D9313F', token: '--danger', note: 'Errors, out of stock' },
  { name: 'Warning', dark: '#F5A028', light: '#D4840A', token: '--warning',note: 'Limited stock, alerts' },
];

function Swatch({ color, name, token, usage, size = 'md' }) {
  const [copied, setCopied] = React.useState(false);
  const copy = () => {
    navigator.clipboard?.writeText(color).catch(() => {});
    setCopied(true); setTimeout(() => setCopied(false), 1200);
  };
  const h = size === 'lg' ? 64 : 44;
  return (
    <div
      onClick={copy}
      title={`Copy ${color}`}
      style={{
        borderRadius: 'var(--r-md)', overflow: 'hidden',
        border: '1px solid var(--border)', cursor: 'pointer',
        transition: 'transform .15s, box-shadow .15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-2px)'; e.currentTarget.style.boxShadow = 'var(--sh-md)'; }}
      onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = ''; }}
    >
      <div style={{ height: h, background: color, position: 'relative' }}>
        {copied && (
          <div style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
            justifyContent: 'center', background: 'rgba(0,0,0,0.4)',
            fontSize: 11, fontWeight: 700, color: '#fff', letterSpacing: '.06em'
          }}>COPIED</div>
        )}
      </div>
      <div style={{ padding: '8px 10px', background: 'var(--surface)' }}>
        <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)', marginBottom: 1 }}>{name}</div>
        <div style={{ fontSize: 10, fontWeight: 600, fontFamily: 'monospace', color: 'var(--text-muted)', marginBottom: usage ? 2 : 0 }}>{color}</div>
        {usage && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{usage}</div>}
      </div>
    </div>
  );
}

function ColorsSection() {
  const [mode, setMode] = React.useState('dark');
  return (
    <section className="section" id="colors">
      <div className="section-eyebrow">Colors</div>
      <h2 className="section-title">Paleta "Midnight Treasure"</h2>
      <p className="section-desc">
        Tinta nocturna de base, oro escaso como acción primaria, índigo para profundidad y violeta para lo genuinamente raro. Ambos modos completamente diseñados — dark es el default del coleccionista.
      </p>

      <div style={{ display: 'flex', gap: 'var(--s2)', marginBottom: 'var(--s6)' }}>
        {['dark','light'].map(m => (
          <button key={m} onClick={() => setMode(m)} style={{
            padding: '6px 16px', borderRadius: 'var(--r-full)',
            border: '1px solid ' + (mode === m ? 'var(--gold)' : 'var(--border-md)'),
            background: mode === m ? 'var(--gold-dim)' : 'transparent',
            color: mode === m ? 'var(--gold)' : 'var(--text-sec)',
            fontSize: 12, fontWeight: 600, fontFamily: 'var(--f-body)', cursor: 'pointer'
          }}>
            {m === 'dark' ? '🌙 Dark' : '☀️ Light'}
          </button>
        ))}
      </div>

      <div className="demo-label">Neutrals & Surfaces</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--s3)', marginBottom: 'var(--s7)' }}>
        {COLOR_TOKENS.map(t => (
          <Swatch key={t.name} color={mode === 'dark' ? t.dark : t.light} name={t.name} usage={t.usage} />
        ))}
      </div>

      <div className="demo-label">Brand & Semantic</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--s3)' }}>
        {BRAND_COLORS.map(t => (
          <Swatch key={t.name} size="lg" color={mode === 'dark' ? t.dark : t.light} name={t.name} usage={t.note} />
        ))}
      </div>
    </section>
  );
}

/* ── Typography Section ── */
function TypographySection() {
  const typeScale = [
    { name: 'Display XL', size: '64px', weight: 800, family: 'display', sample: 'Descubrir tesouros.', tracking: '-0.04em', lh: 1.0 },
    { name: 'Display L',  size: '48px', weight: 800, family: 'display', sample: 'Ediciones que no sabías que existían.', tracking: '-0.03em', lh: 1.05 },
    { name: 'Heading 1',  size: '32px', weight: 700, family: 'display', sample: 'Attack on Titan — Deluxe Edition', tracking: '-0.02em', lh: 1.1 },
    { name: 'Heading 2',  size: '24px', weight: 700, family: 'display', sample: 'Berserk Kanzenban Vol. 1–40', tracking: '-0.02em', lh: 1.15 },
    { name: 'Heading 3',  size: '18px', weight: 600, family: 'display', sample: 'Coffret collector — Édition française', tracking: '-0.01em', lh: 1.2 },
    { name: 'Body L',     size: '16px', weight: 400, family: 'body', sample: 'Una edición limitada lanzada en tres países simultáneamente, con tapas alternativas y extras exclusivos.', tracking: '0', lh: 1.6 },
    { name: 'Body M',     size: '14px', weight: 400, family: 'body', sample: 'Precio desde $42 USD · 40 tomos · Editorial Hakusensha · JP', tracking: '0', lh: 1.55 },
    { name: 'Label',      size: '12px', weight: 600, family: 'body', sample: 'EDICIÓN LIMITADA · STOCK BAJO', tracking: '.08em', lh: 1.4 },
    { name: 'Caption',    size: '11px', weight: 500, family: 'body', sample: 'Detectado hace 2 horas · 3 fuentes disponibles', tracking: '.03em', lh: 1.4 },
  ];

  return (
    <section className="section" id="type">
      <div className="section-eyebrow">Typography</div>
      <h2 className="section-title">Sistema tipográfico</h2>
      <p className="section-desc">
        <strong style={{color:'var(--text)'}}>Bricolage Grotesque</strong> — display expresivo con anchura variable, para headers y momentos de impacto. <strong style={{color:'var(--text)'}}>Plus Jakarta Sans</strong> — cuerpo limpio y legible a todas las densidades. <strong style={{color:'var(--text)'}}>Noto Sans JP</strong> — CJK que respira junto al texto latino sin quedar como parche.
      </p>

      <div className="demo-box" style={{ marginBottom: 'var(--s7)' }}>
        {typeScale.map((t, i) => (
          <div key={i} style={{
            display: 'flex', alignItems: 'baseline', gap: 'var(--s5)',
            padding: 'var(--s4) 0',
            borderBottom: i < typeScale.length - 1 ? '1px solid var(--border)' : 'none',
          }}>
            <div style={{ width: 100, flexShrink: 0 }}>
              <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--gold)', letterSpacing: '.08em', textTransform: 'uppercase' }}>{t.name}</div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{t.size} / {t.weight}</div>
            </div>
            <div style={{
              fontFamily: t.family === 'display' ? 'var(--f-display)' : 'var(--f-body)',
              fontSize: t.size,
              fontWeight: t.weight,
              letterSpacing: t.tracking,
              lineHeight: t.lh,
              color: 'var(--text)',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: i < 3 ? 'nowrap' : 'normal',
            }}>
              {t.sample}
            </div>
          </div>
        ))}
      </div>

      {/* CJK + Latin coexistence */}
      <div className="demo-label">CJK + Latin — convivencia nativa</div>
      <div className="demo-box">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--s6)' }}>
          <div>
            <div style={{ fontFamily: 'var(--f-cjk)', fontSize: 28, fontWeight: 700, lineHeight: 1.3, color: 'var(--text)', marginBottom: 'var(--s2)', letterSpacing: '-0.01em' }}>
              進撃の巨人
            </div>
            <div style={{ fontFamily: 'var(--f-display)', fontSize: 15, fontWeight: 600, color: 'var(--text-sec)', letterSpacing: '-0.01em' }}>
              Attack on Titan — Final Season
            </div>
            <div style={{ fontFamily: 'var(--f-body)', fontSize: 12, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.5 }}>
              講談社 · Kodansha · 2009–2021 · 34 tomos
            </div>
          </div>
          <div>
            <div style={{ fontFamily: 'var(--f-cjk)', fontSize: 20, fontWeight: 700, color: 'var(--text)', marginBottom: 'var(--s2)', lineHeight: 1.5 }}>
              ベルセルク完全版
            </div>
            <div style={{ fontFamily: 'var(--f-display)', fontSize: 15, fontWeight: 600, color: 'var(--text-sec)', letterSpacing: '-0.01em' }}>
              Berserk Kanzenban Edition
            </div>
            <div style={{ fontFamily: 'var(--f-body)', fontSize: 12, color: 'var(--text-muted)', marginTop: 4, lineHeight: 1.5 }}>
              白泉社 · Hakusensha · JP · 40 vols. completos
            </div>
          </div>
        </div>
        <div style={{
          marginTop: 'var(--s5)', padding: 'var(--s4)', background: 'var(--surface-2)',
          borderRadius: 'var(--r-md)', fontSize: 12, color: 'var(--text-sec)', lineHeight: 1.7
        }}>
          <span style={{ color: 'var(--gold)', fontWeight: 600 }}>Regla CJK:</span> Noto Sans JP siempre en font-stack, line-height +10% vs texto latino para respiración vertical. Peso óptico igualado: JP 400 ≈ Jakarta 500.
        </div>
      </div>
    </section>
  );
}

/* ── Spacing Section ── */
function SpacingSection() {
  const steps = [
    { token: '--s0', val: '2px', name: 'Space 0' },
    { token: '--s1', val: '4px', name: 'Space 1' },
    { token: '--s2', val: '8px', name: 'Space 2' },
    { token: '--s3', val: '12px', name: 'Space 3' },
    { token: '--s4', val: '16px', name: 'Space 4' },
    { token: '--s5', val: '20px', name: 'Space 5' },
    { token: '--s6', val: '24px', name: 'Space 6' },
    { token: '--s7', val: '32px', name: 'Space 7' },
    { token: '--s8', val: '40px', name: 'Space 8' },
    { token: '--s9', val: '48px', name: 'Space 9' },
    { token: '--s10','val': '64px', name: 'Space 10' },
    { token: '--s11','val': '80px', name: 'Space 11' },
  ];
  const radii = [
    { name: 'XS', token: '--r-xs', val: '4px' },
    { name: 'SM', token: '--r-sm', val: '6px' },
    { name: 'MD', token: '--r-md', val: '10px' },
    { name: 'LG', token: '--r-lg', val: '14px' },
    { name: 'XL', token: '--r-xl', val: '20px' },
    { name: '2XL',token: '--r-2xl',val: '28px' },
    { name: 'Full',token: '--r-full',val: '9999px' },
  ];
  return (
    <section className="section" id="spacing">
      <div className="section-eyebrow">Spacing & Radii</div>
      <h2 className="section-title">Escala espacial</h2>
      <p className="section-desc">Grilla de 4px. Todos los espacios son múltiplos. Nunca valores ad-hoc — siempre tokens.</p>

      <div className="demo-label">Spacing scale</div>
      <div className="demo-box" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--s3)' }}>
        {steps.map(s => (
          <div key={s.token} style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)' }}>
            <div style={{ width: 80, fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', fontFamily: 'monospace' }}>{s.token}</div>
            <div style={{ width: 36, fontSize: 11, color: 'var(--text-sec)', fontFamily: 'monospace' }}>{s.val}</div>
            <div style={{
              height: 16, width: s.val, maxWidth: 400,
              background: 'var(--indigo)', borderRadius: 2, opacity: 0.7
            }} />
          </div>
        ))}
      </div>

      <div className="demo-label" style={{ marginTop: 'var(--s7)' }}>Border radii</div>
      <div style={{ display: 'flex', gap: 'var(--s4)', flexWrap: 'wrap' }}>
        {radii.map(r => (
          <div key={r.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--s2)' }}>
            <div style={{
              width: r.name === 'Full' ? 64 : 64,
              height: r.name === 'Full' ? 32 : 64,
              background: 'var(--surface-2)',
              border: '1px solid var(--border-md)',
              borderRadius: r.val,
            }} />
            <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-sec)' }}>{r.name}</div>
            <div style={{ fontSize: 10, fontFamily: 'monospace', color: 'var(--text-muted)' }}>{r.val}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── Shadow Section ── */
function ShadowSection() {
  const shadows = [
    { name: 'XS',   token: '--sh-xs', desc: 'Micro — estado focus, badges' },
    { name: 'SM',   token: '--sh-sm', desc: 'Chips, tags, small cards' },
    { name: 'MD',   token: '--sh-md', desc: 'Cards de catálogo, panels' },
    { name: 'LG',   token: '--sh-lg', desc: 'Cards spotlight, modales' },
    { name: 'XL',   token: '--sh-xl', desc: 'Drawers, popovers large' },
    { name: 'Gold', token: '--sh-gold', desc: 'Cards featured, CTA primario' },
  ];
  return (
    <section className="section" id="shadows">
      <div className="section-eyebrow">Elevation</div>
      <h2 className="section-title">Profundidad</h2>
      <p className="section-desc">Sombras en capas. El dark mode usa opacidades más altas para compensar la falta de contraste natural. Gold shadow reservado para elementos destacados.</p>
      <div style={{ display: 'flex', gap: 'var(--s6)', flexWrap: 'wrap' }}>
        {shadows.map(s => (
          <div key={s.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--s3)' }}>
            <div style={{
              width: 100, height: 80,
              background: s.name === 'Gold' ? 'var(--surface)' : 'var(--surface)',
              borderRadius: 'var(--r-lg)',
              boxShadow: `var(${s.token})`,
              border: s.name === 'Gold' ? '1px solid var(--gold-glow)' : '1px solid var(--border)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {s.name === 'Gold' && <div style={{ fontSize: 18 }}>⭐</div>}
            </div>
            <div style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-sec)' }}>{s.name}</div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)', textAlign: 'center', maxWidth: 100 }}>{s.desc}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── Export to window ── */
Object.assign(window, {
  PandaLogo,
  BrandSection,
  ColorsSection,
  TypographySection,
  SpacingSection,
  ShadowSection,
});
