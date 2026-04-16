import { ShapEntry } from '../services/api'

interface Props {
  entries: ShapEntry[]
}

export default function ShapChart({ entries }: Props) {
  if (!entries.length) return null

  const max = Math.max(...entries.flatMap(e => [e.before, e.after]))

  return (
    <div className="mt-4 border-t border-slate-700 pt-4">
      <h3 className="text-sm font-semibold text-white mb-3">SHAP Impact - Before vs After Fix</h3>
      <div className="space-y-2">
        {entries.map(e => (
          <div key={e.feature} className="text-xs">
            <div className="flex justify-between text-slate-400 mb-0.5">
              <span className="font-mono">{e.feature}</span>
              <span>{(e.before * 100).toFixed(1)}% → {(e.after * 100).toFixed(1)}%</span>
            </div>
            <div className="flex gap-1 h-2">
              <div
                className="bg-red-500 rounded-sm transition-all"
                style={{ width: `${max > 0 ? (e.before / max) * 100 : 0}%` }}
              />
            </div>
            <div className="flex gap-1 h-2 mt-0.5">
              <div
                className="bg-green-500 rounded-sm transition-all"
                style={{ width: `${max > 0 ? (e.after / max) * 100 : 0}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1"><span className="w-3 h-2 bg-red-500 inline-block rounded-sm" /> Before</span>
        <span className="flex items-center gap-1"><span className="w-3 h-2 bg-green-500 inline-block rounded-sm" /> After fix</span>
      </div>
    </div>
  )
}
