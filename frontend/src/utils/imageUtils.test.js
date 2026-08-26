import test from 'node:test'
import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'

import { validateImageFile, fileToBase64, fileToPreviewUrl, ALLOWED_TYPES, MAX_FILE_SIZE, MIME_TO_EXT } from './imageUtils.js'

function makeFile(bytes, type, name = 'test.png') {
  const buf = Buffer.from(bytes)
  return new File([buf], name, { type })
}

function installFileReader() {
  const orig = globalThis.FileReader
  globalThis.FileReader = class {
    async readAsDataURL(file) {
      const buf = Buffer.from(await file.arrayBuffer())
      const base64 = buf.toString('base64')
      const mime = file.type || 'application/octet-stream'
      this.result = `data:${mime};base64,${base64}`
      if (this.onload) this.onload()
    }
  }
  return () => { globalThis.FileReader = orig }
}

test('validateImageFile: valid JPEG passes', () => {
  const file = makeFile([0xff, 0xd8, 0xff], 'image/jpeg', 'photo.jpg')
  const result = validateImageFile(file)
  assert.equal(result.valid, true)
  assert.equal(result.file, file)
})

test('validateImageFile: valid PNG passes', () => {
  const file = makeFile([0x89, 0x50, 0x4e, 0x47], 'image/png', 'screenshot.png')
  const result = validateImageFile(file)
  assert.equal(result.valid, true)
})

test('validateImageFile: valid WebP passes', () => {
  const file = makeFile([0x52, 0x49, 0x46, 0x46], 'image/webp', 'image.webp')
  const result = validateImageFile(file)
  assert.equal(result.valid, true)
})

test('validateImageFile: unsupported type rejected', () => {
  const file = makeFile([0x47, 0x49, 0x46], 'image/gif', 'anim.gif')
  const result = validateImageFile(file)
  assert.equal(result.valid, false)
  assert.ok(result.error.includes('不支持'))
})

test('validateImageFile: oversized file rejected', () => {
  const bytes = new Uint8Array(MAX_FILE_SIZE + 1)
  const file = new File([bytes], 'big.jpg', { type: 'image/jpeg' })
  const result = validateImageFile(file)
  assert.equal(result.valid, false)
  assert.ok(result.error.includes('5 MiB'))
})

test('validateImageFile: exactly 5 MiB passes', () => {
  const bytes = new Uint8Array(MAX_FILE_SIZE)
  const file = new File([bytes], 'exact.jpg', { type: 'image/jpeg' })
  const result = validateImageFile(file)
  assert.equal(result.valid, true)
})

test('validateImageFile: null returns error', () => {
  const result = validateImageFile(null)
  assert.equal(result.valid, false)
})

test('fileToBase64: converts file to raw base64 string', async () => {
  const restore = installFileReader()
  try {
    const file = makeFile([0x00, 0x01, 0x02], 'image/png', 'tiny.png')
    const base64 = await fileToBase64(file)
    assert.equal(typeof base64, 'string')
    assert.ok(base64.length > 0)
    assert.ok(!base64.startsWith('data:'))
  } finally {
    restore()
  }
})

test('fileToBase64 and fileToPreviewUrl are consistent', async () => {
  const restore = installFileReader()
  try {
    const file = makeFile([0x00, 0x01, 0x02], 'image/png', 'tiny.png')
    const base64 = await fileToBase64(file)
    const preview = await fileToPreviewUrl(file)
    assert.ok(preview.startsWith('data:image/png;base64,'))
    assert.ok(preview.endsWith(base64))
  } finally {
    restore()
  }
})

test('ALLOWED_TYPES only contains JPEG, PNG, WebP', () => {
  assert.deepEqual(ALLOWED_TYPES, ['image/jpeg', 'image/png', 'image/webp'])
})

test('MIME_TO_EXT maps correctly', () => {
  assert.equal(MIME_TO_EXT['image/jpeg'], '.jpg')
  assert.equal(MIME_TO_EXT['image/png'], '.png')
  assert.equal(MIME_TO_EXT['image/webp'], '.webp')
})