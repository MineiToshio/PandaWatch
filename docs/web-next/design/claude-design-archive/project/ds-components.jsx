/* ═══════════════════════════════════════════
   DS-COMPONENTS.JSX
   Buttons · Inputs · Chips · Badges
   Cards (with tilt) · NavSection
═══════════════════════════════════════════ */

/* ─── SHARED MICRO-COMPONENTS ─── */

function Flag({ code, size = 16 }) {
  const flags = {
    JP: '🇯🇵', FR: '🇫🇷', US: '🇺🇸', ES: '🇪🇸',
    IT: '🇮🇹', BR: '🇧🇷', DE: '🇩🇪', UK: '🇬🇧',
    KR: '🇰🇷', MX: '🇲🇽', AR: '🇦🇷', CA: '🇨🇦',
  };
  return <span style={{ fontSize: size, lineHeight: 1 }}>{flags[code] || '🌐'}</span>;
}

function Chip({ label, selected, onClick, flag, icon, removable, onRemove, color }) {
  const base = {
    display: 'inline-flex', alignItems: 'center', gap: 5,
    padding: '5px 12px', borderRadius: 'var(--r-full)',
    fontSize: 12, fontWeight: 600, fontFamily: 'var(--f-body)',
    cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
    transition: 'all .15s',
    border: '1px solid ' + (selected
      ? (color || 'var(--gold)')
      : 'var(--border-md)'),
    background: selected
      ? (color ? color + '22' : 'var(--gold-dim)')
      : 'var(--surface-2)',
    color: selected
      ? (color || 'var(--gold)')
      : 'var(--text-sec)',
  };
  return (
    <div style={base} onClick={onClick}
      onMouseEnter={e => { if (!selected) { e.currentTarget.style.borderColor = 'var(--border-lg)'; e.currentTarget.style.color = 'var(--text)'; }}}
      onMouseLeave={e => { if (!selected) { e.currentTarget.style.borderColor = 'var(--border-md)'; e.currentTarget.style.color = 'var(--text-sec)'; }}}
    >
      {flag && <Flag code={flag} size={13} />}
      {icon && <span style={{ fontSize: 13 }}>{icon}</span>}
      <span>{label}</span>
      {removable && selected && (
        <span
          style={{ fontSize: 12, opacity: 0.7, marginLeft: 1, lineHeight: 1 }}
          onClick={e => { e.stopPropagation(); onRemove && onRemove(); }}
        >✕</span>
      )}
    </div>
  );
}

/* ─── BUTTONS SECTION ─── */
function ButtonsSection() {
  const Btn = ({ variant = 'primary', size = 'md', children, icon, disabled, loading }) => {
    const sizeMap = { sm: { p: '5px 14px', fs: 12 }, md: { p: '9px 20px', fs: 13 }, lg: { p: '12px 28px', fs: 15 } };
    const s = sizeMap[size];
    const vars = {
      primary:   { bg: 'var(--gold)', color: 'var(--gold-text)', border: 'var(--gold)', hover: 'var(--gold-glow)', shadow: 'var(--sh-gold)' },
      secondary: { bg: 'var(--surface-2)', color: 'var(--text)', border: 'var(--border-md)', hover: 'var(--surface-3)', shadow: 'none' },
      ghost:     { bg: 'transparent', color: 'var(--text-sec)', border: 'var(--border-md)', hover: 'var(--surface-2)', shadow: 'none' },
      accent:    { bg: 'var(--indigo-dim)', color: 'var(--indigo)', border: 'var(--indigo)', hover: 'var(--indigo-dim)', shadow: 'var(--sh-indigo)' },
      danger:    { bg: 'var(--danger-dim)', color: 'var(--danger)', border: 'var(--danger)', hover: 'var(--danger-dim)', shadow: 'none' },
      rare:      { bg: 'var(--violet-dim)', color: 'var(--violet)', border: 'var(--violet)', hover: 'var(--violet-dim)', shadow: 'var(--sh-violet)' },
    };
    const v = vars[variant] || vars.primary;
    return (
      <button
        disabled={disabled || loading}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          padding: s.p, borderRadius: 'var(--r-md)',
          fontSize: s.fs, fontWeight: 600, fontFamily: 'var(--f-body)',
          border: `1px solid ${v.border}`,
          background: v.bg, color: v.color,
          cursor: disabled || loading ? 'not-allowed' : 'pointer',
          opacity: disabled ? 0.45 : 1,
          boxShadow: v.shadow,
          transition: 'all .15s',
          whiteSpace: 'nowrap',
          letterSpacing: size === 'sm' ? '.04em' : '0',
        }}
        onMouseEnter={e => { if (!disabled && !loading) { e.currentTarget.style.background = v.hover; e.currentTarget.style.transform = 'translateY(-1px)'; }}}
        onMouseLeave={e => { e.currentTarget.style.background = v.bg; e.currentTarget.style.transform = ''; }}
      >
        {loading
          ? <span style={{ display: 'inline-block', width: 12, height: 12, border: '2px solid currentColor', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin .7s linear infinite' }} />
          : icon && <span style={{ fontSize: s.fs + 1 }}>{icon}</span>
        }
        {children}
      </button>
    );
  };

  return (
    <section className="section" id="buttons">
      <div className="section-eyebrow">Components</div>
      <h2 className="section-title">Botones</h2>
      <p className="section-desc">6 variantes × 3 tamaños. El botón primario usa oro — úsalo con escasez; una acción principal por vista.</p>

      <style>{`@keyframes spin { to { transform: rotate(360deg); }}`}</style>

      <div className="demo-box">
        {/* Variants */}
        <div className="demo-label">Variantes</div>
        <div className="flex-wrap" style={{ marginBottom: 'var(--s6)' }}>
          {['primary','secondary','ghost','accent','danger','rare'].map(v => (
            <Btn key={v} variant={v}>{v.charAt(0).toUpperCase()+v.slice(1)}</Btn>
          ))}
        </div>

        {/* Sizes */}
        <div className="demo-label">Tamaños</div>
        <div className="flex-wrap" style={{ alignItems: 'center', marginBottom: 'var(--s6)' }}>
          <Btn size="sm">Small</Btn>
          <Btn size="md">Medium</Btn>
          <Btn size="lg">Large</Btn>
        </div>

        {/* With icons */}
        <div className="demo-label">Con iconos</div>
        <div className="flex-wrap" style={{ marginBottom: 'var(--s6)' }}>
          <Btn icon="🔔">Quiero esta edición</Btn>
          <Btn variant="secondary" icon="🔖">Guardar búsqueda</Btn>
          <Btn variant="accent" icon="🛒">Ver en tienda</Btn>
          <Btn variant="rare" icon="✨">Edición rara</Btn>
        </div>

        {/* States */}
        <div className="demo-label">Estados</div>
        <div className="flex-wrap">
          <Btn loading>Cargando...</Btn>
          <Btn disabled>Deshabilitado</Btn>
          <Btn variant="secondary" disabled>Sin stock</Btn>
        </div>
      </div>
    </section>
  );
}

/* ─── INPUTS SECTION ─── */
function InputsSection() {
  const [val, setVal] = React.useState('');
  const [focus1, setFocus1] = React.useState(false);
  const [focus2, setFocus2] = React.useState(false);
  const [focus3, setFocus3] = React.useState(false);

  const inputStyle = (focused, error) => ({
    width: '100%', padding: '9px 14px',
    background: 'var(--surface-2)',
    border: `1px solid ${error ? 'var(--danger)' : focused ? 'var(--gold)' : 'var(--border-md)'}`,
    borderRadius: 'var(--r-md)', color: 'var(--text)',
    fontSize: 14, fontFamily: 'var(--f-body)',
    outline: 'none',
    boxShadow: focused && !error ? '0 0 0 3px var(--gold-dim)' : error ? '0 0 0 3px var(--danger-dim)' : 'none',
    transition: 'all .15s',
  });

  return (
    <section className="section" id="inputs">
      <h2 className="section-title" style={{ fontSize: 26 }}>Inputs</h2>
      <p className="section-desc" style={{ marginBottom: 'var(--s5)' }}>Focus ring de oro — refuerza la sensación de acción. Estado de error en rojo. Placeholder en muted.</p>

      <div className="demo-box">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--s5)' }}>
          {/* Search */}
          <div>
            <div className="demo-label">Búsqueda</div>
            <div style={{ position: 'relative' }}>
              <span style={{
                position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
                fontSize: 15, color: 'var(--text-muted)', pointerEvents: 'none'
              }}>🔍</span>
              <input
                value={val} onChange={e => setVal(e.target.value)}
                onFocus={() => setFocus1(true)} onBlur={() => setFocus1(false)}
                placeholder="Buscar manga, serie, editorial..."
                style={{ ...inputStyle(focus1, false), paddingLeft: 38 }}
              />
            </div>
          </div>

          {/* Text input */}
          <div>
            <div className="demo-label">Precio objetivo (alert)</div>
            <div style={{ position: 'relative' }}>
              <span style={{
                position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
                fontSize: 13, fontWeight: 600, color: 'var(--text-muted)'
              }}>$</span>
              <input
                onFocus={() => setFocus2(true)} onBlur={() => setFocus2(false)}
                placeholder="0.00"
                style={{ ...inputStyle(focus2, false), paddingLeft: 26 }}
              />
            </div>
          </div>

          {/* Error */}
          <div>
            <div className="demo-label">Estado error</div>
            <input
              defaultValue="ISBN inválido"
              style={{ ...inputStyle(false, true) }}
            />
            <div style={{ fontSize: 11, color: 'var(--danger)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 4 }}>
              <span>⚠</span> El ISBN debe tener 13 dígitos
            </div>
          </div>

          {/* With label + hint */}
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-sec)', marginBottom: 5 }}>
              Serie / Título <span style={{ color: 'var(--danger)' }}>*</span>
            </div>
            <input
              onFocus={() => setFocus3(true)} onBlur={() => setFocus3(false)}
              placeholder="Ej. Attack on Titan"
              style={{ ...inputStyle(focus3, false) }}
            />
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
              Título en cualquier idioma — lo normalizamos
            </div>
          </div>
        </div>

        {/* Select */}
        <div style={{ marginTop: 'var(--s5)' }}>
          <div className="demo-label">Dropdown / Select</div>
          <select style={{
            padding: '9px 14px', background: 'var(--surface-2)',
            border: '1px solid var(--border-md)', borderRadius: 'var(--r-md)',
            color: 'var(--text)', fontSize: 14, fontFamily: 'var(--f-body)',
            cursor: 'pointer', outline: 'none', minWidth: 220,
          }}>
            <option>Ordenar por: Score</option>
            <option>Ordenar por: Fecha de detección</option>
            <option>Ordenar por: Precio más bajo</option>
            <option>Ordenar por: Título A→Z</option>
          </select>
        </div>
      </div>
    </section>
  );
}

/* ─── CHIPS SECTION ─── */
function ChipsSection() {
  const [activeTypes, setActiveTypes] = React.useState(['Deluxe']);
  const [activeCountries, setActiveCountries] = React.useState(['JP']);
  const [score, setScore] = React.useState(70);

  const editionTypes = [
    { label: 'Deluxe', icon: '📘', color: '#D48A0C' },
    { label: 'Limitada', icon: '🔴', color: '#E05830' },
    { label: 'Box Set', icon: '📦', color: '#0CA99E' },
    { label: 'Artbook', icon: '🎨', color: '#9540E6' },
    { label: 'Kanzenban', icon: '⭐', color: '#F5C242' },
    { label: 'Variant', icon: '✨', color: '#C46BFF' },
    { label: 'Light Novel', icon: '📖', color: '#6C7BFF' },
    { label: 'Coffret', icon: '🇫🇷', color: '#6C7BFF' },
  ];

  const countries = [
    { code: 'JP', label: 'Japón' }, { code: 'FR', label: 'Francia' },
    { code: 'US', label: 'EE.UU.' }, { code: 'ES', label: 'España' },
    { code: 'IT', label: 'Italia' }, { code: 'BR', label: 'Brasil' },
  ];

  const toggle = (arr, setArr, val) =>
    setArr(arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val]);

  return (
    <section className="section" id="chips">
      <h2 className="section-title" style={{ fontSize: 26 }}>Chips & Filtros</h2>
      <p className="section-desc" style={{ marginBottom: 'var(--s5)' }}>
        Los tipos de edición son ciudadanos de primera clase — chips visuales con color propio. País y idioma con banderas. Filtros aplicados visibles y removibles.
      </p>

      <div className="demo-box">
        {/* Edition type chips — the star */}
        <div className="demo-label">Tipo de edición (filtro principal)</div>
        <div className="flex-wrap" style={{ marginBottom: 'var(--s6)' }}>
          {editionTypes.map(t => (
            <Chip
              key={t.label} label={t.label} icon={t.icon}
              selected={activeTypes.includes(t.label)}
              color={t.color}
              onClick={() => toggle(activeTypes, setActiveTypes, t.label)}
            />
          ))}
        </div>

        {/* Country chips */}
        <div className="demo-label">País / idioma</div>
        <div className="flex-wrap" style={{ marginBottom: 'var(--s6)' }}>
          {countries.map(c => (
            <Chip
              key={c.code} label={c.label} flag={c.code}
              selected={activeCountries.includes(c.code)}
              onClick={() => toggle(activeCountries, setActiveCountries, c.code)}
            />
          ))}
        </div>

        {/* Score slider */}
        <div className="demo-label">Score mínimo</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s4)', marginBottom: 'var(--s6)' }}>
          <input type="range" min={0} max={100} value={score} onChange={e => setScore(+e.target.value)}
            style={{ flex: 1, accentColor: 'var(--gold)' }}
          />
          <div style={{
            minWidth: 52, padding: '4px 10px', background: 'var(--gold-dim)',
            border: '1px solid var(--gold)', borderRadius: 'var(--r-full)',
            fontSize: 12, fontWeight: 700, color: 'var(--gold)', textAlign: 'center'
          }}>{score}+</div>
        </div>

        {/* Applied filters (removable) */}
        <div className="demo-label">Filtros aplicados</div>
        <div className="flex-wrap" style={{ alignItems: 'center' }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600 }}>Activos:</span>
          {activeTypes.map(t => {
            const info = editionTypes.find(x => x.label === t);
            return (
              <Chip key={t} label={t} icon={info?.icon} selected removable
                color={info?.color}
                onRemove={() => toggle(activeTypes, setActiveTypes, t)}
              />
            );
          })}
          {activeCountries.map(c => {
            const info = countries.find(x => x.code === c);
            return (
              <Chip key={c} label={info?.label} flag={c} selected removable
                onRemove={() => toggle(activeCountries, setActiveCountries, c)}
              />
            );
          })}
          {(activeTypes.length > 0 || activeCountries.length > 0) && (
            <button onClick={() => { setActiveTypes([]); setActiveCountries([]); }}
              style={{
                fontSize: 11, color: 'var(--danger)', background: 'none',
                border: 'none', cursor: 'pointer', fontFamily: 'var(--f-body)',
                fontWeight: 600, padding: '0 4px', opacity: 0.8
              }}>
              Limpiar todo
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

/* ─── BADGES SECTION ─── */
function BadgesSection() {
  const stockBadges = [
    { label: 'En stock', bg: 'var(--success-dim)', color: 'var(--success)', border: 'var(--success)' },
    { label: 'Stock bajo', bg: 'rgba(245,160,40,.14)', color: 'var(--warning)', border: 'var(--warning)' },
    { label: 'Agotado', bg: 'var(--danger-dim)', color: 'var(--danger)', border: 'var(--danger)' },
    { label: 'Pre-orden', bg: 'var(--indigo-dim)', color: 'var(--indigo)', border: 'var(--indigo)' },
    { label: 'Anunciado', bg: 'var(--surface-2)', color: 'var(--text-muted)', border: 'var(--border-md)' },
  ];

  const signalBadges = [
    { label: 'Exclusivo retailer', color: '#C46BFF' },
    { label: 'Región exclusiva', color: '#6C7BFF' },
    { label: 'Tirada limitada', color: '#E05830' },
    { label: 'Descatalogado', color: '#FF5F6D' },
    { label: 'Primera edición', color: '#D48A0C' },
  ];

  const Badge = ({ label, bg, color, border, dot }) => (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 10px', borderRadius: 'var(--r-full)',
      fontSize: 11, fontWeight: 700, letterSpacing: '.04em',
      fontFamily: 'var(--f-body)',
      background: bg, color, border: `1px solid ${border}`,
    }}>
      {dot && <div style={{ width: 5, height: 5, borderRadius: '50%', background: color, flexShrink: 0 }} />}
      {label}
    </div>
  );

  return (
    <section className="section" id="badges">
      <h2 className="section-title" style={{ fontSize: 26 }}>Badges</h2>

      <div className="demo-box">
        <div className="demo-label">Estado de stock</div>
        <div className="flex-wrap" style={{ marginBottom: 'var(--s6)' }}>
          {stockBadges.map(b => <Badge key={b.label} {...b} dot />)}
        </div>

        <div className="demo-label">Señales de edición</div>
        <div className="flex-wrap">
          {signalBadges.map(b => (
            <Badge key={b.label} label={b.label}
              bg={b.color + '1A'} color={b.color} border={b.color + '50'}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

/* ─── MANGA CARD — with tilt effect ─── */
function MangaCard({ title, titleJp, type, typeColor, country, publisher, volumes, price, stock, score, spotlight = false, foil = false }) {
  const cardRef = React.useRef(null);

  const handleMove = React.useCallback((e) => {
    const el = cardRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width - 0.5;
    const y = (e.clientY - rect.top)  / rect.height - 0.5;
    el.style.transform = `perspective(700px) rotateX(${-y * 9}deg) rotateY(${x * 9}deg) translateZ(4px)`;
    if (foil) {
      const px = ((e.clientX - rect.left) / rect.width) * 100;
      const py = ((e.clientY - rect.top)  / rect.height) * 100;
      el.style.setProperty('--foil-x', px + '%');
      el.style.setProperty('--foil-y', py + '%');
    }
  }, [foil]);

  const handleLeave = React.useCallback(() => {
    const el = cardRef.current;
    if (!el) return;
    el.style.transform = 'perspective(700px) rotateX(0) rotateY(0) translateZ(0)';
    el.style.transition = 'transform .5s cubic-bezier(.23,1,.32,1)';
    setTimeout(() => { if (el) el.style.transition = ''; }, 500);
  }, []);

  const w = spotlight ? 220 : 160;
  const h = spotlight ? 310 : 226;

  return (
    <div
      ref={cardRef}
      onMouseMove={handleMove}
      onMouseLeave={handleLeave}
      style={{
        width: w,
        background: 'var(--surface)',
        borderRadius: 'var(--r-lg)',
        overflow: 'hidden',
        border: spotlight ? '1px solid var(--gold-glow)' : '1px solid var(--border)',
        boxShadow: spotlight ? 'var(--sh-gold)' : 'var(--sh-md)',
        cursor: 'pointer',
        flexShrink: 0,
        willChange: 'transform',
        position: 'relative',
        transition: 'box-shadow .2s',
      }}
    >
      {/* Foil shimmer overlay */}
      {foil && (
        <div style={{
          position: 'absolute', inset: 0, zIndex: 10, pointerEvents: 'none',
          background: 'radial-gradient(ellipse at var(--foil-x, 50%) var(--foil-y, 50%), rgba(255,255,255,0.08) 0%, transparent 70%)',
          mixBlendMode: 'overlay',
          borderRadius: 'var(--r-lg)',
        }} />
      )}

      {/* Cover */}
      <div className="cover-ph" style={{ width: '100%', height: h }}>
        {titleJp || title}<br />cover art
      </div>

      {/* Rarity/type badge overlaid */}
      <div style={{
        position: 'absolute', top: 8, left: 8,
        padding: '2px 8px', borderRadius: 'var(--r-full)',
        fontSize: 9, fontWeight: 800, letterSpacing: '.07em',
        textTransform: 'uppercase',
        background: typeColor + 'EE', color: '#fff',
        backdropFilter: 'blur(4px)',
        boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
      }}>
        {type}
      </div>

      {/* Country flag */}
      <div style={{ position: 'absolute', top: 8, right: 8 }}>
        <Flag code={country} size={15} />
      </div>

      {/* Card body */}
      <div style={{ padding: '10px 12px 12px' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--text)', lineHeight: 1.3, marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          {title}
        </div>
        {titleJp && (
          <div style={{ fontFamily: 'var(--f-cjk)', fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, lineHeight: 1.4 }}>
            {titleJp}
          </div>
        )}
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>
          {publisher} · {volumes} vols.
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{
            fontSize: 12, fontWeight: 700, color: 'var(--gold)',
          }}>
            {price ? `desde $${price}` : <span style={{ color: 'var(--text-muted)' }}>Sin precio</span>}
          </div>
          <div style={{
            fontSize: 9, fontWeight: 800, letterSpacing: '.04em',
            padding: '2px 6px', borderRadius: 'var(--r-full)',
            background: score >= 85 ? 'var(--success-dim)' : 'var(--surface-2)',
            color: score >= 85 ? 'var(--success)' : 'var(--text-muted)',
            border: `1px solid ${score >= 85 ? 'var(--success)' : 'var(--border)'}`,
          }}>
            {score}
          </div>
        </div>

        {stock === 'low' && (
          <div style={{
            marginTop: 6, fontSize: 9, fontWeight: 700, color: 'var(--warning)',
            display: 'flex', alignItems: 'center', gap: 4, letterSpacing: '.04em'
          }}>
            <span>🔥</span> POCAS UNIDADES
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── CARDS SECTION ─── */
function CardsSection() {
  const cards = [
    { title: 'Berserk Kanzenban', titleJp: 'ベルセルク完全版', type: 'Kanzenban', typeColor: '#F5C242', country: 'JP', publisher: 'Hakusensha', volumes: 40, price: '112', stock: null, score: 97, foil: true },
    { title: 'Vinland Saga Deluxe', titleJp: 'ヴィンランド・サガ', type: 'Deluxe', typeColor: '#D48A0C', country: 'JP', publisher: 'Kodansha', volumes: 11, price: '78', stock: 'low', score: 91 },
    { title: 'One Piece Coffret', titleJp: null, type: 'Coffret', typeColor: '#6C7BFF', country: 'FR', publisher: 'Glénat', volumes: 12, price: '55', stock: null, score: 84 },
    { title: 'Chainsaw Man Box Set', titleJp: 'チェンソーマン', type: 'Box Set', typeColor: '#0CA99E', country: 'US', publisher: 'Viz', volumes: 11, price: '89', stock: 'low', score: 88 },
  ];

  return (
    <section className="section" id="cards">
      <h2 className="section-title" style={{ fontSize: 26 }}>Cards de edición</h2>
      <p className="section-desc" style={{ marginBottom: 'var(--s5)' }}>
        El arte de tapa es el héroe. Tilt 3D en hover — tacto de fisicidad. Foil shimmer reservado para ediciones raras. Spotlight card (primera) tiene borde dorado y sombra especial.
      </p>

      <div className="demo-box">
        <div className="demo-label">Hover para efecto tilt + shimmer</div>
        <div style={{ display: 'flex', gap: 'var(--s4)', flexWrap: 'wrap', alignItems: 'flex-start' }}>
          {/* Spotlight card (bigger) */}
          <div style={{ position: 'relative' }}>
            <div style={{
              position: 'absolute', top: -10, left: '50%', transform: 'translateX(-50%)',
              fontSize: 9, fontWeight: 800, letterSpacing: '.1em', color: 'var(--gold)',
              background: 'var(--gold-dim)', border: '1px solid var(--gold)',
              padding: '2px 10px', borderRadius: 'var(--r-full)', whiteSpace: 'nowrap',
              zIndex: 2,
            }}>✦ SPOTLIGHT</div>
            <MangaCard {...cards[0]} spotlight />
          </div>
          {cards.slice(1).map((c,i) => <MangaCard key={i} {...c} />)}
        </div>
      </div>

      {/* Skeleton */}
      <div className="demo-label" style={{ marginTop: 'var(--s7)' }}>Estado skeleton (cargando)</div>
      <div className="demo-box" style={{ display: 'flex', gap: 'var(--s4)' }}>
        {[0,1,2].map(i => (
          <div key={i} style={{ width: 160, borderRadius: 'var(--r-lg)', overflow: 'hidden', border: '1px solid var(--border)' }}>
            <div className="skeleton" style={{ width: '100%', height: 226 }} />
            <div style={{ padding: '10px 12px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div className="skeleton" style={{ height: 12, width: '80%' }} />
              <div className="skeleton" style={{ height: 9, width: '55%' }} />
              <div className="skeleton" style={{ height: 9, width: '65%' }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ─── NAV SECTION ─── */
function NavSection() {
  const [activeTab, setActiveTab] = React.useState('catalog');
  const tabs = [
    { id: 'catalog', label: 'Descubrir' },
    { id: 'calendar', label: 'Calendario' },
    { id: 'collection', label: 'Mi colección' },
    { id: 'alerts', label: 'Alertas' },
  ];

  const pages = [1,2,3,4,5,'…',28];
  const [page, setPage] = React.useState(3);

  return (
    <section className="section" id="nav-comp">
      <h2 className="section-title" style={{ fontSize: 26 }}>Navegación</h2>

      <div className="demo-box">
        {/* Tabs */}
        <div className="demo-label">Tabs principales</div>
        <div style={{
          display: 'flex', gap: 2, background: 'var(--surface-2)',
          padding: 4, borderRadius: 'var(--r-lg)', width: 'fit-content',
          marginBottom: 'var(--s6)',
        }}>
          {tabs.map(t => (
            <button key={t.id} onClick={() => setActiveTab(t.id)} style={{
              padding: '7px 16px', borderRadius: 'var(--r-md)',
              border: 'none', cursor: 'pointer',
              background: activeTab === t.id ? 'var(--surface)' : 'transparent',
              color: activeTab === t.id ? 'var(--text)' : 'var(--text-muted)',
              fontSize: 13, fontWeight: activeTab === t.id ? 600 : 400,
              fontFamily: 'var(--f-body)',
              boxShadow: activeTab === t.id ? 'var(--sh-sm)' : 'none',
              transition: 'all .15s',
            }}>
              {t.label}
            </button>
          ))}
        </div>

        {/* Pagination (redesigned) */}
        <div className="demo-label">Paginación (no burocrática)</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--s2)' }}>
          <button onClick={() => setPage(p => Math.max(1, p-1))} style={{
            padding: '7px 14px', background: 'var(--surface-2)',
            border: '1px solid var(--border-md)', borderRadius: 'var(--r-md)',
            color: 'var(--text-sec)', cursor: 'pointer', fontSize: 13,
            fontFamily: 'var(--f-body)', fontWeight: 500,
          }}>← Anterior</button>
          <div style={{ display: 'flex', gap: 'var(--s1)' }}>
            {pages.map((p, i) => {
              const isActive = p === page;
              const isDots = p === '…';
              return (
                <button key={i} onClick={() => !isDots && setPage(p)} style={{
                  width: 36, height: 36,
                  background: isActive ? 'var(--gold)' : isDots ? 'transparent' : 'var(--surface-2)',
                  border: isActive ? 'none' : isDots ? 'none' : '1px solid var(--border)',
                  borderRadius: 'var(--r-md)',
                  color: isActive ? 'var(--gold-text)' : isDots ? 'var(--text-muted)' : 'var(--text-sec)',
                  cursor: isDots ? 'default' : 'pointer',
                  fontSize: 13, fontWeight: isActive ? 700 : 400, fontFamily: 'var(--f-body)',
                  boxShadow: isActive ? 'var(--sh-gold)' : 'none',
                  transition: 'all .12s',
                }}>
                  {p}
                </button>
              );
            })}
          </div>
          <button onClick={() => setPage(p => Math.min(28, p+1))} style={{
            padding: '7px 14px', background: 'var(--surface-2)',
            border: '1px solid var(--border-md)', borderRadius: 'var(--r-md)',
            color: 'var(--text-sec)', cursor: 'pointer', fontSize: 13,
            fontFamily: 'var(--f-body)', fontWeight: 500,
          }}>Siguiente →</button>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'var(--s3)' }}>
            {(page-1)*60+1}–{page*60} de 1,680 ediciones
          </div>
        </div>
      </div>
    </section>
  );
}

/* ─── STATES SECTION ─── */
function StatesSection() {
  const [toastVisible, setToastVisible] = React.useState(false);
  const [toastType, setToastType] = React.useState('success');

  const showToast = (type) => {
    setToastType(type);
    setToastVisible(true);
    setTimeout(() => setToastVisible(false), 2800);
  };

  const toastMessages = {
    success: { icon: '✓', label: '¡Alerta creada!', msg: 'Te avisamos cuando baje de $45 USD.', color: 'var(--success)', bg: 'var(--success-dim)', border: 'var(--success)' },
    danger:  { icon: '!', label: 'Error de conexión', msg: 'No pudimos cargar las fuentes. Reintentando...', color: 'var(--danger)', bg: 'var(--danger-dim)', border: 'var(--danger)' },
    info:    { icon: '★', label: 'Nueva detección', msg: 'Berserk Kanzenban disponible en Mandarake.', color: 'var(--gold)', bg: 'var(--gold-dim)', border: 'var(--gold)' },
  };
  const t = toastMessages[toastType];

  return (
    <section className="section" id="states">
      <h2 className="section-title" style={{ fontSize: 26 }}>Estados del sistema</h2>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--s5)', marginBottom: 'var(--s5)' }}>
        {/* Empty state */}
        <div className="demo-box" style={{ textAlign: 'center', padding: 'var(--s9)' }}>
          <div className="demo-label" style={{ textAlign: 'left' }}>Estado vacío</div>
          <div style={{ fontSize: 48, marginBottom: 'var(--s4)' }}>🐼</div>
          <div style={{
            fontFamily: 'var(--f-display)', fontSize: 20, fontWeight: 700,
            color: 'var(--text)', marginBottom: 'var(--s2)', letterSpacing: '-0.02em'
          }}>
            El panda no encontró nada
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 'var(--s6)', maxWidth: 260, margin: '0 auto var(--s6)' }}>
            Probá con otros filtros o amplía el rango de países — quizás esa edición existe donde no la esperabas.
          </div>
          <button style={{
            padding: '8px 20px', background: 'var(--gold-dim)',
            border: '1px solid var(--gold)', borderRadius: 'var(--r-md)',
            color: 'var(--gold)', fontSize: 12, fontWeight: 600,
            fontFamily: 'var(--f-body)', cursor: 'pointer',
          }}>Limpiar filtros</button>
        </div>

        {/* Error state */}
        <div className="demo-box" style={{ textAlign: 'center', padding: 'var(--s9)' }}>
          <div className="demo-label" style={{ textAlign: 'left' }}>Estado de error</div>
          <div style={{ fontSize: 40, marginBottom: 'var(--s4)' }}>📡</div>
          <div style={{
            fontFamily: 'var(--f-display)', fontSize: 20, fontWeight: 700,
            color: 'var(--text)', marginBottom: 'var(--s2)', letterSpacing: '-0.02em'
          }}>
            El radar perdió señal
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.6, marginBottom: 'var(--s6)', maxWidth: 260, margin: '0 auto var(--s6)' }}>
            No pudimos contactar algunas fuentes. El catálogo puede estar incompleto.
          </div>
          <button style={{
            padding: '8px 20px', background: 'var(--danger-dim)',
            border: '1px solid var(--danger)', borderRadius: 'var(--r-md)',
            color: 'var(--danger)', fontSize: 12, fontWeight: 600,
            fontFamily: 'var(--f-body)', cursor: 'pointer',
          }}>Reintentar</button>
        </div>
      </div>

      {/* Toasts */}
      <div className="demo-box">
        <div className="demo-label">Toasts</div>
        <div style={{ display: 'flex', gap: 'var(--s3)' }}>
          {Object.entries(toastMessages).map(([key, tm]) => (
            <button key={key} onClick={() => showToast(key)} style={{
              padding: '7px 16px', background: 'var(--surface-2)',
              border: '1px solid var(--border-md)', borderRadius: 'var(--r-md)',
              color: 'var(--text-sec)', fontSize: 12, fontWeight: 600,
              fontFamily: 'var(--f-body)', cursor: 'pointer',
            }}>
              Toast {key}
            </button>
          ))}
        </div>
      </div>

      {/* Toast display */}
      {toastVisible && (
        <div style={{
          position: 'fixed', bottom: 'var(--s7)', right: 'var(--s7)',
          background: 'var(--surface)',
          border: `1px solid ${t.border}`,
          borderLeft: `3px solid ${t.color}`,
          borderRadius: 'var(--r-lg)',
          padding: 'var(--s4) var(--s5)',
          boxShadow: 'var(--sh-lg)',
          display: 'flex', alignItems: 'center', gap: 'var(--s4)',
          minWidth: 280, maxWidth: 380,
          animation: 'fadeUp .25s ease',
          zIndex: 9999,
        }}>
          <div style={{
            width: 30, height: 30, borderRadius: '50%',
            background: t.bg, border: `1px solid ${t.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 13, fontWeight: 800, color: t.color, flexShrink: 0,
          }}>{t.icon}</div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 1 }}>{t.label}</div>
            <div style={{ fontSize: 12, color: 'var(--text-sec)' }}>{t.msg}</div>
          </div>
          <button onClick={() => setToastVisible(false)} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text-muted)', fontSize: 16, lineHeight: 1,
          }}>✕</button>
        </div>
      )}
    </section>
  );
}

/* ── Export ── */
Object.assign(window, {
  Chip, Flag, MangaCard,
  ButtonsSection, InputsSection, ChipsSection,
  BadgesSection, CardsSection, NavSection, StatesSection,
});
