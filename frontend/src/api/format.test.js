import test from 'node:test'
import assert from 'node:assert/strict'

import { localToIso } from './format.js'


test('converts Shanghai wall time independently of the browser timezone', () => {
  assert.equal(
    localToIso('2026-08-26T09:00', 'Asia/Shanghai'),
    '2026-08-26T01:00:00.000Z',
  )
})

test('converts UTC wall time without adding an offset', () => {
  assert.equal(
    localToIso('2026-08-26T09:00', 'UTC'),
    '2026-08-26T09:00:00.000Z',
  )
})

test('respects daylight saving time for an IANA timezone', () => {
  assert.equal(
    localToIso('2026-01-15T09:00', 'America/New_York'),
    '2026-01-15T14:00:00.000Z',
  )
  assert.equal(
    localToIso('2026-07-15T09:00', 'America/New_York'),
    '2026-07-15T13:00:00.000Z',
  )
})

test('rejects invalid and nonexistent wall times', () => {
  assert.equal(localToIso('2026-02-30T09:00', 'Asia/Shanghai'), '')
  assert.equal(localToIso('2026-03-08T02:30', 'America/New_York'), '')
  assert.equal(localToIso('not-a-date', 'Asia/Shanghai'), '')
})
