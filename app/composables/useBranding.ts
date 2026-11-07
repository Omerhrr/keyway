import { DEFAULT_BRANDING, type Branding } from '~/utils/theme'

/** Business theme + brand copy. Loaded before first paint so the login page wears it too. */
export function useBranding() {
  return useState<Branding>('branding', () => ({ ...DEFAULT_BRANDING }))
}
