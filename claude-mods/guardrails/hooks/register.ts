import type { Register } from 'claude-code'

/** Shell commands that destroy work faster than they can be undone. */
const DESTRUCTIVE: { re: RegExp; why: string }[] = [
  {
    // rm -rf aimed at a root, a home, an unset variable, or a bare glob.
    re: /\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*f|\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*f[a-zA-Z]*[rR]/,
    why: 'a recursive force delete',
  },
  { re: /\bgit\s+push\b[^|;&]*\s(--force|-f)(\s|$)/, why: 'a force push' },
  { re: /\bgit\s+reset\s+--hard\b/, why: 'a hard reset' },
  { re: /\bgit\s+clean\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[dx]/, why: 'a working-tree wipe' },
  // Applying a reviewed plan file is normal work; skipping the approval is not.
  { re: /\bterraform\s+destroy\b|\bterraform\s+apply\b[^|;&]*--?auto-approve\b/, why: 'an unreviewed terraform change' },
  { re: /\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b/i, why: 'a destructive SQL statement' },
  { re: /\bkubectl\s+delete\b[^|;&]*(--all\b|\bns\b|\bnamespace\b)/, why: 'a bulk kubectl delete' },
  { re: /:\s*\(\s*\)\s*\{.*\}\s*;\s*:/, why: 'a fork bomb' },
]

/** An rm -rf is only dangerous where it points; these targets are the dangerous ones. */
const RM_TARGET = /\brm\s[^|;&]*?(\s\/(\s|$)|\s~\/?(\s|$)|\s\$\{?[A-Za-z_][A-Za-z0-9_]*\}?\/|\s\*(\s|$)|\s\/\*|\s\.\.(\s|$))/

/** A force push to a branch everyone else builds on. */
const SHARED_BRANCH = /\b(main|master|develop|production|prod)\b/

/** Credential shapes. Matching text never reaches the log — only the label does. */
const SECRETS: { re: RegExp; label: string }[] = [
  { re: /\bAKIA[0-9A-Z]{16}\b/, label: 'an AWS access key id' },
  { re: /\bASIA[0-9A-Z]{16}\b/, label: 'an AWS session key id' },
  { re: /\bgh[pousr]_[A-Za-z0-9]{36,}\b/, label: 'a GitHub token' },
  { re: /\bgithub_pat_[A-Za-z0-9_]{22,}\b/, label: 'a GitHub fine-grained token' },
  { re: /\bsk-ant-[A-Za-z0-9_-]{20,}\b/, label: 'an Anthropic API key' },
  { re: /\bsk-[A-Za-z0-9]{32,}\b/, label: 'an OpenAI-style API key' },
  { re: /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/, label: 'a Slack token' },
  { re: /\bAIza[0-9A-Za-z_-]{35}\b/, label: 'a Google API key' },
  { re: /-----BEGIN [A-Z ]*PRIVATE KEY-----/, label: 'a private key' },
  { re: /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/, label: 'a JWT' },
  {
    // A secret-ish name assigned a long opaque literal.
    re: /\b(secret|password|passwd|token|api[_-]?key|private[_-]?key|credential)s?\s*[:=]\s*['"]?[A-Za-z0-9+/_-]{24,}['"]?/i,
    label: 'a hard-coded credential',
  },
]

/** Placeholders people deliberately commit; they are not leaks. */
const PLACEHOLDER = /\b(example|placeholder|redacted|dummy|changeme|your[_-]?(key|token|secret)|x{8,}|\.{3,})\b/i

export const findSecret = (text: string): string | undefined =>
  PLACEHOLDER.test(text) ? undefined : SECRETS.find(one => one.re.test(text))?.label

export const findDestructive = (command: string): string | undefined => {
  for (const one of DESTRUCTIVE) {
    if (!one.re.test(command)) continue
    if (one.why === 'a recursive force delete' && !RM_TARGET.test(command)) continue
    if (one.why === 'a force push') {
      if (/--force-with-lease/.test(command)) continue
      if (!SHARED_BRANCH.test(command)) continue
    }
    return one.why
  }
  return undefined
}

export const register: Register = on => {
  on('tool.call', { tool: 'Bash' }, ($, e, next) => {
    // Narrowed rather than assumed: a shape without the field is nothing to judge.
    if (!('command' in e) || typeof e.command !== 'string') return next(e)

    const danger = findDestructive(e.command)
    if (danger !== undefined) {
      return { deny: `${$.plugin.name}: that is ${danger}. Say what you want gone and I will do it narrowly, or run it yourself.` }
    }

    const secret = findSecret(e.command)
    if (secret !== undefined) {
      $.ui.toast(`${$.plugin.name}: blocked ${secret} in a shell command`)
      return { deny: `${$.plugin.name}: the command carries ${secret}. Read it from the environment instead.` }
    }

    return next(e)
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: `${$.plugin.name}: its guard failed, so the command did not run.` },
  )

  on('tool.call', { tool: 'Write' }, ($, e, next) => {
    if (!('content' in e) || typeof e.content !== 'string') return next(e)

    const secret = findSecret(e.content)
    if (secret === undefined) return next(e)

    $.ui.toast(`${$.plugin.name}: blocked ${secret} in ${e.file_path}`)
    return { deny: `${$.plugin.name}: that write carries ${secret}. Put it in the environment or a secrets manager.` }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: `${$.plugin.name}: its guard failed, so the write did not run.` },
  )

  on('tool.call', { tool: 'Edit' }, ($, e, next) => {
    if (!('new_string' in e) || typeof e.new_string !== 'string') return next(e)

    const secret = findSecret(e.new_string)
    if (secret === undefined) return next(e)

    $.ui.toast(`${$.plugin.name}: blocked ${secret} in ${e.file_path}`)
    return { deny: `${$.plugin.name}: that edit carries ${secret}. Put it in the environment or a secrets manager.` }
  }).catch(($, e, next) =>
    next.called ? next(e) : { deny: `${$.plugin.name}: its guard failed, so the edit did not run.` },
  )
}
