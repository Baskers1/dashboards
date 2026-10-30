import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Pulse } from '../types'

/** A turn longer than this is one you have probably wandered away from. */
const LONG_TURN_MS = 60_000
/** Spend past this turns the band amber. US dollars: the API prices in them. */
const SPEND_WARNING_USD = 5
/** Context fill past this turns the status line's figure into a warning. */
const CONTEXT_WARNING_PERCENT = 75

const EMPTY: Pulse = { contextPercent: null, costUsd: null, lastTurnSeconds: null }

const pulse = atom({ plugin: 'session-pulse', key: 'pulse' } as const, EMPTY, {
  shape: 'pulse-1',
})
const isHidden = atom({ plugin: 'session-pulse', key: 'isHidden' } as const, false)

export const statusLine = (it: Pulse, turns: number): string | undefined => {
  const parts: string[] = []
  if (it.contextPercent !== null) {
    const mark = it.contextPercent >= CONTEXT_WARNING_PERCENT ? '!' : ''
    parts.push(`ctx ${Math.round(it.contextPercent)}%${mark}`)
  }
  if (turns > 0) parts.push(`${turns} turns`)
  if (it.lastTurnSeconds !== null) parts.push(`last ${it.lastTurnSeconds}s`)

  return parts.length === 0 ? undefined : parts.join(' · ')
}

export const register: Register = on => {
  on('session.measure', async ($, e, next) => {
    await update($, pulse, was => ({
      ...was,
      contextPercent: e.context.percent ?? was.contextPercent,
      costUsd: e.cost?.usd ?? was.costUsd,
    }))

    $.ui.status(statusLine(await read($, pulse), await $.session.turns()))

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    // Only the main loop: a subagent finishing is not your cue to look up.
    if (e.agentId !== undefined) return next(e)

    const seconds = Math.round(e.durationMs / 1000)
    await update($, pulse, was => ({ ...was, lastTurnSeconds: seconds }))

    if (e.durationMs >= LONG_TURN_MS && !e.isAborted) {
      $.ui.toast(`Done after ${seconds}s`)
      // The chime is a courtesy: a surface with no audio must not fail the hook.
      void $.audio.play({ asset: 'fx/done.wav' }).catch(() => {})
    }

    $.ui.status(statusLine(await read($, pulse), await $.session.turns()))

    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const it = await read($, pulse)
    if (e.props.hasSurvey || it.costUsd === null || (await read($, isHidden))) {
      return next(e)
    }

    const { Box, Button, Text } = $.ui.resolve(e)
    const isHigh = it.costUsd >= SPEND_WARNING_USD

    return (
      <Box>
        <Text color={isHigh ? 'warning' : 'subtle'}>
          ${it.costUsd.toFixed(2)} this session{' '}
        </Text>
        <Button key="hide" label="Hide" onPress={() => update($, isHidden, () => true)} />
      </Box>
    )
  })
}
