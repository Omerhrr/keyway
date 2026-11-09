// Which pages need which permission, and which optional feature they belong to.
// [path prefix, permission (any one of), feature key]
export const ROUTE_RULES: [string, string[], string | null][] = [
  ['/dashboard', ['dashboard.view'], null],
  ['/conversations', ['conversations.view', 'conversations.manage'], 'whatsapp'],
  ['/drafts', ['orders.view', 'orders.manage'], 'whatsapp'],
  ['/orders', ['orders.view', 'orders.manage'], null],
  ['/confirmations', ['confirmations.manage'], 'confirmations'],
  ['/dispatch', ['dispatch.view', 'dispatch.manage'], 'dispatch'],
  ['/vendors', ['vendors.view', 'vendors.manage'], null],
  ['/vendor', ['vendors.view', 'vendors.manage'], null],
  ['/catalog', ['catalog.view', 'catalog.manage'], null],
  ['/inventory', ['inventory.view', 'inventory.manage'], null],
  ['/customers', ['orders.view', 'orders.manage'], null],
  ['/cod', ['cod.manage'], 'cod'],
  ['/settlements', ['settlements.manage'], 'settlements'],
  ['/finance', ['finance.manage'], 'finance'],
  ['/reports', ['reports.view'], 'reports'],
  ['/settings', ['settings.manage'], null],
  ['/audit', ['audit.view'], 'audit'],
]

export function ruleFor(path: string) {
  return ROUTE_RULES.find(([p]) => path === p || path.startsWith(p + '/'))
}
