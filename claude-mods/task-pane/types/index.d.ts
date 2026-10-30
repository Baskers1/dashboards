export type Ask = {
  /** The turn this ask started, or a mint of its own while no turn is known. */
  id: string
  /** The ask in one line, as it will read in the pane. */
  label: string
  /** How it ended: still running, answered, or stopped. */
  state: 'open' | 'done' | 'aborted'
  /** Wall-clock seconds the turn took; null while it is open. */
  seconds: number | null
}

declare module 'claude-code' {
  interface PluginState {
    'task-pane': { asks: Shaped<Ask[]> }
  }
}
