import { HINTS, CONTEXT_HINTS } from '~/utils/hints'

/** Hover (or tap) a field label to see a short note about what belongs in the field. */
export default defineNuxtPlugin(() => {
  const norm = (s: string) => s.toLowerCase().replace(/\([^)]*\)/g, '').replace(/\s+/g, ' ').replace(/\s*\*+$/, '').trim()

  function contextsFor(el: Element): string[] {
    const out: string[] = []
    const dlg = el.closest('[role="dialog"]')
    if (dlg) {
      const t = norm((dlg.querySelector('[data-slot="title"], h2') as HTMLElement | null)?.textContent || '')
      if (t) {
        out.push(t)
        const words = t.split(' ')
        if (words.length > 2) out.push(words.slice(0, 2).join(' '))
        out.push(words[0])
      }
    }
    out.push('page:' + window.location.pathname)
    return out
  }

  function hintFor(labelEl: Element): string {
    const raw = (labelEl.textContent || '').replace('*', '')
    // "Access key (replace)" keeps its brackets as a separate entry
    const bare = norm(raw)
    for (const c of contextsFor(labelEl)) {
      const hit = CONTEXT_HINTS[`${c}|${bare}`]
      if (hit) return hit
    }
    return HINTS[bare] || HINTS[raw.toLowerCase().replace(/[()]/g, '').replace(/\s+/g, ' ').trim()] || ''
  }

  const tip = document.createElement('div')
  tip.setAttribute('role', 'tooltip')
  tip.style.cssText = 'position:fixed;z-index:400;max-width:260px;padding:6px 10px;border-radius:8px;font-size:12px;line-height:1.4;pointer-events:none;opacity:0;transition:opacity .12s;background:#18181b;color:#fff;box-shadow:0 4px 14px rgba(0,0,0,.25)'
  document.body.appendChild(tip)
  let hideTimer: any = null
  let shownAt = 0

  function show(labelEl: Element, text: string) {
    tip.textContent = text
    shownAt = Date.now()
    tip.style.opacity = '1'
    const r = labelEl.getBoundingClientRect()
    const tw = tip.offsetWidth, th = tip.offsetHeight
    let left = Math.min(Math.max(8, r.left), window.innerWidth - tw - 8)
    let top = r.bottom + 6
    if (top + th > window.innerHeight - 8) top = Math.max(8, r.top - th - 6)
    tip.style.left = `${left}px`
    tip.style.top = `${top}px`
  }
  const hide = () => { tip.style.opacity = '0' }

  const findLabel = (t: EventTarget | null) => (t as Element | null)?.closest?.('label[for]') || null

  document.addEventListener('mouseover', (e) => {
    const l = findLabel(e.target)
    if (!l) return
    const text = hintFor(l)
    if (text) { clearTimeout(hideTimer); show(l, text) }
  })
  document.addEventListener('mouseout', (e) => { if (findLabel(e.target)) hide() })
  // touch screens have no hover: a tap on a label shows the note for a few seconds
  document.addEventListener('click', (e) => {
    const l = findLabel(e.target)
    if (!l) return hide()
    const text = hintFor(l)
    if (text && window.matchMedia('(hover: none)').matches) {
      show(l, text); clearTimeout(hideTimer); hideTimer = setTimeout(hide, 3500)
    }
  })
  // scrolling moves the label away from the note, so close it (ignore the scroll that brought the label into view)
  window.addEventListener('scroll', () => { if (Date.now() - shownAt > 400) hide() }, true)
})
