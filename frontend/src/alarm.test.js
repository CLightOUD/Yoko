import assert from 'node:assert/strict'
import test from 'node:test'

class FakeAudioParam {
  value = 1

  setValueAtTime(value) {
    this.value = value
  }

  exponentialRampToValueAtTime(value) {
    this.value = value
  }

  cancelScheduledValues() {}
}

class FakeOscillator {
  frequency = { value: 0 }
  stopped = false

  connect() {}
  start() {}

  stop() {
    this.stopped = true
  }
}

class FakeAudioContext {
  static oscillators = []

  currentTime = 1
  destination = {}
  state = 'running'

  createOscillator() {
    const oscillator = new FakeOscillator()
    FakeAudioContext.oscillators.push(oscillator)
    return oscillator
  }

  createGain() {
    return {
      gain: new FakeAudioParam(),
      connect() {},
    }
  }

  resume() {
    return Promise.resolve()
  }
}

test('stopAlarm stops all scheduled alarm notes', async () => {
  globalThis.window = { AudioContext: FakeAudioContext }
  const { playAlarm, stopAlarm } = await import('./alarm.js')

  playAlarm()
  assert.equal(FakeAudioContext.oscillators.length, 15)

  stopAlarm()
  assert.ok(FakeAudioContext.oscillators.every((oscillator) => oscillator.stopped))
})
