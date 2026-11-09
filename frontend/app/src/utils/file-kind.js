/**
 * 按文件名/地址猜「该用哪个原生组件打开」——小程序预览页和各处 openXxx 共用。
 * 认不出来就当文本（md / srt / vtt / json 都是文本）。
 */
const VIDEO_EXT = /\.(mp4|mov|webm|mkv|m4v)(\?|$)/i
const IMAGE_EXT = /\.(png|jpe?g|webp|gif|bmp)(\?|$)/i

export function guessFileKind(name = '') {
  const s = String(name || '')
  if (VIDEO_EXT.test(s)) return 'video'
  if (IMAGE_EXT.test(s)) return 'image'
  return 'text'
}
