import { expect, test } from 'claude-code/testing'

const COMPOSE = {
  model: 'claude-opus-5',
  promptModel: 'claude-opus-5',
  surfaces: ['terminal'],
  tools: ['Bash'],
  outputStyle: null,
  traits: [],
} as const

const engineSections = [{ id: 'intro', text: 'You are Claude Code.', scope: 'shared' as const }]

/** Stands in for the across-sessions store the engine would keep. */
const withStore = (on: Parameters<Parameters<typeof test>[1]>[1]) => {
  const kept = new Map<string, unknown>()
  on('store.get', (_, e) => ({ value: kept.get(e.key) }))
  on('store.set', (_, e) => {
    kept.set(e.key, e.value)
    return { value: undefined }
  })
}

test('the brief is appended last, after the engine sections', async ($, on) => {
  withStore(on)
  on('prompt.compose', () => ({ sections: engineSections }))

  const { sections } = await $.prompt.compose(COMPOSE)

  expect(sections[0]?.id).toBe('intro')
  expect(sections.at(-1)?.id).toBe('house-style:gds')
  expect(sections.at(-1)?.scope).toBe('session')
  expect(sections.at(-1)?.text).toContain('WCAG 2.2 level AA')
})

test('turning it off leaves the prompt as the engine composed it', async ($, on) => {
  withStore(on)
  on('prompt.compose', () => ({ sections: engineSections }))
  on('command.register', () => ({ value: { command: 'house-style' } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const said = await $.command.run({ command: 'house-style', args: '' })
  expect(said.text).toContain('off')

  const { sections } = await $.prompt.compose(COMPOSE)
  expect(sections.map(one => one.id)).toEqual(['intro'])
})
