import type { EngineInterface, Register } from 'claude-code'

const ADR_DIR = 'docs/adr'
const PROTECTED_BRANCHES = ['main', 'master', 'develop', 'production']

export type Check = { name: string; argv: readonly string[] }

/** The checks a contributor to this repo would run before pushing. */
export const checksFor = (files: readonly string[], scripts: readonly string[]): Check[] => {
  const out: Check[] = []

  if (files.includes('package.json')) {
    for (const name of ['lint', 'typecheck', 'test'] as const) {
      if (scripts.includes(name)) out.push({ name: `npm run ${name}`, argv: ['npm', 'run', name] })
    }
  }
  if (files.includes('pyproject.toml') || files.includes('setup.cfg')) {
    out.push({ name: 'ruff check', argv: ['ruff', 'check', '.'] })
    out.push({ name: 'pytest', argv: ['pytest', '-q'] })
  }
  if (files.includes('Cargo.toml')) {
    out.push({ name: 'cargo clippy', argv: ['cargo', 'clippy', '--all-targets', '--', '-D', 'warnings'] })
    out.push({ name: 'cargo test', argv: ['cargo', 'test'] })
  }
  if (files.includes('go.mod')) {
    out.push({ name: 'go vet', argv: ['go', 'vet', './...'] })
    out.push({ name: 'go test', argv: ['go', 'test', './...'] })
  }

  return out
}

/** The next ADR number, from the highest NNNN- prefix already filed. */
export const nextNumber = (names: readonly string[]): string => {
  const highest = names.reduce((top, name) => {
    const found = /^(\d{4})-/.exec(name)
    return found === null ? top : Math.max(top, Number(found[1]))
  }, 0)

  return String(highest + 1).padStart(4, '0')
}

export const toSlug = (title: string): string =>
  title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60)

const adrBody = (number: string, title: string, date: string): string => `# ${number}. ${title}

- Date: ${date}
- Status: Proposed

## Context

What forces are at play? What constraint, deadline or obligation makes a decision necessary now?

## Decision

What we are doing, in the active voice. One paragraph.

## Options considered

| Option | For | Against |
| --- | --- | --- |
|  |  |  |

## Consequences

What becomes easier, what becomes harder, and what we have to live with.

## Review

When would we revisit this, and what evidence would change it?
`

/** Every child runs from an argv list, so nothing is interpolated into a shell. */
const runArgv = ($: EngineInterface, argv: readonly string[], timeoutMs = 300_000) =>
  $.process.run(argv, { timeoutMs }).catch(() => ({
    exitCode: 127,
    stdout: '',
    stderr: `${argv[0]} is not available here`,
    isStdoutTruncated: false,
    isStderrTruncated: false,
  }))

const lastLines = (text: string, count: number): string =>
  text.trimEnd().split('\n').slice(-count).join('\n')

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'adr',
      description: 'Draft a numbered Architecture Decision Record in docs/adr',
      argumentHint: 'the decision in a few words',
    })
    await $.command.register({
      name: 'ship',
      description: "Run this repo's own checks, and push the branch only when they all pass",
      argumentHint: 'check (to stop before pushing)',
    })

    return next(e)
  })

  on('command.run', { command: 'adr' }, async ($, e) => {
    const title = e.args?.trim() ?? ''
    if (title === '') return { text: 'Name the decision: /adr use Postgres for the write side.' }

    const root = await $.session.root()
    const dir = `${root}/${ADR_DIR}`
    const filed = (await $.fs.exists(dir)) ? (await $.fs.list(dir)).map(one => one.name) : []
    const number = nextNumber(filed)
    const date = new Date(await $.clock.now()).toISOString().slice(0, 10)
    const name = `${number}-${toSlug(title)}.md`

    await $.fs.write(`${dir}/${name}`, adrBody(number, title, date))

    return {
      text: `Drafted ${ADR_DIR}/${name} (status: Proposed).`,
      context: [
        `An ADR skeleton is at ${dir}/${name}. Fill Context, Decision, Options considered and Consequences from this session's discussion, then show the user what you wrote.`,
      ],
    }
  })

  on('command.run', { command: 'ship' }, async ($, e) => {
    const isCheckOnly = (e.args ?? '').trim().toLowerCase() === 'check'
    const root = await $.session.root()

    const branch = (await runArgv($, ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], 15_000)).stdout.trim()
    if (PROTECTED_BRANCHES.includes(branch)) {
      return { text: `On ${branch}. Cut a branch before shipping; nothing was run.` }
    }

    const names = (await $.fs.list(root)).map(one => one.name)
    const scripts = names.includes('package.json')
      ? Object.keys(JSON.parse(await $.fs.read(`${root}/package.json`)).scripts ?? {})
      : []
    const checks = checksFor(names, scripts)

    if (checks.length === 0) {
      return { text: 'No lint, typecheck or test command recognised here. Nothing ran and nothing was pushed.' }
    }

    const lines: string[] = []
    for (const check of checks) {
      $.ui.status(`ship: ${check.name}`)
      const ran = await runArgv($, check.argv)
      lines.push(`${ran.exitCode === 0 ? 'pass' : 'FAIL'}  ${check.name}`)

      if (ran.exitCode !== 0) {
        $.ui.status(undefined)
        return {
          text: [...lines, '', 'Not pushed.', '', lastLines(ran.stderr || ran.stdout, 20)].join('\n'),
          context: [`/ship stopped: ${check.name} exited ${ran.exitCode}. Diagnose and fix it, then run /ship again.`],
        }
      }
    }
    $.ui.status(undefined)

    if (isCheckOnly) return { text: [...lines, '', 'All green. Not pushed (check only).'].join('\n') }

    const pushed = await runArgv($, ['git', 'push', '-u', 'origin', branch], 120_000)
    if (pushed.exitCode !== 0) {
      return { text: [...lines, '', 'Push failed:', lastLines(pushed.stderr, 10)].join('\n') }
    }
    lines.push(`pass  pushed ${branch}`)

    const pr = await runArgv($, ['gh', 'pr', 'create', '--draft', '--fill'], 120_000)
    lines.push(
      pr.exitCode === 0
        ? `pass  draft PR: ${pr.stdout.trim().split('\n').at(-1) ?? 'created'}`
        : `--    no PR opened (${lastLines(pr.stderr, 1) || 'gh unavailable'}); open one yourself`,
    )

    return { text: lines.join('\n') }
  })
}
