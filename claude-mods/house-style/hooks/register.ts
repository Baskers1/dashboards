import type { EngineInterface, Register } from 'claude-code'

const KEY = 'house-style:isOn'
const SECTION_ID = 'house-style:gds'

/**
 * The standing brief. It states expectations, not law: where a specific
 * regulation or Service Standard point decides something, check the current
 * published version rather than this text.
 */
const BRIEF = `## House style (UK public sector)

Content, wherever you write user-facing words (UI copy, error messages, docs, READMEs):
- GOV.UK style: plain English, active voice, short sentences, sentence case for headings and buttons.
- Say what the user must do. No "please", no "simply", no "just", no marketing tone.
- Use the words users use, not the words the department uses. Expand an acronym on first use.
- Error messages name what went wrong and the next action.
- Dates as 1 March 2026; money as £1,234.56; use "and" not "&".

Accessibility, for anything with an interface:
- Target WCAG 2.2 level AA. Treat a failure as a defect, not an enhancement.
- Semantic HTML first; ARIA only where no element carries the meaning.
- Every control reachable and operable by keyboard, with a visible focus style.
- Text contrast at least 4.5:1 (3:1 for large text and for UI component boundaries).
- Every image, icon and chart carries a text alternative; never colour alone to carry meaning.
- Form inputs have persistent visible labels and programmatic error association.

Delivery, when shaping or reviewing work:
- Hold proposals against the GOV.UK Service Standard: user needs first, iterate, accessible by default,
  open source by default, open standards, secure and private, measurable performance.
- Prefer a tested government pattern (GOV.UK Design System, GOV.UK Frontend) over a bespoke component;
  say so when you deviate and why.
- Name the assumption when a requirement is unclear, rather than inventing policy.

Say so plainly when a request conflicts with this brief; do not silently drop it.`

/** On unless this machine has turned it off; the store outlives the session. */
const isOn = async ($: EngineInterface): Promise<boolean> => (await $.store.get(KEY)) !== false

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'house-style',
      description: 'Turn the GOV.UK content, accessibility and Service Standard brief on or off',
    })

    return next(e)
  })

  on('command.run', { command: 'house-style' }, async $ => {
    const next = !(await isOn($))
    await $.store.set(KEY, next)
    // The composed prompt is cached per turn; the change lands on the next one.
    return { text: `House style is now ${next ? 'on' : 'off'}. It applies from your next message.` }
  })

  on('prompt.compose', async ($, e, next) => {
    const composed = await next(e)
    if (!(await isOn($))) return composed

    return {
      sections: [
        ...composed.sections.filter(one => one.id !== SECTION_ID),
        { id: SECTION_ID, text: BRIEF, scope: 'session' as const },
      ],
    }
  })
}
