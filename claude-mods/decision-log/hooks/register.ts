import type { EngineInterface, Register } from 'claude-code'

const LOG = 'memory/decisions.md'
const HEAD = '# Decisions\n\nOne line per decision, newest last. Appended by the decision-log mod and by hand.\n'

/**
 * Phrases that mark a decision rather than a discussion of one. Deliberately
 * tight: a journal nobody trusts is worse than no journal.
 */
const MARKERS = [
  /\bwe(?:'ll| will| are going to| 've| have) (?:go with|use|adopt|standardise on|standardize on)\b/i,
  /\b(?:decided|decision)\s*(?::|that\b|to\b)/i,
  /\blet'?s (?:go with|use|adopt)\b/i,
  /\bagreed\s*(?::|that\b|to\b)/i,
  /\bsettled on\b/i,
  /\bgoing with\b/i,
]

/** A hedge means it is still a proposal. */
const HEDGED = /\b(?:should we|shall we|could|might|maybe|perhaps|what if|do you think|or we could)\b/i

export const findDecision = (text: string): string | undefined => {
  for (const line of text.split(/(?<=[.!?\n])\s+/)) {
    const one = line.trim()
    if (one.length < 12 || one.length > 300) continue
    if (HEDGED.test(one)) continue
    if (MARKERS.some(re => re.test(one))) return one.replace(/\s+/g, ' ')
  }
  return undefined
}

/** ISO date in UTC: sortable, and the same wherever the session runs. */
const today = (nowMs: number): string => new Date(nowMs).toISOString().slice(0, 10)

const append = async ($: EngineInterface, line: string): Promise<void> => {
  const root = await $.session.root()
  const path = `${root}/${LOG}`
  const had = (await $.fs.exists(path)) ? await $.fs.read(path) : HEAD

  if (had.includes(line)) return // already recorded this session

  await $.fs.write(path, `${had.replace(/\n*$/, '')}\n- ${today(await $.clock.now())} — ${line}\n`)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'decided',
      description: 'Record a decision in memory/decisions.md',
      argumentHint: 'what was decided, and why',
    })

    return next(e)
  })

  on('command.run', { command: 'decided' }, async ($, e) => {
    const said = e.args?.trim() ?? ''
    if (said === '') return { text: 'Say what was decided: /decided we will use Postgres, not DynamoDB.' }

    await append($, said)
    return { text: `Recorded in ${LOG}.` }
  })

  on('prompt.submit', async ($, e, next) => {
    if (e.isMeta !== true) {
      const found = findDecision(e.text)
      // A write must never hold up the person's prompt.
      if (found !== undefined) void append($, found).catch(() => {})
    }

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId === undefined && !e.isAborted) {
      const found = findDecision(e.answer)
      if (found !== undefined) void append($, found).catch(() => {})
    }

    return next(e)
  })
}
