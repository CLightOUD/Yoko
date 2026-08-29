// 到期提醒的提示音：用 Web Audio 合成，无需外部音频文件。
// 浏览器自动播放策略要求音频上下文需先由用户手势解锁，故提供 unlockAudio 在首次交互时调用。
let ctx = null
let activeAlarm = null

export function unlockAudio() {
  const Ctx = window.AudioContext || window.webkitAudioContext
  if (!Ctx) return
  if (!ctx) {
    try {
      ctx = new Ctx()
    } catch {
      return
    }
  }
  if (ctx.state === 'suspended') ctx.resume().catch(() => {})
}

// 柔和但清晰的五音提示，音域控制在 C5-G5，避免高频过于刺耳。
const CHIME_NOTES = [
  { offset: 0, frequency: 523.25, duration: 0.32 },
  { offset: 0.28, frequency: 659.25, duration: 0.34 },
  { offset: 0.58, frequency: 783.99, duration: 0.46 },
  { offset: 1.02, frequency: 659.25, duration: 0.34 },
  { offset: 1.32, frequency: 523.25, duration: 0.58 },
]

function playChime(startAt, alarm) {
  CHIME_NOTES.forEach(({ offset, frequency, duration }) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const t = startAt + offset
    osc.type = 'triangle'
    osc.frequency.value = frequency
    gain.gain.setValueAtTime(0.0001, t)
    gain.gain.exponentialRampToValueAtTime(0.24, t + 0.035)
    gain.gain.exponentialRampToValueAtTime(0.0001, t + duration)
    osc.connect(gain)
    gain.connect(alarm.master)
    osc.start(t)
    osc.stop(t + duration + 0.02)
    alarm.oscillators.add(osc)
    osc.onended = () => alarm.oscillators.delete(osc)
  })
}

// 取消尚未播放的音符，并将正在播放的音符快速淡出，避免确认后仍继续响。
export function stopAlarm() {
  if (!activeAlarm || !ctx) return
  const alarm = activeAlarm
  activeAlarm = null
  const now = ctx.currentTime

  try {
    alarm.master.gain.cancelScheduledValues(now)
    alarm.master.gain.setValueAtTime(Math.max(alarm.master.gain.value, 0.0001), now)
    alarm.master.gain.exponentialRampToValueAtTime(0.0001, now + 0.04)
  } catch {
    // 某些旧浏览器不完整支持增益自动化，仍继续停止振荡器。
  }

  alarm.oscillators.forEach((osc) => {
    try {
      osc.stop(now + 0.05)
    } catch {
      // 已自然结束的节点无需再次处理。
    }
  })
  alarm.oscillators.clear()
}

export function playAlarm() {
  const Ctx = window.AudioContext || window.webkitAudioContext
  if (!Ctx) return
  try {
    if (!ctx) ctx = new Ctx()
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    stopAlarm()

    const master = ctx.createGain()
    master.gain.value = 1
    master.connect(ctx.destination)
    const alarm = { master, oscillators: new Set() }
    activeAlarm = alarm

    const now = ctx.currentTime
    // 三段音序间隔约 3.2 秒，总时长约 8.3 秒。
    for (let i = 0; i < 3; i += 1) playChime(now + i * 3.2, alarm)
  } catch {
    // 音频不可用时静默，不影响提醒弹窗
  }
}
