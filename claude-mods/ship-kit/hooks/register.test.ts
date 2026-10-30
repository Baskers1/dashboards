import { expect, test } from 'claude-code/testing'

import { checksFor, nextNumber, toSlug } from './register'

test('checks follow what the repo actually is', () => {
  expect(checksFor(['package.json'], ['lint', 'test']).map(one => one.name)).toEqual([
    'npm run lint',
    'npm run test',
  ])
  // A script the repo does not define is never invented.
  expect(checksFor(['package.json'], []).length).toBe(0)
  expect(checksFor(['pyproject.toml'], []).map(one => one.name)).toEqual(['ruff check', 'pytest'])
  expect(checksFor(['go.mod'], []).map(one => one.name)).toEqual(['go vet', 'go test'])
  expect(checksFor(['README.md'], []).length).toBe(0)
})

test('every check runs from an argv list, never a shell string', () => {
  for (const check of checksFor(['pyproject.toml', 'go.mod', 'Cargo.toml'], [])) {
    expect(Array.isArray(check.argv)).toBe(true)
    expect(check.argv.length).toBeGreaterThan(1)
  }
})

test('ADR numbering continues from what is filed', () => {
  expect(nextNumber([])).toBe('0001')
  expect(nextNumber(['0001-use-postgres.md', '0007-drop-soap.md', 'README.md'])).toBe('0008')
})

test('a title becomes a tidy slug', () => {
  expect(toSlug('Use GOV.UK Frontend, not a bespoke kit')).toBe('use-gov-uk-frontend-not-a-bespoke-kit')
  expect(toSlug('  Spaces & symbols!  ')).toBe('spaces-symbols')
})

test('/ship refuses to run on a protected branch', async ($, on) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('session.root', () => ({ value: '/repo' }))
  on('process.run', () => ({ value: { exitCode: 0, stdout: 'main\n', stderr: '', isStdoutTruncated: false, isStderrTruncated: false } }))

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const said = await $.command.run({ command: 'ship', args: '' })

  expect(said.text).toContain('Cut a branch')
  expect(said.text).toContain('nothing was run')
})

test('/adr writes a numbered skeleton and tells the model to fill it', async ($, on) => {
  const files = new Map<string, string>()
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('command.register', (_, e) => ({ value: { command: e.name } }))
  on('session.root', () => ({ value: '/repo' }))
  on('clock.now', () => ({ value: Date.UTC(2026, 9, 28) }))
  on('fs.exists', () => ({ value: true }))
  on('fs.list', () => ({ value: [{ name: '0003-old.md', kind: 'file', size: 1, mtimeMs: 0, isLink: false }] }))
  on('fs.write', (_, e) => {
    files.set(e.path, e.text)
    return { value: undefined }
  })

  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  const said = await $.command.run({ command: 'adr', args: 'Use Postgres for the write side' })

  expect(said.text).toContain('0004-use-postgres-for-the-write-side.md')
  expect(said.context?.[0]).toContain('Fill Context')

  const written = files.get('/repo/docs/adr/0004-use-postgres-for-the-write-side.md') ?? ''
  expect(written).toContain('# 0004. Use Postgres for the write side')
  expect(written).toContain('Date: 2026-10-28')
  expect(written).toContain('Status: Proposed')
})
