// Theme helpers: build a full colour scale from one brand colour and turn the theme into CSS.

export interface Branding {
  brand_name: string
  tagline: string
  login_headline: string
  login_text: string
  primary: string
  radius: number
  default_mode: 'system' | 'light' | 'dark'
}

export const DEFAULT_BRANDING: Branding = {
  brand_name: 'Keyway',
  tagline: 'Logistics, delivered simply',
  login_headline: 'Your whole delivery business in one place.',
  login_text: 'Take orders from WhatsApp, keep each vendor\'s stock separate, confirm with customers, send out deliveries, track cash collected and pay vendors with confidence.',
  primary: '#059669',
  radius: 0.55,
  default_mode: 'system',
}

export const COLOR_PRESETS: { name: string; hex: string }[] = [
  { name: 'Emerald', hex: '#059669' },
  { name: 'Teal', hex: '#0d9488' },
  { name: 'Sky', hex: '#0284c7' },
  { name: 'Blue', hex: '#2563eb' },
  { name: 'Indigo', hex: '#4f46e5' },
  { name: 'Violet', hex: '#7c3aed' },
  { name: 'Pink', hex: '#db2777' },
  { name: 'Red', hex: '#dc2626' },
  { name: 'Orange', hex: '#ea580c' },
  { name: 'Amber', hex: '#d97706' },
  { name: 'Slate', hex: '#475569' },
]

function toRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}
function toHex(rgb: number[]): string {
  return '#' + rgb.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')
}
function mix(a: number[], b: number[], t: number): number[] {
  return a.map((v, i) => v + (b[i] - v) * t)
}

/** 50..950 scale: lighter shades blend with white, darker with black, 500 is the brand colour. */
export function colorScale(base: string): Record<string, string> {
  const c = toRgb(/^#[0-9a-fA-F]{6}$/.test(base) ? base : DEFAULT_BRANDING.primary)
  const white = [255, 255, 255]
  const black = [0, 0, 0]
  return {
    50: toHex(mix(c, white, 0.94)), 100: toHex(mix(c, white, 0.86)), 200: toHex(mix(c, white, 0.72)),
    300: toHex(mix(c, white, 0.52)), 400: toHex(mix(c, white, 0.28)), 500: toHex(c),
    600: toHex(mix(c, black, 0.14)), 700: toHex(mix(c, black, 0.3)), 800: toHex(mix(c, black, 0.45)),
    900: toHex(mix(c, black, 0.58)), 950: toHex(mix(c, black, 0.75)),
  }
}

export function themeCss(b: Branding): string {
  const s = colorScale(b.primary)
  const vars = Object.entries(s).map(([k, v]) => `--ui-color-primary-${k}:${v};`).join('')
  const radius = Number.isFinite(b.radius) ? b.radius : DEFAULT_BRANDING.radius
  return `:root{${vars}--ui-radius:${radius}rem;}`
}
