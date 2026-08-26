const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const MAX_FILE_SIZE = 5 * 1024 * 1024 // 5 MiB

const MIME_TO_EXT = {
  'image/jpeg': '.jpg',
  'image/png': '.png',
  'image/webp': '.webp',
}

/**
 * 验证图片文件类型和大小。
 * 返回 { valid: true, file } 或 { valid: false, error }。
 */
export function validateImageFile(file) {
  if (!file) {
    return { valid: false, error: '未选择文件' }
  }
  if (!ALLOWED_TYPES.includes(file.type)) {
    return {
      valid: false,
      error: `不支持的文件格式，请选择 ${ALLOWED_TYPES.map((t) => MIME_TO_EXT[t]).join('、')} 图片`,
    }
  }
  if (file.size > MAX_FILE_SIZE) {
    const mb = (file.size / (1024 * 1024)).toFixed(1)
    return {
      valid: false,
      error: `图片大小 ${mb} MiB 超过 5 MiB 限制，请压缩后重试`,
    }
  }
  return { valid: true, file }
}

/**
 * 将 File 对象转换为纯 Base64 字符串（不含 data URL 前缀）。
 */
export function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = /** @type {string} */ (reader.result)
      const commaIndex = dataUrl.indexOf(',')
      if (commaIndex === -1) {
        reject(new Error('无效的 Base64 数据'))
        return
      }
      resolve(dataUrl.slice(commaIndex + 1))
    }
    reader.onerror = () => reject(new Error('读取图片失败'))
    reader.readAsDataURL(file)
  })
}

/**
 * 将 File 对象转换为 Data URL，用于预览显示。
 */
export function fileToPreviewUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(/** @type {string} */ (reader.result))
    reader.onerror = () => reject(new Error('读取预览失败'))
    reader.readAsDataURL(file)
  })
}

export { ALLOWED_TYPES, MAX_FILE_SIZE, MIME_TO_EXT }