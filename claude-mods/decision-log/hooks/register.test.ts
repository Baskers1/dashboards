import { expect, test } from 'claude-code/testing'

import { findDecision } from './register'

test('it catches a stated decision', () => {
  expect(findDecision("Right, we'll go with Postgres for the write side.")).toBe(
    "Right, we'll go with Postgres for the write side.",
  )
  expect(findDecision('Decided: one repository per bounded context.')).toContain('Decided:')
  expect(findDecision('We settled on OpenTelemetry for traces.')).toContain('settled on')
})

test('it leaves proposals and chatter alone', () => {
  expect(findDecision('Should we go with Postgres?')).toBe(undefined)
  expect(findDecision('We could use DynamoDB, or we could use Postgres.')).toBe(undefined)
  expect(findDecision('Maybe we will go with Kafka later.')).toBe(undefined)
  expect(findDecision('The tests pass.')).toBe(undefined)
  expect(findDecision('decided to')).toBe(undefined) // too short to be a record
})

test('it takes the decision sentence out of a longer answer', () => {
  const answer = [
    'I looked at both queues.',
    'SQS is simpler to operate and the team already runs it.',
    'Decided: SQS for the outbox, revisit if ordering becomes a requirement.',
    'I will raise the change tomorrow.',
  ].join(' ')

  expect(findDecision(answer)).toBe(
    'Decided: SQS for the outbox, revisit if ordering becomes a requirement.',
  )
})

test('/decided writes a dated line into the log', async ($, on) => {
  const files = new Map<string, string>()
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', () => ({ value: { command: 'decided' } }))
  on('session.root', () => ({ value: '/repo' }))
  on('clock.now', () => ({ value: Date.UTC(2026, 9, 28) }))
  on('fs.exists', (_, e) => ({ value: files.has(e.path) }))
  on('fs.read', (_, e) => ({ value: files.get(e.path) ?? '' }))
  on('fs.write', (_, e) => {
    files.set(e.path, e.text)
    return { value: undefined }
  })

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const said = await $.command.run({ command: 'decided', args: 'Use GOV.UK Frontend, not a bespoke kit' })

  expect(said.text).toContain('memory/decisions.md')
  expect(files.get('/repo/memory/decisions.md')).toContain(
    '- 2026-10-28 — Use GOV.UK Frontend, not a bespoke kit',
  )
})
