/* 可访问图标组件（内联 SVG，不使用字符图标）
   文档第 10 节：图标使用可访问图标组件，不使用字符图标。 */
const Icons = {
  _svg(path, opts = {}) {
    const size = opts.size || 16;
    const stroke = opts.stroke || "currentColor";
    const label = opts.label ? `<title>${opts.label}</title>` : "";
    const cls = opts.cls ? ` class="${opts.cls}"` : "";
    return `<svg${cls} width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${label}${path}</svg>`;
  },
  dashboard: (o) => Icons._svg(`<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>`, o),
  projects: (o) => Icons._svg(`<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>`, o),
  knowledge: (o) => Icons._svg(`<path d="M4 5a2 2 0 0 1 2-2h7v16H6a2 2 0 0 0-2 2z"/><path d="M20 5a2 2 0 0 0-2-2h-3v16h3a2 2 0 0 1 2 2z"/>`, o),
  templates: (o) => Icons._svg(`<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 9v12"/>`, o),
  admin: (o) => Icons._svg(`<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1l2-1.5-2-3.4-2.3 1a7 7 0 0 0-1.7-1L14.5 3h-5l-.4 2.6a7 7 0 0 0-1.7 1l-2.3-1-2 3.4 2 1.5a7 7 0 0 0 0 2l-2 1.5 2 3.4 2.3-1a7 7 0 0 0 1.7 1l.4 2.6h5l.4-2.6a7 7 0 0 0 1.7-1l2.3 1 2-3.4-2-1.5a7 7 0 0 0 .1-1z"/>`, o),
  overview: (o) => Icons._svg(`<path d="M3 3h8v8H3zM13 3h8v5h-8zM13 11h8v10h-8zM3 13h8v8H3z"/>`, o),
  documents: (o) => Icons._svg(`<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>`, o),
  requirements: (o) => Icons._svg(`<path d="M9 11l3 3 8-8"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>`, o),
  plan: (o) => Icons._svg(`<path d="M3 6h18M3 12h18M3 18h18"/><circle cx="7" cy="6" r="1.4" fill="currentColor"/><circle cx="11" cy="12" r="1.4" fill="currentColor"/><circle cx="15" cy="18" r="1.4" fill="currentColor"/>`, o),
  authoring: (o) => Icons._svg(`<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>`, o),
  reviews: (o) => Icons._svg(`<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>`, o),
  handover: (o) => Icons._svg(`<path d="M4 7h11l-3-3M20 17H9l3 3"/>`, o),
  records: (o) => Icons._svg(`<path d="M12 8v4l3 2"/><circle cx="12" cy="12" r="9"/>`, o),
  plus: (o) => Icons._svg(`<path d="M12 5v14M5 12h14"/>`, o),
  search: (o) => Icons._svg(`<circle cx="11" cy="11" r="7"/><path d="M21 21l-4-4"/>`, o),
  check: (o) => Icons._svg(`<path d="M20 6L9 17l-5-5"/>`, o),
  close: (o) => Icons._svg(`<path d="M18 6L6 18M6 6l12 12"/>`, o),
  alert: (o) => Icons._svg(`<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>`, o),
  info: (o) => Icons._svg(`<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>`, o),
  lock: (o) => Icons._svg(`<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>`, o),
  upload: (o) => Icons._svg(`<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/>`, o),
  retry: (o) => Icons._svg(`<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>`, o),
  refresh: (o) => Icons._svg(`<path d="M21 12a9 9 0 0 0-15-6.7L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 15 6.7L21 16"/><path d="M21 21v-5h-5"/>`, o),
  eye: (o) => Icons._svg(`<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z"/><circle cx="12" cy="12" r="3"/>`, o),
  user: (o) => Icons._svg(`<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>`, o),
  download: (o) => Icons._svg(`<path d="M12 4v12M7 11l5 5 5-5"/><path d="M4 20h16"/>`, o),
  logout: (o) => Icons._svg(`<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>`, o),
  chevronRight: (o) => Icons._svg(`<path d="M9 6l6 6-6 6"/>`, o),
  split: (o) => Icons._svg(`<path d="M12 3v18M12 8l-5-5M12 8l5-5M12 16l-5 5M12 16l5 5"/>`, o),
  merge: (o) => Icons._svg(`<path d="M6 3v6a6 6 0 0 0 6 6h0M18 3v6a6 6 0 0 1-6 6M12 15v6"/>`, o),
  gate: (o) => Icons._svg(`<path d="M4 21V9a4 4 0 0 1 8 0v12M12 21V9a4 4 0 0 1 8 0v12M4 21h16"/>`, o),
  clock: (o) => Icons._svg(`<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>`, o),
  file: (o) => Icons._svg(`<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>`, o),
  link: (o) => Icons._svg(`<path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/>`, o),
};
window.Icons = Icons;
