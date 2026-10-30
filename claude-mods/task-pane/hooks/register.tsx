import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Ask } from '../types'

const PANE = 'task-pane'
const KEEP = 50

const asks = atom({ plugin: 'task-pane', key: 'asks' } as const, [], { shape: 'asks-1' })

/** The first line of a prompt, trimmed to something a narrow pane can show. */
export const toLabel = (text: string): string => {
  const line = text.split('\n').find(one => one.trim() !== '')?.trim() ?? ''
  return line.length > 72 ? `${line.slice(0, 71)}…` : line
}

const MARK = { open: '⧗', done: '✓', aborted: '✗' } as const
const COLOR = { open: 'suggestion', done: 'success', aborted: 'error' } as const

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'tasks',
      description: 'Show what you have asked for this session, and what landed',
    })
    void $.ui.open({ id: PANE, title: 'Asks' })

    return next(e)
  })

  on('command.run', { command: 'tasks' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Asks' })

    return { text: 'Asks pane opened.' }
  })

  on('prompt.submit', async ($, e, next) => {
    // A prompt the person never typed is not an ask of theirs.
    if (e.isMeta === true) return next(e)

    const label = toLabel(e.text)
    if (label === '') return next(e)

    const ask: Ask = { id: e.turnId ?? `p${await $.clock.now()}`, label, state: 'open', seconds: null }
    await update($, asks, list => [...list, ask].slice(-KEEP))

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    if (e.agentId !== undefined) return next(e)

    const seconds = Math.round(e.durationMs / 1000)
    await update($, asks, list => {
      // The turn's own ask if it carried the id, else the oldest still open.
      const target = list.findLast(one => one.id === e.turnId) ?? list.findLast(one => one.state === 'open')
      if (target === undefined) return list

      return list.map(one =>
        one === target ? { ...one, state: e.isAborted ? 'aborted' : 'done', seconds } : one,
      )
    })

    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const list = await read($, asks)
    const room = Math.max(1, (e.viewport?.rows ?? 24) - 4)
    const open = list.filter(one => one.state === 'open').length

    return (
      <Box flexDirection="column">
        {list.length === 0 && <Text dimColor>Nothing asked yet.</Text>}
        {list.slice(-room).map(ask => (
          <Text color={COLOR[ask.state]}>
            {MARK[ask.state]} {ask.label}
            {ask.seconds === null ? '' : ` (${ask.seconds}s)`}
          </Text>
        ))}
        {list.length > 0 && (
          <Box>
            <Text dimColor>
              {list.length} asked, {open} open{' '}
            </Text>
            <Button key="clear" label="Clear" onPress={() => update($, asks, () => [])} />
          </Box>
        )}
      </Box>
    )
  })
}
