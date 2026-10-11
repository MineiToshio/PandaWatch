// PandaWatch UI Kit — Mock Data & Utilities
// Plain JS (no JSX) — loaded before React components

const RARITY_CONFIG = {
  accessible: {
    label: 'Accessible', color: '#64748B', bg: '#F1F5F9', border: '#CBD5E1',
    icon: 'circle', score: '0–20',
    tooltip: 'Special edition, widely available. No rush.'
  },
  limited: {
    label: 'Limited', color: '#1A8A5A', bg: '#EDFAF3', border: '#A6DFCA',
    icon: 'star', score: '21–40',
    tooltip: 'Limited print run. Available with some effort.'
  },
  rare: {
    label: 'Rare', color: '#2D52CC', bg: '#EEF2FF', border: '#C7D2FE',
    icon: 'star2', score: '41–65',
    tooltip: 'Hard to find. Secondary market usually required.'
  },
  'very-rare': {
    label: 'Super Rare', color: '#7C3AED', bg: '#F5F3FF', border: '#DDD6FE',
    icon: 'sparkle', score: '66–85',
    tooltip: 'Very low availability. Regional or short print window.'
  },
  'ultra-rare': {
    label: 'Ultra Rare', color: '#9E6C00', bg: '#FFFBEB', border: '#FDE68A',
    icon: 'diamond', score: '86–100',
    tooltip: 'Extremely scarce. Event exclusives, lotteries, micro-prints.'
  },
  unknown: {
    label: 'Unknown', color: '#9CA3AF', bg: '#F9FAFB', border: '#E5E7EB',
    icon: 'help', score: 'null',
    tooltip: 'Insufficient data to estimate rarity.'
  }
};

function scoreToRarity(score) {
  if (score == null) return 'unknown';
  if (score <= 20) return 'accessible';
  if (score <= 40) return 'limited';
  if (score <= 65) return 'rare';
  if (score <= 85) return 'very-rare';
  return 'ultra-rare';
}

const COVER_SCHEMES = {
  'pn-fanbook':    { grad: 'linear-gradient(160deg,#0f0c29 0%,#302b63 55%,#24243e 100%)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(180,170,255,0.9)' },
  'berserk':       { grad: 'linear-gradient(160deg,#0a0000 0%,#2a0800 40%,#5c1200 80%,#8b1a00 100%)', bar: 'rgba(0,0,0,0.6)', barText: 'rgba(212,180,50,0.95)' },
  'berserk-2':     { grad: 'linear-gradient(160deg,#1a0800,#3d1200)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(180,120,50,0.85)' },
  'berserk-3':     { grad: 'linear-gradient(160deg,#2d0a00,#5c1500)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(180,120,50,0.7)' },
  'op-100':        { grad: 'linear-gradient(160deg,#1e3a8a 0%,#1e40af 40%,#ea580c 80%,#f97316 100%)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(255,220,150,0.95)' },
  'csm-boxset':    { grad: 'linear-gradient(160deg,#1a0000 0%,#5c0000 50%,#991b1b 100%)', bar: 'rgba(0,0,0,0.55)', barText: 'rgba(252,165,165,0.9)' },
  'csm-2':         { grad: 'linear-gradient(160deg,#3d0000,#7f1d1d)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(252,165,165,0.75)' },
  'csm-3':         { grad: 'linear-gradient(160deg,#5c0000,#8b1a1a)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(252,165,165,0.65)' },
  'akira':         { grad: 'linear-gradient(160deg,#0a0a0a 0%,#1a0000 40%,#7f1d1d 100%)', bar: 'rgba(0,0,0,0.6)', barText: 'rgba(239,68,68,0.9)' },
  'naruto':        { grad: 'linear-gradient(135deg,#7c2d12 0%,#ea580c 45%,#f97316 100%)', bar: 'rgba(0,0,0,0.45)', barText: 'rgba(255,240,200,0.95)' },
  'generic-dark':  { grad: 'linear-gradient(160deg,#1c1915,#3b3632)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(200,190,180,0.9)' },
  'generic-blue':  { grad: 'linear-gradient(160deg,#0c1a3d,#1e3a8a,#1e40af)', bar: 'rgba(0,0,0,0.5)', barText: 'rgba(180,200,255,0.9)' },
};

const MANGA_ITEMS = [
  // ── Bakuman items ── use the real cover image (assets/bakuman-cover.png) — match the
  //    examples shown in preview/components-manga-card.html and components-collection-card.html.
  {
    id: 'bakuman-anniversary-de',
    type: 'single',
    title: 'Bakuman 20th Anniversary Edition',
    shortTitle: '20th Anniversary Edition',
    series: 'Bakuman',
    editionType: 'Anniversary',
    productType: 'anniversary',
    publisher: 'Tokyopop',
    country: 'Germany',
    language: 'German',
    score: 55,
    status: null,
    isbn: '9783842089136',
    price: '€19.00',
    publishedAt: '2023-04-12',
    detectedAt: '2026-05-21',
    signals: ['anniversary', 'hardcover'],
    signalTypes: ['anniversary'],
    source: 'Publisher Direct',
    sourceClass: 'publisher',
    sourceUrl: 'https://www.tokyopop.de/',
    coverScheme: 'generic-dark',
    imgSrc: '../../assets/bakuman-cover.png',
    description: 'Tokyopop\'s 20th anniversary edition of Bakuman for the German market.',
    tags: ['anniversary','germany','german','tokyopop'],
  },
  {
    id: 'bakuman-deluxe-jp',
    type: 'collection',
    title: 'Bakuman Deluxe Collector\'s Edition',
    shortTitle: 'Deluxe Collector\'s Edition',
    series: 'Bakuman',
    editionType: 'Deluxe',
    productType: 'deluxe',
    publisher: 'Shueisha',
    country: 'Japan',
    language: 'Japanese',
    score: 35,
    status: 'new',
    isbn: null,
    price: '¥3,200 / vol',
    publishedAt: '2024-12-04',
    detectedAt: '2026-05-22',
    signals: ['deluxe', 'hardcover', 'limited'],
    signalTypes: ['deluxe', 'limited'],
    source: 'Publisher Direct',
    sourceClass: 'publisher',
    sourceUrl: 'https://www.shueisha.co.jp/',
    coverScheme: 'generic-dark',
    imgSrc: '../../assets/bakuman-cover.png',
    volumes: 11,
    volumeCovers: ['generic-dark','generic-dark','generic-dark'],
    description: 'Shueisha\'s deluxe collector\'s edition of Bakuman, hardcover with bonus material.',
    tags: ['deluxe','box-set','japan','japanese','shueisha'],
  },
  {
    id: 'bakuman-fanbook',
    type: 'single',
    title: 'Bakuman Exhibition Fanbook — Ohba & Obata',
    shortTitle: 'Exhibition Fanbook — Ohba & Obata',
    series: 'Bakuman',
    editionType: 'Fanbook',
    productType: 'fanbook',
    publisher: 'Shueisha',
    country: 'Japan',
    language: 'Japanese',
    score: 75,
    status: 'changed',
    isbn: '9784088808451',
    price: '¥2,800',
    publishedAt: '2018-10-20',
    detectedAt: '2026-05-12',
    signals: ['fanbook', 'exhibition', 'limited'],
    signalTypes: ['fanbook', 'exhibition'],
    source: 'Manga Sanctuary',
    sourceClass: 'trusted_media',
    sourceUrl: 'https://www.manga-sanctuary.com/',
    coverScheme: 'generic-dark',
    imgSrc: '../../assets/bakuman-cover.png',
    description: 'Limited fanbook produced for the Ohba & Obata exhibition.',
    tags: ['fanbook','exhibition','japan','japanese','shueisha'],
  },
  {
    id: 'pn-fanbook',
    type: 'single',
    title: 'The Promised Neverland Mystic Code Fanbook',
    shortTitle: 'Mystic Code Fanbook',
    series: 'The Promised Neverland',
    editionType: 'Fanbook',
    productType: 'fanbook',
    publisher: 'kazé manga',
    country: 'France',
    language: 'French',
    score: 30,
    status: 'changed',
    isbn: '9782820342706',
    price: '€9.99',
    publishedAt: '2021-10-27',
    detectedAt: '2026-05-19',
    signals: ['fanbook'],
    signalTypes: ['fanbook'],
    source: 'Manga Sanctuary',
    sourceClass: 'trusted_media',
    sourceUrl: 'https://www.manga-sanctuary.com/',
    coverScheme: 'pn-fanbook',
    description: 'kazé manga · simple · Fanbook · The Promised Neverland - Mystic Code',
    tags: ['wiki','manga-sanctuary','manga','france','type:fanbook','edition:simple'],
  },
  {
    id: 'berserk-deluxe',
    type: 'collection',
    title: 'Berserk Deluxe Edition',
    shortTitle: 'Deluxe Edition',
    series: 'Berserk',
    editionType: 'Deluxe',
    productType: 'deluxe',
    publisher: 'Dark Horse Comics',
    country: 'USA',
    language: 'English',
    score: 55,
    status: null,
    isbn: null,
    price: '$49.99 / vol',
    publishedAt: '2019-04-09',
    detectedAt: '2026-05-15',
    signals: ['deluxe', 'hardcover', 'oversized'],
    signalTypes: ['deluxe', 'hardcover'],
    source: 'Publisher Direct',
    sourceClass: 'publisher',
    sourceUrl: 'https://www.darkhorse.com/',
    coverScheme: 'berserk',
    volumes: 14,
    volumeCovers: ['berserk','berserk-2','berserk-3'],
    description: 'Oversized hardcover deluxe editions collecting Berserk in premium format with full-color pages and improved binding.',
    tags: ['deluxe','hardcover','oversized','usa','english','dark-horse'],
  },
  {
    id: 'op-100-variant',
    type: 'single',
    title: 'One Piece Vol. 100 Celebration Variant Cover',
    shortTitle: 'Vol. 100 Celebration Variant',
    series: 'One Piece',
    editionType: 'Variant Cover',
    productType: 'variant-cover',
    publisher: 'Shueisha',
    country: 'Japan',
    language: 'Japanese',
    score: 92,
    status: 'new',
    isbn: '9784088828442',
    price: '¥528',
    publishedAt: '2021-09-03',
    detectedAt: '2026-05-20',
    signals: ['variant-cover', 'celebration', 'limited-print'],
    signalTypes: ['variant-cover', 'limited-print'],
    source: 'Publisher Direct',
    sourceClass: 'publisher',
    sourceUrl: 'https://www.shueisha.co.jp/',
    coverScheme: 'op-100',
    description: 'Special variant cover edition celebrating the 100th volume milestone of One Piece, featuring exclusive artwork.',
    tags: ['variant-cover','celebration','limited','japan','japanese','shueisha'],
  },
  {
    id: 'csm-boxset',
    type: 'collection',
    title: 'Chainsaw Man Box Set Vol. 1–11',
    shortTitle: 'Box Set Vol. 1–11',
    series: 'Chainsaw Man',
    editionType: 'Box Set',
    productType: 'box-set',
    publisher: 'Norma Editorial',
    country: 'Spain',
    language: 'Spanish',
    score: 35,
    status: 'new',
    isbn: null,
    price: '€89.99',
    publishedAt: '2023-11-15',
    detectedAt: '2026-05-18',
    signals: ['box-set'],
    signalTypes: ['box-set'],
    source: 'Manga Sanctuary',
    sourceClass: 'trusted_media',
    sourceUrl: 'https://www.manga-sanctuary.com/',
    coverScheme: 'csm-boxset',
    volumes: 11,
    volumeCovers: ['csm-boxset','csm-2','csm-3'],
    description: 'Complete box set of Chainsaw Man volumes 1 through 11 by Norma Editorial for the Spanish market.',
    tags: ['box-set','spain','spanish','norma-editorial'],
  },
  {
    id: 'akira-35th',
    type: 'collection',
    title: 'Akira 35th Anniversary Box Set',
    shortTitle: '35th Anniversary Box Set',
    series: 'Akira',
    editionType: 'Anniversary Box Set',
    productType: 'box-set',
    publisher: 'Kodansha Comics',
    country: 'Japan',
    language: 'Japanese',
    score: 78,
    status: 'changed',
    isbn: null,
    price: '¥38,500',
    publishedAt: '2018-11-13',
    detectedAt: '2026-05-10',
    signals: ['box-set', 'anniversary', 'limited', 'special-cover'],
    signalTypes: ['box-set', 'anniversary', 'limited'],
    source: 'Publisher Direct',
    sourceClass: 'publisher',
    sourceUrl: 'https://www.kodansha.us/',
    coverScheme: 'akira',
    volumes: 6,
    volumeCovers: ['akira','generic-dark','generic-dark'],
    description: 'Limited 35th anniversary box set of Akira by Kodansha, featuring 6 volumes in a premium collector\'s box with exclusive artwork.',
    tags: ['box-set','anniversary','limited','japan','japanese','kodansha'],
  },
  {
    id: 'naruto-exhibition',
    type: 'single',
    title: 'Naruto Exhibition Official Fanbook',
    shortTitle: 'Exhibition Official Fanbook',
    series: 'Naruto',
    editionType: 'Fanbook',
    productType: 'fanbook',
    publisher: 'Shueisha',
    country: 'Japan',
    language: 'Japanese',
    score: 58,
    status: null,
    isbn: '9784088806983',
    price: '¥1,650',
    publishedAt: '2015-07-01',
    detectedAt: '2026-05-05',
    signals: ['fanbook', 'exhibition'],
    signalTypes: ['fanbook', 'exhibition'],
    source: 'Publisher Direct',
    sourceClass: 'publisher',
    sourceUrl: 'https://www.shueisha.co.jp/',
    coverScheme: 'naruto',
    description: 'Official fanbook produced for the Naruto exhibition, featuring exclusive artwork, interviews, and behind-the-scenes content.',
    tags: ['fanbook','exhibition','japan','japanese','shueisha'],
  },
];

// Derive rarity for each item
MANGA_ITEMS.forEach(item => {
  item.rarity = scoreToRarity(item.score);
  item.rarityConfig = RARITY_CONFIG[item.rarity];
});

const FILTER_OPTIONS = {
  rarity: ['accessible','limited','rare','very-rare','ultra-rare','unknown'],
  editionType: ['Fanbook','Box Set','Deluxe','Variant Cover','Anniversary','Anniversary Box Set','Limited Edition','Premium','Collector\'s Edition'],
  country: ['Japan','France','USA','Spain','Germany','Italy','UK'],
  language: ['Japanese','French','English','Spanish','German','Italian'],
  publisher: ['Shueisha','kazé manga','Dark Horse Comics','Norma Editorial','Kodansha Comics','Tokyopop'],
  sourceClass: ['trusted_media','publisher','marketplace'],
  status: ['new','changed'],
};

const SORT_OPTIONS = [
  { value: 'most-rare', label: 'Most Rare' },
  { value: 'recently-detected', label: 'Recently Detected' },
  { value: 'newest-release', label: 'Newest Release' },
  { value: 'a-z', label: 'A–Z' },
  { value: 'publisher', label: 'Publisher' },
];

function sortItems(items, sortBy) {
  const sorted = [...items];
  switch (sortBy) {
    case 'most-rare':      return sorted.sort((a,b) => (b.score||0) - (a.score||0));
    case 'recently-detected': return sorted.sort((a,b) => b.detectedAt.localeCompare(a.detectedAt));
    case 'newest-release': return sorted.sort((a,b) => b.publishedAt.localeCompare(a.publishedAt));
    case 'a-z':            return sorted.sort((a,b) => a.title.localeCompare(b.title));
    case 'publisher':      return sorted.sort((a,b) => a.publisher.localeCompare(b.publisher));
    default:               return sorted;
  }
}

function filterItems(items, filters, query) {
  return items.filter(item => {
    if (query) {
      const q = query.toLowerCase();
      if (![item.title, item.series, item.publisher, item.isbn||'', item.country]
        .some(f => f && f.toLowerCase().includes(q))) return false;
    }
    if (filters.rarity?.length && !filters.rarity.includes(item.rarity)) return false;
    if (filters.editionType?.length && !filters.editionType.includes(item.editionType)) return false;
    if (filters.country?.length && !filters.country.includes(item.country)) return false;
    if (filters.language?.length && !filters.language.includes(item.language)) return false;
    if (filters.publisher?.length && !filters.publisher.includes(item.publisher)) return false;
    if (filters.status?.length && !filters.status.includes(item.status)) return false;
    return true;
  });
}

// Export to window for cross-file access
Object.assign(window, {
  RARITY_CONFIG, MANGA_ITEMS, FILTER_OPTIONS, SORT_OPTIONS,
  scoreToRarity, sortItems, filterItems, COVER_SCHEMES
});
