import { expect, test } from 'claude-code/testing'

import { toLabel } from './register'

const PANE = {
  plugin: 'task-pane',
  component: 'Pane',
  requestId: 'task-pane',
  props: {
    title: 'Asks',
    isFocused: false,
    bodyColumns: 60,
    placement: 'dock',
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

test('a label is the first real line, cut to the pane width', () => {
  expect(toLabel('\n\n  Fix the login bug  \nand then some')).toBe('Fix the login bug')
  expect(toLabel('x'.repeat(100))).toHaveLength(72)
  expect(toLabel('   \n  ')).toBe('')
})

test('an ask is listed open, then ticked when the turn ends', async ($, on) => {
  on('command.register', () => ({ value: { command: 'tasks' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('prompt.submit', (_, e) => ({ text: e.text }))
  on('turn.complete', (_, e) => ({ text: e.answer }))
  on('clock.now', () => ({ value: 1_000 }))

  await $.session.start({ cwd: '/', surface: 'desktop', isInteractive: true })
  await $.prompt.submit({ text: 'Cut a release branch' })

  const open = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await open.find({ type: 'Text', text: /Cut a release/ }))?.text).toContain('⧗')
  await open.unmount()

  await $.turn.complete({ answer: 'done', durationMs: 4000, isAborted: false, turnId: 't1', reason: 'answer' })

  const closed = await $.ui.mount({ ...PANE, surface: 'desktop' })
  expect((await closed.find({ type: 'Text', text: /Cut a release/ }))?.text).toContain('✓')
  await closed.unmount()
})

test('the empty pane says so, on every surface', async ($, on) => {
  on('ui.open', () => ({ value: { isPlaced: true } }))

  for (const surface of ['terminal', 'desktop', 'vscode', 'mobile'] as const) {
    const ui = await $.ui.mount({ ...PANE, surface })
    expect((await ui.find({ type: 'Text' }))?.text).toBe('Nothing asked yet.')
    await ui.unmount()
  }
})
