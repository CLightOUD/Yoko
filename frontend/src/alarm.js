// 到期提醒的提示音：用 Web Audio 合成，无需外部音频文件。
// 浏览器自动播放策略要求音频上下文需先由用户手势解锁，故提供 unlockAudio 在首次交互时调用。
let ctx = null

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

// 到点播放：简约“叮咚”声，循环三遍，总时长约 15 秒。
function playChime(startAt) {
  if (!ctx) return
  const notes = [1046.5, 784.0] // C6 → G5，两音门铃
  notes.forEach((freq, i) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    const t = startAt + i * 0.35
    osc.type = 'sine'
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.0001, t)
    gain.gain.exponentialRampToValueAtTime(0.45, t + 0.02)
    gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.3)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(t)
    osc.stop(t + 0.32)
  })
}

export function playAlarm() {
  const Ctx = window.AudioContext || window.webkitAudioContext
  if (!Ctx) return
  try {
    if (!ctx) ctx = new Ctx()
    if (ctx.state === 'suspended') ctx.resume().catch(() => {})
    const now = ctx.currentTime
    for (let i = 0; i < 3; i += 1) playChime(now + i * 7.35)
  } catch {
    // 音频不可用时静默，不影响提醒弹窗
  }
}