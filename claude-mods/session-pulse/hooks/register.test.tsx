import { expect, test } from 'claude-code/testing'

import { statusLine } from './register'

test('the status line shows what it has and nothing it does not', () => {
  expect(statusLine({ contextPercent: null, costUsd: null, lastTurnSeconds: null }, 0)).toBe(undefined)
  expect(statusLine({ contextPercent: 68.4, costUsd: 1.4, lastTurnSeconds: 12 }, 42)).toBe(
    'ctx 68% · 42 turns · last 12s',
  )
})

test('a full context window is marked', () => {
  expect(statusLine({ contextPercent: 81, costUsd: null, lastTurnSeconds: null }, 0)).toBe('ctx 81%!')
  expect(statusLine({ contextPercent: 74, costUsd: null, lastTurnSeconds: null }, 0)).toBe('ctx 74%')
})

test('the band shows the spend once a cost is known, on every surface', async ($, on) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('session.measure', (_, e) => ({ changed: e.changed }))
  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.session.measure({
    context: { window: 200_000, tokens: 40_000, percent: 20 },
    rateLimits: [],
    cost: { usd: 1.4 },
    changed: ['context', 'cost'],
  })

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({
      plugin: 'session-pulse',
      component: 'AbovePrompt',
      surface,
      props: { hasSurvey: false },
    })

    expect((await ui.find({ type: 'Text', text: /1\.40/ }))?.text).toContain('$1.40')
    await ui.unmount()
  }
})
