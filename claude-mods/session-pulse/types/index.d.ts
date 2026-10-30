export type Pulse = {
  /** Percentage of the context window in use, 0-100; null before the first response. */
  contextPercent: number | null
  /** US dollars spent this session; null where the host keeps no ledger. */
  costUsd: number | null
  /** Wall-clock seconds of the last completed turn; null before the first. */
  lastTurnSeconds: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'session-pulse': { pulse: Shaped<Pulse>; isHidden: boolean }
  }
}
