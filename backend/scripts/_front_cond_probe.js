// 把 `.vue` 里某个 `computed` 的计算函数**真跑一遍**，而不是在源码里找字符串。
//
// 为什么要有这个：p57 ⑥ 以前用 `"canPreviewOne" in dia` 判「只有多段时才给按钮」——
// 文件里写着这个名字就算绿。结果主人 2026-11-02 截图：按钮根本不出现，门还是绿的。
// 判据必须问「这个状态下它返回什么」，不是「文件里有没有这句话」。
//
// 用法：
//   node _front_cond_probe.js <vue文件> <函数名> <状态数组JSON文件>
//   node _front_cond_probe.js diagnose.vue canPreviewOne states.json
// 输出：JSON 数组，每项 = 该状态下的返回值。
// 取不到函数 = 直接非零退出（判据变红，不许静默当通过）。
//
// 依赖的其它 computed（例如 `canPreviewOne` 读 `this.peekSegments`）会在同一个文件里
// 找到同名函数按需求值 —— 不用在探针里把它的实现再抄一遍（抄一遍就会两边各说一套）。
const fs = require('fs')

const [, , vuePath, fnName, statesPath] = process.argv
if (!vuePath || !fnName || !statesPath) {
  console.error('用法: node _front_cond_probe.js <vue> <函数名> <states.json>')
  process.exit(2)
}

const src = fs.readFileSync(vuePath, 'utf8')

// 本仓库 .vue 的手写函数固定是 4 空格缩进 + `\n    },` 收尾
const ALL = /^ {4}([A-Za-z_$][\w$]*)\(\)\s*\{([\s\S]*?)\n {4}\},/gm
const fns = {}
let mm
while ((mm = ALL.exec(src))) {
  const name = mm[1]
  if (!(name in fns)) fns[name] = mm[2]
}
if (!fns[fnName]) {
  console.error(`没在 ${vuePath} 里找到 ${fnName}() 的函数体`)
  process.exit(3)
}

const compiled = new Map()
function call(name, self) {
  if (!compiled.has(name)) {
    const body = fns[name]
    try {
      // `new Function` 本身就是那层壳：调用它才拿到里面那个函数
      const inner = new Function('"use strict";return function(){' + body + '\n}')()
      compiled.set(name, inner)
    } catch (e) {
      throw new Error(`解析 ${name} 失败: ${e.message}`)
    }
  }
  return compiled.get(name).call(self)
}

// `this` 代理：状态里给了就用状态；没给就看同文件里有没有同名计算属性，有就现算
function makeSelf(state) {
  const cache = new Map()
  const p = new Proxy(state, {
    get(t, prop) {
      if (prop === 'toJSON') return undefined
      if (prop in t) return t[prop]
      if (typeof prop === 'string' && fns[prop]) {
        if (!cache.has(prop)) cache.set(prop, call(prop, p))
        return cache.get(prop)
      }
      return undefined
    },
    has(t, prop) { return prop in t || (typeof prop === 'string' && !!fns[prop]) },
  })
  return p
}

const states = JSON.parse(fs.readFileSync(statesPath, 'utf8'))
const out = states.map((s) => {
  try {
    return { name: s.name || '', got: call(fnName, makeSelf(s.self || {})) }
  } catch (e) {
    return { name: s.name || '', error: String((e && e.message) || e) }
  }
})
process.stdout.write(JSON.stringify(out))
