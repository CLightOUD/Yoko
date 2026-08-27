import { getPushConfig, subscribePush } from './api/client'

function base64UrlToUint8Array(value) {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return Uint8Array.from(raw, (character) => character.charCodeAt(0))
}

export async function ensurePushSubscription() {
  if (
    typeof navigator === 'undefined'
    || !('serviceWorker' in navigator)
    || !('PushManager' in window)
    || Notification.permission !== 'granted'
  ) {
    return false
  }
  const config = await getPushConfig()
  if (!config.enabled || !config.application_server_key) return false

  const registration = await navigator.serviceWorker.register('/push-sw.js')
  let subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToUint8Array(config.application_server_key),
    })
  }
  const serialized = subscription.toJSON()
  await subscribePush({
    endpoint: serialized.endpoint,
    keys: serialized.keys,
  })
  return true
}
