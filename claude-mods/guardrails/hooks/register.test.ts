import { expect, test } from 'claude-code/testing'

import { findDestructive, findSecret } from './register'

// Fixtures are assembled from pieces: a live guardrails mod blocks the very
// literals this file has to assert on.
const RF = ['rm', '-rf'].join(' ')
const FORCE_PUSH = ['git', 'push', '-f', 'origin', 'main'].join(' ')
const TF_DESTROY = ['terraform', 'destroy'].join(' ')

test('it names destructive commands and leaves safe ones alone', () => {
  expect(findDestructive(`${RF} /`)).toBe('a recursive force delete')
  expect(findDestructive(`${RF} $BUILD_DIR/dist`)).toBe('a recursive force delete')
  expect(findDestructive(FORCE_PUSH)).toBe('a force push')
  expect(findDestructive('git reset --hard origin/main')).toBe('a hard reset')
  expect(findDestructive('terraform apply -auto-approve')).toBe('an unreviewed terraform change')
  expect(findDestructive(TF_DESTROY)).toBe('an unreviewed terraform change')

  // Narrow, ordinary work must not be blocked.
  expect(findDestructive(`${RF} node_modules`)).toBe(undefined)
  expect(findDestructive('git push origin feature/x')).toBe(undefined)
  expect(findDestructive('git push --force-with-lease origin main')).toBe(undefined)
  expect(findDestructive('terraform apply tfplan')).toBe(undefined)
  expect(findDestructive('npm test')).toBe(undefined)
})

test('it names credential shapes and ignores placeholders', () => {
  expect(findSecret('AKIAZZ3QQ7MMBBVVHHDD')).toBe('an AWS access key id')
  expect(findSecret('-----BEGIN RSA PRIVATE KEY-----')).toBe('a private key')
  expect(findSecret('api_key = "p9Qw3RtY6uI0oP2aS4dF6gH8jK1lZ3xC"')).toBe('a hard-coded credential')

  // A documented placeholder is not a leak.
  expect(findSecret('API_KEY=your-key-here')).toBe(undefined)
  expect(findSecret('ls -la && npm run build')).toBe(undefined)
})

test('the hook denies a force push and passes an ordinary one', async ($, on) => {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('tool.call', () => ({ result: {} }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const blocked = await $.tool.call({ tool: 'Bash', command: FORCE_PUSH })
  expect(blocked.deny).toContain('force push')

  const allowed = await $.tool.call({ tool: 'Bash', command: 'git status' })
  expect(allowed.deny).toBe(undefined)
})
